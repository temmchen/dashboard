#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verwaltung.py — Lerndashboards · Zugänge verwalten
===================================================

Verwaltet die Zugänge in zugangsdaten.json (liegt als Verknüpfung in OneDrive,
_Portal-Setup/geheim/Lerndashboards-zugangsdaten.json) und schreibt die lesbare
Passwort-Übersicht samt QR-Code in den OneDrive-Ordner „KI/Lerndashboards Mobil“
(Feld `werkzeuge` der zugangsdaten.json) sowie eine Kopie nach „KI/Passwoerter“.

    /usr/bin/python3 verwaltung.py liste              alle Zugänge anzeigen
    /usr/bin/python3 verwaltung.py passwort "Tom"     Passwort neu würfeln + Tresor neu verschlüsseln
    /usr/bin/python3 verwaltung.py setzen "Tom" "neues-passwort"   eigenes Passwort setzen
    /usr/bin/python3 verwaltung.py zugang "iPad"      weiteren Zugang anlegen
    /usr/bin/python3 verwaltung.py entfernen "iPad"   Zugang entfernen
    /usr/bin/python3 verwaltung.py readme             Passwort-Übersicht und QR-Code neu schreiben

Nach jedem Befehl (außer liste/readme) läuft build.py; danach veröffentlichen:
    /usr/bin/python3 veroeffentlichen.py --erzwingen
"""

import argparse
import json
import secrets
import subprocess
import sys
import unicodedata
from datetime import date
from pathlib import Path

HIER = Path(__file__).resolve().parent
KONFIG = HIER / "zugangsdaten.json"

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # ohne 0/O, 1/l/i — tippfreundlich


def neues_passwort(gruppen=4):
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(gruppen))


def lade():
    if not KONFIG.is_file():
        sys.exit("zugangsdaten.json fehlt — Vorlage: zugangsdaten.beispiel.json")
    return json.loads(KONFIG.read_text(encoding="utf-8"))


def speichere(cfg):
    KONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    schreibe_passwort_readme(cfg)


# ─────────────────────────── Passwort-Übersicht ─────────────────────────────

def qr_erzeugen(url: str, ziel: Path) -> bool:
    """QR-Code als PNG (Modul qrcode + pillow, sonst segno). Fehlt beides, gibt es keinen QR."""
    try:
        import qrcode
        img = qrcode.make(url, border=2, box_size=10)
        img.save(str(ziel))
        return True
    except Exception:
        pass
    try:
        import segno
        segno.make(url, error="m").save(str(ziel), scale=10, border=2)
        return True
    except Exception:
        return False


def werkzeugordner(cfg) -> Path:
    try:
        return Path(cfg["werkzeuge"]).expanduser()
    except Exception:
        return HIER


def schreibe_passwort_readme(cfg):
    """Lesbare Passwort-Übersicht in den OneDrive-Ordner „KI/Lerndashboards Mobil“ und
    nach „KI/Passwoerter“ schreiben — beides außerhalb des Repos, nie hochgeladen."""
    url = cfg.get("url") or "https://temmchen.github.io/lerndashboards/"
    ordner = werkzeugordner(cfg)
    if not ordner.is_dir():
        print(f"ℹ️  Werkzeugordner fehlt ({ordner}) — keine Passwort-Übersicht geschrieben.")
        return
    qr = ordner / "QR-Lerndashboards.png"
    hat_qr = qr_erzeugen(url, qr)
    stand = date.today().strftime("%d.%m.%Y")

    z = []
    z.append("# 🔐 Lerndashboards (iPhone & iPad) — Zugang und Passwort")
    z.append("")
    z.append("> ⚠️ **NUR für dich (OneDrive, privat).** Niemals ins Repo kopieren, niemals teilen.")
    z.append("> Diese Datei schreibt `verwaltung.py` **automatisch** — nicht von Hand pflegen.")
    z.append("> Quelle der Wahrheit: `_Portal-Setup/geheim/Lerndashboards-zugangsdaten.json`.")
    z.append("")
    z.append(f"**Adresse:** {url}  ")
    z.append(f"**Schuljahr:** {cfg.get('schuljahr', '?')} · **Stand:** {stand}")
    z.append("")
    if hat_qr:
        z.append("**Am iPhone/iPad öffnen:** Kamera auf den Code halten, dann in Safari „Teilen → Zum Home-Bildschirm“.")
        z.append("")
        z.append("![QR-Code Lerndashboards](QR-Lerndashboards.png)")
        z.append("")
    z.append("| Zugang | Passwort |")
    z.append("|---|---|")
    for zg in cfg.get("zugaenge", []):
        z.append(f"| **{zg.get('name', '?')}** | `{zg.get('passwort', '?')}` |")
    z.append("")
    z.append("Anmelden: Zugang (Name) und Passwort eingeben — Bindestriche mitschreiben, Groß-/Kleinschreibung")
    z.append("spielt keine Rolle. Mit dem Häkchen „Auf diesem Gerät angemeldet bleiben“ merkt sich das Gerät den")
    z.append("Tresor-Schlüssel (nicht das Passwort) — „Abmelden“ löscht ihn wieder. Beim ersten Anmelden bietet")
    z.append("Safari an, Zugang und Passwort in **Passwörter** (iCloud-Schlüsselbund) zu sichern.")
    z.append("")
    z.append("## Gut zu wissen")
    z.append("")
    z.append("- Passwort ändern: `/usr/bin/python3 ~/Documents/GitHub/lerndashboards/verwaltung.py passwort \"Tom\"`")
    z.append("  (oder `… setzen \"Tom\" \"wunsch-passwort\"`) → der Tresor wird neu verschlüsselt, alte Anmeldungen")
    z.append("  auf den Geräten verfallen. Danach `Lerndashboards veröffentlichen.command` doppelklicken.")
    z.append("- Weiterer Zugang (z. B. iPad mit eigenem Passwort): `… verwaltung.py zugang \"iPad\"`")
    z.append("- Inhalte: alle Lerndashboards aus `KI/Lerndashboards/` (je Modul die HTML-Datei oben im Ordner);")
    z.append("  Ordner mit `github.json` erscheinen nur als Link auf die öffentliche GitHub-Pages-Seite.")
    z.append("- Das Repo `temmchen/lerndashboards` ist öffentlich, enthält aber nur Programmcode und AES-256-Chiffrat.")
    text = "\n".join(z) + "\n"
    (ordner / "PASSWOERTER.md").write_text(text, encoding="utf-8")

    # Zweite Kopie neben den anderen Portal-Zugangsdaten (KI/Passwoerter/), ohne Bild-Link.
    passwoerter = ordner.parent / "Passwoerter"
    if passwoerter.is_dir():
        kopie = text.replace("![QR-Code Lerndashboards](QR-Lerndashboards.png)",
                             "QR-Code: `KI/Lerndashboards Mobil/QR-Lerndashboards.png`")
        (passwoerter / "Lerndashboards README.md").write_text(kopie, encoding="utf-8")


# ─────────────────────────── Befehle ────────────────────────────────────────

def baue(extra=()):
    print("\n— Tresor wird neu gebaut —", flush=True)
    r = subprocess.run([sys.executable, str(HIER / "build.py")] + list(extra))
    if r.returncode != 0:
        sys.exit("build.py ist fehlgeschlagen — Änderung ist gespeichert, aber noch nichts veröffentlicht.")


def abschluss(*zeilen):
    print()
    for z in zeilen:
        print(z)
    print("\nJetzt veröffentlichen:  /usr/bin/python3 veroeffentlichen.py --erzwingen")
    print("(oder Doppelklick auf „Lerndashboards veröffentlichen.command“ — mit --erzwingen)")


def cmd_liste(cfg):
    print(f"Lerndashboards · {cfg.get('schuljahr', '?')} · {cfg.get('url', '')}")
    print(f"Inhalte aus: {cfg.get('quelle', '?')}\n")
    for zg in cfg.get("zugaenge", []):
        print(f"  {zg.get('name', '?'):22s} Passwort: {zg.get('passwort', '?')}")


def finde(cfg, name):
    n = name.strip().lower()
    for zg in cfg.get("zugaenge", []):
        if str(zg.get("name", "")).strip().lower() == n:
            return zg
    return None


def pruefe_passwort(pw: str):
    pw = unicodedata.normalize("NFC", pw).strip()
    if len(pw) < 12:
        sys.exit("Das Passwort sollte mindestens 12 Zeichen haben (Muster: xxxx-xxxx-xxxx-xxxx).")
    return pw


def cmd_passwort(cfg, wer, neu=None):
    zg = finde(cfg, wer)
    if not zg:
        sys.exit(f"'{wer}' nicht gefunden — verwaltung.py liste zeigt alle Zugänge.")
    zg["passwort"] = pruefe_passwort(neu) if neu else neues_passwort(4)
    for anderer in cfg.get("zugaenge", []):
        if anderer is not zg and anderer.get("passwort", "").strip().lower() == zg["passwort"].lower():
            sys.exit("Dieses Passwort hat schon ein anderer Zugang.")
    speichere(cfg)
    baue(["--neu-verschluesseln"])          # alte Sitzungen auf den Geräten verfallen
    abschluss(f"✅ Neues Passwort für {zg['name']}: {zg['passwort']}",
              "   Der Tresor wurde neu verschlüsselt — auf iPhone/iPad einmal neu anmelden.",
              "   Frühere Stände bleiben in der Git-Historie mit dem alten Passwort lesbar.")


def cmd_zugang(cfg, name):
    name = name.strip()
    if not name:
        sys.exit("Name fehlt.")
    if finde(cfg, name):
        sys.exit(f"Zugang '{name}' existiert schon.")
    pw = neues_passwort(4)
    cfg.setdefault("zugaenge", []).append({"name": name, "passwort": pw})
    speichere(cfg)
    baue()
    abschluss(f"✅ Zugang '{name}' angelegt — Passwort: {pw}")


def cmd_entfernen(cfg, name):
    zg = finde(cfg, name)
    if not zg:
        sys.exit(f"'{name}' nicht gefunden.")
    if len(cfg.get("zugaenge", [])) <= 1:
        sys.exit("Der letzte Zugang lässt sich nicht entfernen.")
    cfg["zugaenge"] = [z for z in cfg["zugaenge"] if z is not zg]
    speichere(cfg)
    baue(["--neu-verschluesseln"])
    abschluss(f"✅ Zugang '{zg['name']}' entfernt — Tresor neu verschlüsselt.")


def main():
    parser = argparse.ArgumentParser(description="Lerndashboards verwalten")
    sub = parser.add_subparsers(dest="befehl", required=True)
    sub.add_parser("liste", help="alle Zugänge anzeigen")
    sub.add_parser("readme", help="Passwort-Übersicht und QR-Code neu schreiben")
    p = sub.add_parser("passwort", help="Passwort neu würfeln")
    p.add_argument("wer", help="Name des Zugangs, z. B. \"Tom\"")
    p = sub.add_parser("setzen", help="eigenes Passwort für einen Zugang setzen")
    p.add_argument("wer", help="Name des Zugangs, z. B. \"Tom\"")
    p.add_argument("passwort", help="das neue Passwort (mindestens 12 Zeichen)")
    p = sub.add_parser("zugang", help="weiteren Zugang anlegen")
    p.add_argument("name", help="Anzeigename, z. B. iPad")
    p = sub.add_parser("entfernen", help="Zugang entfernen")
    p.add_argument("name")
    args = parser.parse_args()

    cfg = lade()
    if args.befehl == "liste":
        cmd_liste(cfg)
    elif args.befehl == "readme":
        schreibe_passwort_readme(cfg)
        print("Passwort-Übersicht und QR-Code geschrieben.")
    elif args.befehl == "passwort":
        cmd_passwort(cfg, args.wer)
    elif args.befehl == "setzen":
        cmd_passwort(cfg, args.wer, args.passwort)
    elif args.befehl == "zugang":
        cmd_zugang(cfg, args.name)
    elif args.befehl == "entfernen":
        cmd_entfernen(cfg, args.name)


if __name__ == "__main__":
    main()
