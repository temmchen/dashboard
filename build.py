#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py — Lerndashboards · Verschlüsselungs-Build
===================================================

Sammelt die Lerndashboards aus OneDrive (`KI/Lerndashboards/`, je Modul eine
einzige HTML-Datei), verschlüsselt jede Datei mit AES-256-GCM und legt nur
Chiffrat unter docs/vaults/ ab. docs/ ist die GitHub-Pages-Wurzel: im
öffentlichen Repo liegt kein Klartext und kein Passwort. Auf dem iPhone/iPad
entschlüsselt die Seite nach der Anmeldung im Browser und zeigt das Dashboard
so, wie es am Mac läuft.

Aufruf:
    /usr/bin/python3 build.py                     normaler (inkrementeller) Build
    /usr/bin/python3 build.py --liste             nur zeigen, was gefunden würde
    /usr/bin/python3 build.py --neu-verschluesseln frischer Tresor-Schlüssel (Schlüsselrotation)

Was aufgenommen wird (Ordner `quelle` aus zugangsdaten.json, ein Unterordner je Modul):
  * Ordner mit `github.json` und Feld `pages`  → nur ein Link (die Seite ist ohnehin
    öffentlich auf GitHub Pages, z. B. Oszilloskop, Kompendium)
  * Ordner mit einer HTML-Datei oben           → verschlüsselt in den Tresor
    (Titel, Klasse, Modul, Stunden/Teile mit Datum aus dem eingebetteten
    <script id="meta"> des Dashboards; Beschreibung aus README.md)
  * Ordner ohne beides, Punkt-/Unterstrich-Ordner, `optionen.ausschliessen` → übersprungen

Krypto-Design (muss zu docs/index.html passen — identisch mit Journal Mobil,
Schuljahr- und CdM-Portal):
  * Schlüsselableitung: PBKDF2-HMAC-SHA256, 600 000 Iterationen, Salt 16 B je Zugang
  * Passwort wird vor der Ableitung normalisiert: NFC, Leerraum an den Enden weg,
    Kleinschreibung (iPhone-Tastaturen schreiben gern groß)
  * Umschlag-Verfahren: EIN zufälliger 256-Bit-Inhaltsschlüssel K für den Tresor;
    K wird für jeden Zugang einzeln "eingewickelt" (AES-GCM über JSON {k, rolle, label})
  * Manifest und Dateien: 12-B-Nonce || AES-256-GCM-Chiffrat (Tag enthalten)
  * Datei-Namen im Repo sind Zufalls-IDs; ändert sich eine Datei, bekommt sie
    eine NEUE ID — so darf das Gerät Dateien dauerhaft zwischenspeichern.

Der Quellordner wird ausschließlich GELESEN.
"""

import argparse
import base64
import datetime
import json
import re
import secrets
import shutil
import sys
import unicodedata
from html import unescape
from pathlib import Path

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    sys.exit("Fehlendes Paket: bitte einmalig  /usr/bin/python3 -m pip install --user cryptography  ausführen.")

HIER = Path(__file__).resolve().parent
DOCS = HIER / "docs"
VAULTS = DOCS / "vaults"
KONFIG = HIER / "zugangsdaten.json"
BUILD_STATE = HIER / ".build-state.json"   # GEHEIM (gitignored): Tresor-Schlüssel + Datei-IDs

PBKDF2_ITER = 600_000
VAULT_NAME = "lerndashboards"               # es gibt genau einen Tresor
PORTAL_ID = "lerndashboards"

# Felder des eingebetteten Dashboard-Metablocks, die das Portal braucht (keine Folieninhalte).
META_FELDER = ("modul", "modulname", "modulcode", "klasse", "schule", "schuljahr", "zeit", "raum",
               "beginn", "ende", "einheit", "kuerzel", "dashTitel", "kurz")
STUNDEN_FELDER = ("nr", "datum", "titel", "untertitel", "kapitel", "meilenstein", "rubrik", "typ", "farbe", "k")
MEILENSTEIN_FELDER = ("id", "datum", "titel", "kurz", "teil", "woche")


# ─────────────────────────── Krypto-Bausteine ───────────────────────────────

def b64(daten: bytes) -> str:
    return base64.b64encode(daten).decode("ascii")


def normalisiere_passwort(passwort) -> str:
    """Wie im Browser (docs/index.html): NFC, Enden trimmen, Kleinschreibung."""
    return unicodedata.normalize("NFC", str(passwort or "")).strip().lower()


def leite_kek_ab(passwort: str, salt: bytes) -> bytes:
    """Key-Encryption-Key aus dem (normalisierten) Passwort ableiten."""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITER)
    return kdf.derive(normalisiere_passwort(passwort).encode("utf-8"))


def verschluessele(key: bytes, klartext: bytes) -> bytes:
    """12-B-Nonce || GCM-Chiffrat — Format für Manifest und Dateien."""
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, klartext, None)


def wickle_ein(kek: bytes, nutzlast: dict) -> dict:
    """Tresor-Schlüssel + Rolleninfo für einen Zugang einwickeln."""
    nonce = secrets.token_bytes(12)
    ct = AESGCM(kek).encrypt(nonce, json.dumps(nutzlast, ensure_ascii=False).encode("utf-8"), None)
    return {"iv": b64(nonce), "ct": b64(ct)}


# ─────────────────────────── Quelle lesen ───────────────────────────────────

def json_lesen(pfad: Path, was: str):
    """JSON lesen; eine vorhandene, aber unlesbare Datei (OneDrive-Sync, Konfliktkopie)
    bricht den Build ab — es soll nie ein halber Stand aufs Gerät."""
    if not pfad.exists():
        return None
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except Exception as ex:
        sys.exit(f"{was} ist nicht lesbar ({pfad}): {ex}\n"
                 f"→ OneDrive fertig synchronisieren lassen, dann erneut veröffentlichen.")


def slug(name: str) -> str:
    """Ordnername → Kennung für Adressen (?d=…): klein, ASCII, Bindestriche."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "eintrag"


def lies_titel(text: str) -> str:
    m = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    return unescape(m.group(1)).strip() if m else ""


def lies_meta(text: str) -> dict:
    """Eingebettete Planung des Dashboards: <script type="application/json" id="meta">."""
    m = re.search(r'<script[^>]*id="meta"[^>]*>\s*(.*?)\s*</script>', text, re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(1))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def lies_praes_meta(text: str) -> dict:
    """<meta name="praes:klasse" content="…"> (ältere Präsentationen)."""
    aus = {}
    for name, inhalt in re.findall(r'<meta\s+name="praes:([a-z]+)"\s+content="([^"]*)"', text, re.I):
        aus[name.lower()] = unescape(inhalt).strip()
    return aus


def erster_absatz(readme: Path) -> str:
    """Erster Textabsatz der README (ohne Überschrift, Markdown grob entfernt)."""
    if not readme.is_file():
        return ""
    absatz = []
    for zeile in readme.read_text(encoding="utf-8", errors="replace").splitlines():
        z = zeile.strip()
        if not z or z.startswith("#"):
            if absatz:
                break
            continue
        if z.startswith(("|", "-", "*", ">", "```")):
            if absatz:
                break
            continue
        absatz.append(z)
    text = " ".join(absatz)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)      # Links → Linktext
    text = re.sub(r"[*`]+", "", text)                            # fett/kursiv/Code (Unterstriche in Namen bleiben)
    return text.strip()


def nur_felder(d: dict, felder) -> dict:
    return {k: d[k] for k in felder if k in d and d[k] not in (None, "", [])}


def sammle(cfg: dict):
    """Alles einsammeln, was ins Manifest kommt. Dateien werden noch nicht gelesen —
    nur als (Schlüssel, Pfad, Eintrag) gemerkt; das Verschlüsseln übernimmt der Build."""
    quelle = Path(cfg["quelle"]).expanduser()
    if not quelle.is_dir():
        sys.exit(f"Quellordner fehlt: {quelle}")
    opt = cfg.get("optionen") or {}
    max_bytes = int(float(opt.get("max_mb_je_datei", 40)) * 1024 * 1024)
    ausschliessen = {str(a).strip().lower() for a in (opt.get("ausschliessen") or [])}

    eintraege = []
    dateien = []            # [(schluessel, Path, eintrag_dict)] — eintrag_dict bekommt fid
    uebersprungen = []
    for ordner in sorted(p for p in quelle.iterdir() if p.is_dir()):
        if ordner.name.startswith((".", "_")) or ordner.name.lower() in ausschliessen:
            continue
        gh = json_lesen(ordner / "github.json", "github.json")
        if isinstance(gh, dict) and gh.get("pages") and not gh.get("verschluesselt"):
            # Öffentliche Lernseite: nur verlinken, nichts verschlüsseln. (Eine github.json mit
            # "verschluesselt": true zeigt nur auf dieses Portal – der Ordner kommt in den Tresor.)
            eintraege.append({
                "typ": "link", "id": slug(ordner.name), "ordner": ordner.name,
                "titel": gh.get("titel") or ordner.name,
                "klasse": gh.get("klasse") or "", "modul": gh.get("modul") or "",
                "art": gh.get("typ") or "", "url": gh["pages"],
                "farben": gh.get("farben") if isinstance(gh.get("farben"), list) else [],
            })
            continue
        htmls = sorted(p for p in ordner.glob("*.html") if p.is_file() and not p.name.startswith("."))
        if not htmls:
            uebersprungen.append(f"{ordner.name} (keine HTML-Datei oben im Ordner)")
            continue
        html = htmls[0]
        if len(htmls) > 1:
            uebersprungen.append(f"{ordner.name}: {len(htmls) - 1} weitere HTML-Datei(en) ignoriert, genommen: {html.name}")
        text = html.read_text(encoding="utf-8", errors="replace")
        meta = lies_meta(text)
        praes = lies_praes_meta(text)
        stunden = [nur_felder(s, STUNDEN_FELDER) for s in (meta.get("stunden") or []) if isinstance(s, dict)]
        meilensteine = [nur_felder(m, MEILENSTEIN_FELDER) for m in (meta.get("meilensteine") or []) if isinstance(m, dict)]
        farbe = ""
        for s in stunden:
            if s.get("farbe"):
                farbe = s["farbe"]
                break
        e = {
            "typ": "tresor", "id": slug(ordner.name), "ordner": ordner.name, "datei": html.name,
            "titel": meta.get("dashTitel") or lies_titel(text) or html.stem,
            "klasse": meta.get("klasse") or praes.get("klasse") or "",
            "modul": meta.get("modul") or praes.get("fach") or "",
            "farbe": farbe,
            "meta": nur_felder(meta, META_FELDER),
            "stunden": stunden,
            "meilensteine": meilensteine,
            "beschreibung": erster_absatz(ordner / "README.md"),
            "fid": None, "groesse": 0, "geaendert": "",
        }
        st = html.stat()
        if st.st_size > max_bytes:
            e["hinweis"] = "zu groß fürs Handy"
            uebersprungen.append(f"{ordner.name}/{html.name} (> {max_bytes // 1048576} MB)")
            eintraege.append(e)
            continue
        dateien.append((f"{ordner.name}/{html.name}", html, e))
        eintraege.append(e)

    manifest = {
        "v": 1,
        "portal": PORTAL_ID,
        "schuljahr": cfg.get("schuljahr") or "",
        "eintraege": eintraege,
    }
    return manifest, dateien, uebersprungen


# ─────────────────────────── Haupt-Build ────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Lerndashboards verschlüsselt bauen")
    parser.add_argument("--liste", action="store_true", help="nur zeigen, was gefunden würde (kein Build)")
    parser.add_argument("--neu-verschluesseln", action="store_true",
                        help="Tresor mit frischem Schlüssel und frischen IDs neu aufbauen "
                             "(echte Schlüsselrotation; alte Sitzungen auf den Geräten verfallen)")
    args = parser.parse_args()

    if not KONFIG.is_file():
        sys.exit("zugangsdaten.json fehlt — Vorlage: zugangsdaten.beispiel.json")
    cfg = json.loads(KONFIG.read_text(encoding="utf-8"))
    quelle = Path(cfg["quelle"]).expanduser()
    print(f"Quelle: {quelle}")

    manifest, dateien, uebersprungen = sammle(cfg)
    if args.liste:
        for e in manifest["eintraege"]:
            if e["typ"] == "link":
                print(f"  🔗 {e['id']:40s} {e['titel']}  →  {e['url']}")
            else:
                einheit = e["meta"].get("einheit", "Stunde")
                mehrzahl = {"Stunde": "Stunden", "Teil": "Teile"}.get(einheit, einheit + "n")
                print(f"  🔒 {e['id']:40s} {e['titel']}  ({e['ordner']}/{e['datei']}, "
                      f"{len(e['stunden'])} {mehrzahl})")
        for u in uebersprungen:
            print(f"  – übersprungen: {u}")
        return

    # ── Zugänge (Principals) + Passwörter prüfen ──
    zugaenge = cfg.get("zugaenge") or []
    if not zugaenge:
        sys.exit("zugangsdaten.json braucht mindestens einen Zugang unter \"zugaenge\".")
    principals = []
    gesehen = []
    print("Zugänge:")
    for i, z in enumerate(zugaenge):
        passwort = normalisiere_passwort(z.get("passwort"))
        label = z.get("name") or f"Zugang {i + 1}"
        if len(passwort) < 8:
            sys.exit(f"Passwort für '{label}' fehlt oder ist kürzer als 8 Zeichen.")
        if passwort in gesehen:
            sys.exit(f"Passwort für '{label}' ist doppelt vergeben.")
        gesehen.append(passwort)
        salt = secrets.token_bytes(16)
        pid = f"p{i}"
        print(f"  · {pid}: {label} — leite Schlüssel ab …")
        principals.append({"id": pid, "salt": salt, "kek": leite_kek_ab(passwort, salt),
                           "label": label, "rolle": "leser"})

    # ── Tresor (inkrementell) ──
    frisch = bool(args.neu_verschluesseln)
    if frisch and VAULTS.exists():
        shutil.rmtree(VAULTS)
    VAULTS.mkdir(parents=True, exist_ok=True)

    alt = {"vaults": {}, "dateien": {}}
    if not frisch:
        try:
            d = json.loads(BUILD_STATE.read_text(encoding="utf-8"))
            alt = {"vaults": d.get("vaults", {}), "dateien": d.get("dateien", {})}
        except Exception:
            pass
    if frisch:
        print("🔄 Neuverschlüsselung: der Tresor bekommt einen frischen Schlüssel.")

    vorher = alt["vaults"].get(VAULT_NAME)
    if vorher:
        vid = vorher["id"]
        k_vault = base64.b64decode(vorher["key"])
    else:
        vid = secrets.token_hex(8)
        k_vault = secrets.token_bytes(32)
    neu = {"vaults": {VAULT_NAME: {"id": vid, "key": b64(k_vault)}}, "dateien": {}}

    vdir = VAULTS / vid
    (vdir / "f").mkdir(parents=True, exist_ok=True)
    behalten = set()
    zaehler = {"neu": 0, "wiederverwendet": 0}
    gesamt = 0
    for schluessel, quelle_datei, ziel in dateien:
        st = quelle_datei.stat()
        vorher_d = alt["dateien"].get(schluessel)
        unveraendert = (vorher_d
                        and vorher_d.get("size") == st.st_size
                        and int(vorher_d.get("mtime", -1)) == int(st.st_mtime)
                        and (vdir / "f" / f"{vorher_d['fid']}.enc").exists())
        if unveraendert:
            fid = vorher_d["fid"]                       # Chiffrat bleibt Byte-gleich
            zaehler["wiederverwendet"] += 1
        else:
            # Geänderte Datei → NEUE Kennung, damit ein alter Cache auf dem Gerät
            # nie ein veraltetes Chiffrat für die neue Fassung hält.
            fid = secrets.token_hex(12)
            (vdir / "f" / f"{fid}.enc").write_bytes(verschluessele(k_vault, quelle_datei.read_bytes()))
            zaehler["neu"] += 1
        neu["dateien"][schluessel] = {"fid": fid, "size": st.st_size, "mtime": int(st.st_mtime)}
        behalten.add(f"{fid}.enc")
        ziel["fid"] = fid
        ziel["groesse"] = st.st_size
        ziel["geaendert"] = datetime.datetime.fromtimestamp(st.st_mtime).replace(microsecond=0).isoformat()
        gesamt += st.st_size
        if st.st_size > 95 * 1024 * 1024:
            print(f"  ⚠️  {quelle_datei.name}: über 95 MB — GitHub-Limit ist 100 MB/Datei!")

    for veraltet in (vdir / "f").iterdir():             # gelöschte oder ersetzte Dateien aufräumen
        if veraltet.name not in behalten:
            veraltet.unlink()
    for anderer in VAULTS.iterdir():                     # fremde Tresore (alte IDs) entfernen
        if anderer.is_dir() and anderer.name != vid:
            shutil.rmtree(anderer)

    build_id = secrets.token_hex(6)
    jetzt = datetime.datetime.now().replace(microsecond=0).isoformat()
    manifest["erstellt"] = jetzt
    manifest["build"] = build_id
    manifest["statistik"] = {
        "dashboards": sum(1 for e in manifest["eintraege"] if e["typ"] == "tresor" and e.get("fid")),
        "links": sum(1 for e in manifest["eintraege"] if e["typ"] == "link"),
        "bytes": gesamt,
        "uebersprungen": uebersprungen,
    }
    (vdir / "m.enc").write_bytes(
        verschluessele(k_vault, json.dumps(manifest, ensure_ascii=False).encode("utf-8")))

    wraps = []
    for pr in principals:
        w = wickle_ein(pr["kek"], {"k": b64(k_vault), "rolle": pr["rolle"], "label": pr["label"]})
        w["p"] = pr["id"]
        wraps.append(w)

    index = {
        "v": 1,
        "portal": PORTAL_ID,
        "schuljahr": cfg.get("schuljahr") or "",
        "erstellt": jetzt,
        "build": build_id,
        "kdf": {"typ": "PBKDF2-SHA256", "iter": PBKDF2_ITER, "normalisierung": "nfc+trim+lower"},
        "principals": [{"id": p["id"], "salt": b64(p["salt"])} for p in principals],
        "vaults": [{"id": vid, "wraps": wraps, "manifest": f"vaults/{vid}/m.enc"}],
    }
    (VAULTS / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    (DOCS / ".nojekyll").write_text("")
    BUILD_STATE.write_text(json.dumps(neu, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── Zusammenfassung ──
    st = manifest["statistik"]
    print(f"\nVerschlüsselt: {zaehler['neu']} Datei(en) neu, "
          f"{zaehler['wiederverwendet']} unverändert übernommen.")
    print(f"Inhalt: {st['dashboards']} Dashboards im Tresor · {st['links']} öffentliche Links · "
          f"{gesamt / 1024 / 1024:.1f} MiB")
    for e in manifest["eintraege"]:
        if e["typ"] == "tresor":
            print(f"  🔒 {e['id']}  →  {e['titel']}  ({e['groesse'] / 1024 / 1024:.1f} MiB)")
        else:
            print(f"  🔗 {e['id']}  →  {e['titel']}")
    if uebersprungen:
        print(f"Übersprungen ({len(uebersprungen)}):")
        for u in uebersprungen:
            print(f"  – {u}")
    print("Fertig. → docs/ committen und pushen, Passwörter bleiben lokal.")


if __name__ == "__main__":
    main()
