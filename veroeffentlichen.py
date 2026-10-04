#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
veroeffentlichen.py — Ein-Klick-Veröffentlichung für die Lerndashboards
========================================================================

Gedacht für den Doppelklick auf „Lerndashboards veröffentlichen.command" im
OneDrive-Ordner KI/Lerndashboards Mobil — und für den Portal-Wächter, der
`--pruefen` aufrufen und bei „OFFEN" selbst veröffentlichen kann.

  1. holt den GitHub-Stand ab (git pull)
  2. vergleicht die Lerndashboards (HTML-Datei, README.md und github.json je
     Modulordner) mit dem Stand der letzten Veröffentlichung
  3. baut verschlüsselt neu, prüft docs/ auf private Klartexte, committet, pusht —
     nur wenn sich etwas geändert hat

    /usr/bin/python3 veroeffentlichen.py              prüfen und bei Bedarf veröffentlichen
    /usr/bin/python3 veroeffentlichen.py --pruefen    nur nachsehen: NICHTS-ZU-TUN / OFFEN
    /usr/bin/python3 veroeffentlichen.py --erzwingen  auch ohne Datei-Änderung bauen und pushen
                                                      (nach Code- oder Passwort-Änderungen)
    /usr/bin/python3 veroeffentlichen.py --nur-pruefung   nur die Klartext-Prüfung von docs/
"""

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

HIER = Path(__file__).resolve().parent
DOCS = HIER / "docs"
KONFIG = HIER / "zugangsdaten.json"
STAND = HIER / ".letzter-stand.json"          # lokales Gedächtnis (gitignored)
GEHEIM = ("zugangsdaten.json", ".build-state.json", ".letzter-stand.json")
BEGLEITER = ("README.md", "github.json", "zuordnung.json")


def sag(text=""):
    print(text, flush=True)


def git(*args, fehler_ok=False):
    r = subprocess.run(["git", "-C", str(HIER)] + list(args), capture_output=True, text=True)
    if r.returncode != 0 and not fehler_ok:
        sag(f"❌ git {' '.join(args)} fehlgeschlagen:\n{r.stderr.strip()}")
        sys.exit(1)
    return r


def stat_von(p: Path):
    st = p.stat()
    return [st.st_size, int(st.st_mtime)]


def inventar(cfg):
    """Alles, was in den Build eingeht: {relativer Pfad: [Größe, mtime]}."""
    quelle = Path(cfg["quelle"]).expanduser()
    inv = {}
    if not quelle.is_dir():
        return inv
    for ordner in sorted(p for p in quelle.iterdir() if p.is_dir()):
        if ordner.name.startswith((".", "_")):
            continue
        for p in sorted(ordner.glob("*.html")):
            if p.is_file() and not p.name.startswith("."):
                inv[f"{ordner.name}/{p.name}"] = stat_von(p)
        for name in BEGLEITER:
            p = ordner / name
            if p.is_file():
                inv[f"{ordner.name}/{name}"] = stat_von(p)
    return inv


# ─────────────────────────── Klartext-Prüfung ───────────────────────────────

def verbotene_texte(cfg):
    """Private Texte, die nie im Klartext in docs/ stehen dürfen."""
    texte = []
    for z in cfg.get("zugaenge") or []:
        pw = unicodedata.normalize("NFC", str(z.get("passwort") or "")).strip()
        if len(pw) >= 8:
            texte.append((pw.lower(), f"Passwort von Zugang „{z.get('name', '?')}“"))
            texte.append((pw.lower().replace("-", ""), f"Passwort von Zugang „{z.get('name', '?')}“ (ohne Bindestriche)"))
    # Kennzeichen eines Dashboards im Klartext: der eingebettete Planungsblock und die Titel.
    texte.append(('id="meta"', "Planungsblock eines Dashboards"))
    quelle = Path(cfg["quelle"]).expanduser()
    if quelle.is_dir():
        for ordner in quelle.iterdir():
            if not ordner.is_dir() or ordner.name.startswith((".", "_")):
                continue
            for p in ordner.glob("*.html"):
                try:
                    m = re.search(r"<title>(.*?)</title>", p.read_text(encoding="utf-8", errors="replace"), re.S | re.I)
                except Exception:
                    m = None
                if m and len(m.group(1).strip()) >= 8:
                    texte.append((m.group(1).strip().lower(), f"Titel von {ordner.name}/{p.name}"))
    return texte


def pruefe_klartext(cfg):
    """docs/ nach privaten Klartexten durchsuchen; geheime Dateien dürfen nicht im Git-Index sein."""
    treffer = []
    for geheim in GEHEIM:
        if git("ls-files", "--error-unmatch", geheim, fehler_ok=True).returncode == 0:
            treffer.append((geheim, "geheime Datei ist im Git-Index"))
    for zeile in git("ls-files", "-s", fehler_ok=True).stdout.splitlines():
        if zeile.startswith("120000"):
            treffer.append((zeile.split("\t", 1)[-1], "Verknüpfung (Symlink) im Git-Index"))
    texte = verbotene_texte(cfg)
    for p in sorted(DOCS.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(HIER).as_posix()
        if p.suffix == ".enc":
            continue                                   # Chiffrat: zufällige Bytes, kein Text
        roh = p.read_bytes()
        klein = roh.lower()
        for text, art in texte:
            if text.encode("utf-8") in klein:
                treffer.append((rel, art))
    return treffer


# ─────────────────────────── Ablauf ─────────────────────────────────────────

def main():
    if not KONFIG.is_file():
        sys.exit("zugangsdaten.json fehlt im Repo-Ordner (Verknüpfung nach _Portal-Setup/geheim).")
    cfg = json.loads(KONFIG.read_text(encoding="utf-8"))
    url = cfg.get("url") or "https://temmchen.github.io/lerndashboards/"
    quelle = Path(cfg["quelle"]).expanduser()
    if not quelle.is_dir():
        sys.exit(f"Quellordner nicht gefunden: {quelle}")

    if "--nur-pruefung" in sys.argv:
        treffer = pruefe_klartext(cfg)
        if treffer:
            sag("❌ Private Angaben im Klartext gefunden:")
            for datei, art in treffer:
                sag(f"   {datei}: {art}")
            sys.exit(1)
        sag("✅ keine privaten Klartexte in docs/, geheime Dateien nicht im Index")
        return

    stand_alt = {}
    if STAND.is_file():
        try:
            stand_alt = json.loads(STAND.read_text(encoding="utf-8"))
        except Exception:
            stand_alt = {}

    # --pruefen: nur nachsehen, nichts anfassen (Portal-Wächter)
    if "--pruefen" in sys.argv:
        jetzt = inventar(cfg)
        git("fetch", "--quiet", "origin", "main", fehler_ok=True)
        voraus = git("rev-list", "--count", "HEAD..origin/main", fehler_ok=True).stdout.strip() or "0"
        if jetzt == stand_alt.get("inventar", {}) and voraus == "0":
            print("NICHTS-ZU-TUN")
        else:
            print("OFFEN")
        return

    sag("📱 Lerndashboards — Prüfen & Veröffentlichen")
    sag("=" * 46)

    # 1) GitHub-Stand holen
    hat_remote = bool(git("remote", fehler_ok=True).stdout.strip())
    if not hat_remote:
        sys.exit("❌ Kein GitHub-Remote eingerichtet — bitte „Lerndashboards einrichten.command“ ausführen.")
    sag("\n① Hole aktuellen Stand von GitHub …")
    pull = git("pull", "--no-rebase", "--quiet", "origin", "main", fehler_ok=True)
    if pull.returncode != 0:
        sag(f"❌ git pull fehlgeschlagen — bitte zuerst am Mac aufräumen:\n{pull.stderr.strip()}")
        sys.exit(1)

    # 2) Änderungen seit der letzten Veröffentlichung
    jetzt = inventar(cfg)
    alt = stand_alt.get("inventar", {})
    neu = sorted(set(jetzt) - set(alt))
    weg = sorted(set(alt) - set(jetzt))
    geaendert = sorted(k for k in set(jetzt) & set(alt) if jetzt[k] != alt[k])
    sag("\n② Änderungen seit der letzten Veröffentlichung:" if stand_alt
        else "\n② Erste Veröffentlichung mit diesem Werkzeug — nehme alles auf:")
    for k in neu[:15]:
        sag(f"   + {k}")
    if len(neu) > 15:
        sag(f"   + … und {len(neu) - 15} weitere")
    for k in geaendert[:10]:
        sag(f"   ~ {k}")
    if len(geaendert) > 10:
        sag(f"   ~ … und {len(geaendert) - 10} weitere")
    for k in weg[:10]:
        sag(f"   − {k}")
    if not (neu or geaendert or weg):
        sag("   (keine Änderungen)")

    erzwingen = "--erzwingen" in sys.argv
    if erzwingen:
        sag("   (--erzwingen: baue und veröffentliche auch ohne Änderung)")
    if not (neu or geaendert or weg or erzwingen):
        sag("\n✅ Alles aktuell — iPhone und iPad haben schon den neuesten Stand.")
        STAND.write_text(json.dumps({"inventar": jetzt}), encoding="utf-8")
        return

    # 3) Bauen
    sag("\n③ Baue verschlüsselt neu …")
    r = subprocess.run([sys.executable, str(HIER / "build.py")])
    if r.returncode != 0:
        sys.exit("❌ build.py fehlgeschlagen — es wurde nichts veröffentlicht.")

    # 4) Klartext-Prüfung
    sag("\n④ Prüfe docs/ auf private Klartexte …")
    treffer = pruefe_klartext(cfg)
    if treffer:
        sag("❌ Private Angaben im Klartext gefunden – es wird NICHTS veröffentlicht:")
        for datei, art in treffer:
            sag(f"   {datei}: {art}")
        sys.exit(1)
    sag("   ✅ keine privaten Klartexte, keine Verknüpfungen, geheime Dateien nicht im Index")

    # 5) Veröffentlichen — bewusst NUR die Tresor-Daten; Änderungen an index.html o. Ä.
    #    werden getrennt committet (sonst ginge Halbfertiges ungeprüft online).
    teile = []
    if neu:
        teile.append(f"{len(neu)} neu")
    if geaendert:
        teile.append(f"{len(geaendert)} geändert")
    if weg:
        teile.append(f"{len(weg)} entfernt")
    nachricht = "Inhalte aktualisiert: " + (", ".join(teile) if teile else "neu gebaut")

    sag("⑤ Veröffentliche …")
    git("add", "docs/vaults", "docs/.nojekyll")
    andere = [z for z in git("status", "--porcelain", "--", "docs", fehler_ok=True).stdout.splitlines()
              if z and not z[3:].startswith("docs/vaults") and not z[3:].endswith(".nojekyll")]
    if andere:
        sag("   ℹ️  Lokal geändert, wird NICHT mitveröffentlicht (bei Bedarf manuell committen):")
        for z in andere[:5]:
            sag(f"      {z[3:]}")
    commit = git("commit", "-q", "-m", nachricht, fehler_ok=True)
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
        sag(f"❌ git commit: {commit.stderr.strip()}")
        sys.exit(1)
    git("push", "-q", "origin", "main")

    STAND.write_text(json.dumps({"inventar": jetzt}), encoding="utf-8")
    sag(f"\n✅ Fertig! In 1–2 Minuten online: {url}")
    sag("   Auf iPhone/iPad: Lerndashboards öffnen — die Seite lädt den neuen Stand von selbst.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sag("\nAbgebrochen — es wurde nichts veröffentlicht.")
