#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
veroeffentlichen.py — Ein-Klick-Veröffentlichung für Dashboard Mobil
=====================================================================

Gedacht für den Doppelklick auf „Dashboard Mobil veröffentlichen.command" im
OneDrive-Ordner KI/Dashboard Mobil — und für den Portal-Wächter, der
`--pruefen` aufrufen und bei „OFFEN" selbst veröffentlichen kann.

  1. holt den GitHub-Stand ab (git pull)
  2. vergleicht die Inhalte (Lerndashboards, Präsentationen, Simulationen samt
     README.md/github.json/zuordnung.json) und die Repo-Liste bei GitHub mit dem
     Stand der letzten Veröffentlichung
  3. baut verschlüsselt neu, prüft docs/ auf private Klartexte, committet, pusht —
     nur wenn sich etwas geändert hat

    /usr/bin/python3 veroeffentlichen.py              prüfen und bei Bedarf veröffentlichen
    /usr/bin/python3 veroeffentlichen.py --pruefen    nur nachsehen: NICHTS-ZU-TUN / OFFEN
    /usr/bin/python3 veroeffentlichen.py --erzwingen  auch ohne Datei-Änderung bauen und pushen
                                                      (nach Code- oder Passwort-Änderungen)
    /usr/bin/python3 veroeffentlichen.py --nur-pruefung   nur die Klartext-Prüfung von docs/
"""

import json
import subprocess
import sys
import unicodedata
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
import build as B  # noqa: E402  (gleicher Ordner: Quellen einsammeln, Repo-Signatur)

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


def inventar(cfg, mit_repos=True):
    """Alles, was in den Build eingeht: {Schlüssel: [Größe, mtime]} + Repo-Signatur unter "@repos"
    (None, wenn GitHub gerade nicht erreichbar war)."""
    manifest, jobs, _ = B.sammle(cfg)
    inv = {}
    for schluessel, p, _e, _rel in jobs:
        inv[schluessel] = stat_von(p)
    for bereich, quelle in B.quellen(cfg).items():
        if not quelle.is_dir():
            continue
        if bereich == "simulationen":
            kandidaten = [p for p in quelle.rglob("*") if p.is_dir()]
        else:
            kandidaten = [p for p in quelle.iterdir() if p.is_dir()]
        for ordner in kandidaten:
            if any(t.startswith(".") or t.lower() in B.IGNORIERTE_ORDNER for t in ordner.relative_to(quelle).parts):
                continue
            for name in BEGLEITER:
                p = ordner / name
                if p.is_file():
                    inv[f"{bereich}/{ordner.relative_to(quelle).as_posix()}/{name}"] = stat_von(p)
    # Zuordnungen (Simulations-Filemanager) und Journal-Klassen fließen in den Build ein – Änderungen dort
    # müssen ebenfalls eine Veröffentlichung auslösen.
    pf = B.zuordnung_pfade(cfg)
    if pf.get("zentral") and pf["zentral"].is_file():
        inv["@zuordnung/zentral"] = stat_von(pf["zentral"])
    j = pf.get("journal")
    if j and j.is_dir():
        dateien = [j / "config.json", j / "aktuelles-jahr.txt"]
        try:
            jahr = (j / "aktuelles-jahr.txt").read_text(encoding="utf-8").strip()
            if jahr:
                dateien += [j / jahr / "stundenplan.json", j / jahr / "skripte.json"]
        except Exception:
            pass
        for q in dateien:
            if q.is_file():
                inv[f"@journal/{q.relative_to(j).as_posix()}"] = stat_von(q)
    inv["@repos"] = B.repos_signatur(B.eigenes_repo(cfg), (cfg.get("repos") or {}).get("portale")) if mit_repos else None
    return inv, manifest


# ─────────────────────────── Klartext-Prüfung ───────────────────────────────

def verbotene_texte(cfg, manifest):
    """Private Texte, die nie im Klartext in docs/ stehen dürfen."""
    texte = []
    for z in cfg.get("zugaenge") or []:
        pw = unicodedata.normalize("NFC", str(z.get("passwort") or "")).strip()
        if len(pw) >= 8:
            texte.append((pw.lower(), f"Passwort von Zugang „{z.get('name', '?')}“"))
            texte.append((pw.lower().replace("-", ""), f"Passwort von Zugang „{z.get('name', '?')}“ (ohne Bindestriche)"))
    texte.append(('id="meta"', "Planungsblock eines Lerndashboards"))
    for b in B.BEREICHE:
        for e in (manifest.get("bereiche") or {}).get(b, []):
            t = str(e.get("titel") or "").strip()
            if e.get("typ") == "tresor" and len(t) >= 8:
                texte.append((t.lower(), f"Titel von {b}/{e.get('id')}"))
    return texte


def pruefe_klartext(cfg, manifest):
    """docs/ nach privaten Klartexten durchsuchen; geheime Dateien dürfen nicht im Git-Index sein."""
    treffer = []
    for geheim in GEHEIM:
        if git("ls-files", "--error-unmatch", geheim, fehler_ok=True).returncode == 0:
            treffer.append((geheim, "geheime Datei ist im Git-Index"))
    for zeile in git("ls-files", "-s", fehler_ok=True).stdout.splitlines():
        if zeile.startswith("120000"):
            treffer.append((zeile.split("\t", 1)[-1], "Verknüpfung (Symlink) im Git-Index"))
    texte = verbotene_texte(cfg, manifest)
    for p in sorted(DOCS.rglob("*")):
        if not p.is_file() or p.suffix == ".enc":            # Chiffrat: zufällige Bytes, kein Text
            continue
        rel = p.relative_to(HIER).as_posix()
        klein = p.read_bytes().lower()
        for text, art in texte:
            if text.encode("utf-8") in klein:
                treffer.append((rel, art))
    return treffer


# ─────────────────────────── Ablauf ─────────────────────────────────────────

def main():
    if not KONFIG.is_file():
        sys.exit("zugangsdaten.json fehlt im Repo-Ordner (Verknüpfung nach _Portal-Setup/geheim).")
    cfg = json.loads(KONFIG.read_text(encoding="utf-8"))
    url = cfg.get("url") or "https://temmchen.github.io/dashboard/"

    if "--nur-pruefung" in sys.argv:
        manifest, _, _ = B.sammle(cfg)
        treffer = pruefe_klartext(cfg, manifest)
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
    alt = stand_alt.get("inventar", {})

    # --pruefen: nur nachsehen, nichts anfassen (Portal-Wächter)
    if "--pruefen" in sys.argv:
        jetzt, _ = inventar(cfg)
        if jetzt.get("@repos") is None:
            jetzt["@repos"] = alt.get("@repos")      # GitHub nicht erreichbar → zählt nicht als Änderung
        git("fetch", "--quiet", "origin", "main", fehler_ok=True)
        voraus = git("rev-list", "--count", "HEAD..origin/main", fehler_ok=True).stdout.strip() or "0"
        if jetzt == alt and voraus == "0":
            print("NICHTS-ZU-TUN")
        else:
            print("OFFEN")
        return

    sag("📱 Dashboard Mobil — Prüfen & Veröffentlichen")
    sag("=" * 46)

    # 1) GitHub-Stand holen
    hat_remote = bool(git("remote", fehler_ok=True).stdout.strip())
    if not hat_remote:
        sys.exit("❌ Kein GitHub-Remote eingerichtet — bitte „Dashboard Mobil einrichten.command“ ausführen.")
    sag("\n① Hole aktuellen Stand von GitHub …")
    pull = git("pull", "--no-rebase", "--quiet", "origin", "main", fehler_ok=True)
    if pull.returncode != 0:
        sag(f"❌ git pull fehlgeschlagen — bitte zuerst am Mac aufräumen:\n{pull.stderr.strip()}")
        sys.exit(1)

    # 2) Änderungen seit der letzten Veröffentlichung
    jetzt, manifest = inventar(cfg)
    repos_neu = jetzt.get("@repos")
    if repos_neu is None:
        jetzt["@repos"] = alt.get("@repos")
        sag("   ⚠️  GitHub-Repo-Liste nicht abrufbar — die letzte Liste bleibt.")
    neu = sorted(k for k in set(jetzt) - set(alt) if not k.startswith("@"))
    weg = sorted(k for k in set(alt) - set(jetzt) if not k.startswith("@"))
    geaendert = sorted(k for k in set(jetzt) & set(alt) if jetzt[k] != alt[k] and not k.startswith("@"))
    repos_anders = jetzt.get("@repos") != alt.get("@repos")
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
    if repos_anders:
        sag("   ~ GitHub-Repos (neu, umbenannt oder gepusht)")
    if not (neu or geaendert or weg or repos_anders):
        sag("   (keine Änderungen)")

    erzwingen = "--erzwingen" in sys.argv
    if erzwingen:
        sag("   (--erzwingen: baue und veröffentliche auch ohne Änderung)")
    if not (neu or geaendert or weg or repos_anders or erzwingen):
        sag("\n✅ Alles aktuell — iPhone und iPad haben schon den neuesten Stand.")
        STAND.write_text(json.dumps({"inventar": jetzt}), encoding="utf-8")
        return

    # 3) Bauen (die Repo-Liste wurde gerade eben abgefragt; ohne Zugriff bleibt die alte)
    sag("\n③ Baue verschlüsselt neu …")
    r = subprocess.run([sys.executable, str(HIER / "build.py")] + (["--ohne-repos"] if repos_neu is None else []))
    if r.returncode != 0:
        sys.exit("❌ build.py fehlgeschlagen — es wurde nichts veröffentlicht.")

    # 4) Klartext-Prüfung
    sag("\n④ Prüfe docs/ auf private Klartexte …")
    treffer = pruefe_klartext(cfg, manifest)
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
    if repos_anders:
        teile.append("Repo-Liste")
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
    sag("   Auf iPhone/iPad: Dashboard öffnen — die Seite lädt den neuen Stand von selbst.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sag("\nAbgebrochen — es wurde nichts veröffentlicht.")
