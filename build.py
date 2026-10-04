#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py — Dashboard Mobil · Verschlüsselungs-Build
====================================================

Baut die iPhone/iPad-Fassung des Dashboards: sammelt aus OneDrive die
**Lerndashboards** (`KI/Lerndashboards/`), die **Präsentationen** (`KI/Keynotes/`)
und die **Simulationen** (`KI/Simulations/`), holt die Liste aller eigenen
**GitHub-Repositories** (öffentlich und privat, über `gh`), verschlüsselt alles
mit AES-256-GCM und legt nur Chiffrat unter docs/vaults/ ab. docs/ ist die
GitHub-Pages-Wurzel: im öffentlichen Repo liegt kein Klartext und kein Passwort.

Aufruf:
    /usr/bin/python3 build.py                      normaler (inkrementeller) Build
    /usr/bin/python3 build.py --liste              nur zeigen, was gefunden würde
    /usr/bin/python3 build.py --ohne-repos         GitHub nicht abfragen (alte Liste behalten)
    /usr/bin/python3 build.py --neu-verschluesseln frischer Tresor-Schlüssel (Schlüsselrotation)

Was aufgenommen wird (`quellen` in zugangsdaten.json):
  * Lerndashboards: je Unterordner die HTML-Datei oben (Titel, Klasse, Stunden aus dem
    eingebetteten <script id="meta">); Ordner mit `github.json` + `pages` nur als Link.
  * Präsentationen (Keynotes): je Unterordner die HTML-Datei oben (eine Datei, Filme sind
    eingebaut); Beschreibung aus README.md, Klassen aus zuordnung.json.
  * Simulationen: jede HTML-Seite im Baum Jahr › Klasse › Fach › Thema (ohne `_`-Seiten,
    ohne build/, Quellcode/ usw.). Verweist eine Seite auf Dateien neben sich (css/, js/ …),
    kommt ihr ganzer Ordner mit – der Service Worker der Seite liefert ihn entschlüsselt aus.
  * Repos: `gh api user/repos` (alle eigenen, auch private), Pages-Adresse nach Konvention
    https://<benutzer>.github.io/<repo>/, QR-Code als Modulraster.

Krypto-Design (muss zu docs/index.html und docs/sw.js passen — wie Journal Mobil,
Schuljahr- und CdM-Portal):
  * Schlüsselableitung: PBKDF2-HMAC-SHA256, 600 000 Iterationen, Salt 16 B je Zugang
  * Passwort vor der Ableitung normalisiert: NFC, Enden getrimmt, Kleinschreibung
  * Umschlag-Verfahren: EIN zufälliger 256-Bit-Inhaltsschlüssel K für den Tresor;
    K wird für jeden Zugang einzeln "eingewickelt" (AES-GCM über JSON {k, rolle, label})
  * Manifest und Dateien: 12-B-Nonce || AES-256-GCM-Chiffrat (Tag enthalten)
  * Datei-Namen im Repo sind Zufalls-IDs; ändert sich eine Datei, bekommt sie eine NEUE ID

Die Quellordner werden ausschließlich GELESEN.
"""

import argparse
import base64
import datetime
import json
import re
import secrets
import shutil
import subprocess
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
BUILD_STATE = HIER / ".build-state.json"   # GEHEIM (gitignored): Tresor-Schlüssel + Datei-IDs + letzte Repo-Liste

PBKDF2_ITER = 600_000
VAULT_NAME = "dashboard"                    # es gibt genau einen Tresor
PORTAL_ID = "dashboard-mobil"
BEREICHE = ("lerndashboards", "praesentationen", "simulationen")

# Felder des eingebetteten Dashboard-Metablocks, die das Portal braucht (keine Folieninhalte).
META_FELDER = ("modul", "modulname", "modulcode", "klasse", "schule", "schuljahr", "zeit", "raum",
               "beginn", "ende", "einheit", "kuerzel", "dashTitel", "kurz")
STUNDEN_FELDER = ("nr", "datum", "titel", "untertitel", "kapitel", "meilenstein", "rubrik", "typ", "farbe", "k")
MEILENSTEIN_FELDER = ("id", "datum", "titel", "kurz", "teil", "woche")

# Dateien, die bei mehrteiligen Einträgen (Simulationen mit css/, js/ …) mitkommen.
MITNEHMEN = {"html", "htm", "js", "mjs", "css", "json", "svg", "png", "jpg", "jpeg", "gif", "webp", "ico",
             "woff", "woff2", "ttf", "otf", "mp4", "webm", "mp3", "m4a", "wav", "vtt", "pdf", "txt", "md", "csv", "xml"}
IGNORIERTE_ORDNER = {"build", "quellcode", ".claude", ".git", "node_modules", "__pycache__", "pruefbilder", "pruefbild"}
KLASSEN_MUSTER = [r"DP ?[1-4] ?[A-Z]{2}", r"[1-7] ?G[A-Z]{2,3} ?[A-Z]?", r"Module ?[FM]"]
FACH_MUSTER = [r"ELTEC ?\d{1,2}", r"MINT ?\d{1,2}", r"DITEC ?\d{1,2}", r"PRODI ?\d{1,2}", r"ELETE", r"TPELE", r"OPXX ?\d?"]
EINHEIT_MUSTER = re.compile(r"^(Session|Woche|Stunde|Kapitel|Teil|Block|Einheit)\s*\d+", re.I)


# ─────────────────────────── Krypto-Bausteine ───────────────────────────────

def b64(daten: bytes) -> str:
    return base64.b64encode(daten).decode("ascii")


def normalisiere_passwort(passwort) -> str:
    """Wie im Browser (docs/index.html): NFC, Enden trimmen, Kleinschreibung."""
    return unicodedata.normalize("NFC", str(passwort or "")).strip().lower()


def leite_kek_ab(passwort: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITER)
    return kdf.derive(normalisiere_passwort(passwort).encode("utf-8"))


def verschluessele(key: bytes, klartext: bytes) -> bytes:
    """12-B-Nonce || GCM-Chiffrat — Format für Manifest und Dateien."""
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, klartext, None)


def wickle_ein(kek: bytes, nutzlast: dict) -> dict:
    nonce = secrets.token_bytes(12)
    ct = AESGCM(kek).encrypt(nonce, json.dumps(nutzlast, ensure_ascii=False).encode("utf-8"), None)
    return {"iv": b64(nonce), "ct": b64(ct)}


# ─────────────────────────── Hilfen zum Lesen ───────────────────────────────

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
    """Name → Kennung für Adressen (?d=…, d/<id>/…): klein, ASCII, Bindestriche."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "eintrag"


def lies_titel(text: str) -> str:
    m = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    return unescape(m.group(1)).strip() if m else ""


def lies_meta(text: str) -> dict:
    """Eingebettete Planung eines Lerndashboards: <script type="application/json" id="meta">."""
    m = re.search(r'<script[^>]*id="meta"[^>]*>\s*(.*?)\s*</script>', text, re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(1))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def lies_meta_tags(text: str, praefix: str) -> dict:
    """<meta name="praes:klasse" content="…"> bzw. sim:… (Präsentationen, Simulationen)."""
    aus = {}
    for name, inhalt in re.findall(r'<meta\s+name="' + re.escape(praefix) + r':([a-z]+)"\s+content="([^"]*)"', text, re.I):
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


VERWEIS = re.compile(r"""(?:src|href|poster)\s*=\s*["']([^"'#?][^"']*)["']""", re.I)


def hat_relative_verweise(text: str) -> bool:
    """Lädt die Seite Dateien neben sich (css/, js/, Bilder)? Dann muss der Ordner mit."""
    for ziel in VERWEIS.findall(text):
        z = ziel.strip()
        if not z or z.startswith(("data:", "//", "#", "javascript:", "mailto:", "tel:")):
            continue
        if re.match(r"^[a-z][a-z0-9+.\-]*:", z, re.I):          # http:, https:, blob: …
            continue
        return True
    return False


def dateien_im_ordner(wurzel: Path, max_bytes: int):
    """Alle mitzunehmenden Dateien unter `wurzel` → [(rel, Path)], Übersprungenes als Liste."""
    aus, uebersprungen = [], []
    for p in sorted(wurzel.rglob("*")):
        if not p.is_file():
            continue
        rel_teile = p.relative_to(wurzel).parts
        if any(t.startswith(".") or t.lower() in IGNORIERTE_ORDNER for t in rel_teile[:-1]):
            continue
        name = p.name
        if name.startswith(".") or ".bak" in name or name.endswith("~"):
            continue
        if p.suffix.lstrip(".").lower() not in MITNEHMEN:
            continue
        if p.stat().st_size > max_bytes:
            uebersprungen.append(f"{p.relative_to(wurzel).as_posix()} (> {max_bytes // 1048576} MB)")
            continue
        aus.append((p.relative_to(wurzel).as_posix(), p))
    return aus, uebersprungen


def neuer_eintrag(bereich: str, kennung: str, titel: str) -> dict:
    return {"typ": "tresor", "bereich": bereich, "id": kennung, "titel": titel,
            "beschreibung": "", "klasse": "", "klassen": [], "modul": "", "fach": "", "jahr": "", "thema": "",
            "einheit": "", "datum": "", "farbe": "", "start": "", "dateien": {}, "mehrteilig": False,
            "groesse": 0, "geaendert": ""}


def quellen(cfg: dict) -> dict:
    """{bereich: Path} aus zugangsdaten.json (`quellen`; Altform `quelle` = Lerndashboards)."""
    q = cfg.get("quellen") or {}
    if not q and cfg.get("quelle"):
        q = {"lerndashboards": cfg["quelle"]}
    return {b: Path(p).expanduser() for b, p in q.items() if b in BEREICHE and p}


# ─────────────────────────── Lerndashboards ─────────────────────────────────

def sammle_lerndashboards(quelle: Path, max_bytes: int, ausschliessen: set):
    eintraege, jobs, uebersprungen = [], [], []
    for ordner in sorted(p for p in quelle.iterdir() if p.is_dir()):
        if ordner.name.startswith((".", "_")) or ordner.name.lower() in ausschliessen:
            continue
        gh = json_lesen(ordner / "github.json", "github.json")
        if isinstance(gh, dict) and gh.get("pages") and not gh.get("verschluesselt"):
            eintraege.append({
                "typ": "link", "bereich": "lerndashboards", "id": slug(ordner.name), "ordner": ordner.name,
                "titel": gh.get("titel") or ordner.name,
                "klasse": gh.get("klasse") or "", "modul": gh.get("modul") or "",
                "art": gh.get("typ") or "", "url": gh["pages"],
                "farben": gh.get("farben") if isinstance(gh.get("farben"), list) else [],
            })
            continue
        htmls = sorted(p for p in ordner.glob("*.html") if p.is_file() and not p.name.startswith("."))
        if not htmls:
            uebersprungen.append(f"Lerndashboards/{ordner.name} (keine HTML-Datei oben im Ordner)")
            continue
        html = htmls[0]
        text = html.read_text(encoding="utf-8", errors="replace")
        meta = lies_meta(text)
        praes = lies_meta_tags(text, "praes")
        stunden = [nur_felder(s, STUNDEN_FELDER) for s in (meta.get("stunden") or []) if isinstance(s, dict)]
        meilensteine = [nur_felder(m, MEILENSTEIN_FELDER) for m in (meta.get("meilensteine") or []) if isinstance(m, dict)]
        e = neuer_eintrag("lerndashboards", slug(ordner.name), meta.get("dashTitel") or lies_titel(text) or html.stem)
        e.update({
            "ordner": ordner.name,
            "klasse": meta.get("klasse") or praes.get("klasse") or "",
            "modul": meta.get("modul") or praes.get("fach") or "",
            "farbe": next((s["farbe"] for s in stunden if s.get("farbe")), ""),
            "meta": nur_felder(meta, META_FELDER),
            "stunden": stunden, "meilensteine": meilensteine,
            "beschreibung": erster_absatz(ordner / "README.md"),
            "start": html.name,
        })
        if html.stat().st_size > max_bytes:
            e["hinweis"] = "zu groß fürs Handy"
            uebersprungen.append(f"Lerndashboards/{ordner.name}/{html.name} (> {max_bytes // 1048576} MB)")
        else:
            jobs.append((f"lerndashboards/{ordner.name}/{html.name}", html, e, html.name))
        eintraege.append(e)
    return eintraege, jobs, uebersprungen


# ─────────────────────────── Präsentationen ─────────────────────────────────

def sammle_praesentationen(quelle: Path, max_bytes: int, ausschliessen: set):
    eintraege, jobs, uebersprungen = [], [], []
    for ordner in sorted(p for p in quelle.iterdir() if p.is_dir()):
        if ordner.name.startswith((".", "_")) or ordner.name.lower() in ausschliessen:
            continue
        htmls = sorted(p for p in ordner.glob("*.html") if p.is_file() and not p.name.startswith("."))
        if not htmls:
            uebersprungen.append(f"Keynotes/{ordner.name} (keine HTML-Datei oben im Ordner)")
            continue
        html = htmls[0]
        text = html.read_text(encoding="utf-8", errors="replace")
        praes = lies_meta_tags(text, "praes")
        zuo = json_lesen(ordner / "zuordnung.json", "zuordnung.json") or {}
        klassen = [k for k in (zuo.get("klassen") or []) if isinstance(k, str)]
        module = zuo.get("module") if isinstance(zuo.get("module"), dict) else {}
        titel = lies_titel(text) or ordner.name
        titel = re.sub(r"\s*·\s*Tom Bleyer\s*$", "", titel)
        e = neuer_eintrag("praesentationen", slug(ordner.name), titel)
        e.update({
            "ordner": ordner.name,
            "klasse": praes.get("klasse") or (klassen[0] if klassen else ""),
            "klassen": klassen, "module": module,
            "modul": praes.get("fach") or "",
            "folien": len(re.findall(r"<section[^>]*class=\"slide", text)),
            "filme": len(re.findall(r"KI\.film\(", text)),
            "beschreibung": erster_absatz(ordner / "README.md"),
            "start": html.name,
            "farbe": "#ec4899",
        })
        if html.stat().st_size > max_bytes:
            e["hinweis"] = "zu groß fürs Handy"
            uebersprungen.append(f"Keynotes/{ordner.name}/{html.name} (> {max_bytes // 1048576} MB)")
        else:
            jobs.append((f"praesentationen/{ordner.name}/{html.name}", html, e, html.name))
        eintraege.append(e)
    return eintraege, jobs, uebersprungen


# ─────────────────────────── Simulationen ───────────────────────────────────

def jahr_aus(text: str) -> str:
    m = re.match(r"^(\d{4})[ _\-/]?(\d{4}|\d{2})$", text.strip())
    if not m:
        return ""
    b = m.group(2)
    if len(b) == 2:
        b = m.group(1)[:2] + b
    return f"{m.group(1)}-{b}"


def erstes_muster(muster, text: str) -> str:
    for mu in muster:
        m = re.search(mu, text, re.I)
        if m:
            return re.sub(r"\s+", "", m.group(0)).upper()
    return ""


def sammle_simulationen(quelle: Path, max_bytes: int, ausschliessen: set):
    eintraege, jobs, uebersprungen = [], [], []
    for html in sorted(quelle.rglob("*.html")):
        rel_teile = html.relative_to(quelle).parts
        if any(t.startswith(".") or t.lower() in IGNORIERTE_ORDNER for t in rel_teile[:-1]):
            continue
        if html.name.startswith(("_", ".")) or ".bak" in html.name:
            continue
        if any(t.lower() in ausschliessen for t in rel_teile):
            continue
        text = html.read_text(encoding="utf-8", errors="replace")
        sim = lies_meta_tags(text, "sim")
        ordner_teile = list(rel_teile[:-1])
        jahr, klasse, fach, thema, einheit = "", "", "", "", ""
        rest = []
        for t in ordner_teile:
            if not jahr and jahr_aus(t):
                jahr = jahr_aus(t)
            elif not klasse and erstes_muster(KLASSEN_MUSTER, t) and len(t) <= 10:
                klasse = erstes_muster(KLASSEN_MUSTER, t)
            elif not fach and erstes_muster(FACH_MUSTER, t) and len(t) <= 10:
                fach = erstes_muster(FACH_MUSTER, t)
            elif EINHEIT_MUSTER.match(t):
                einheit = t
            else:
                rest.append(re.sub(r"\s+", " ", t).strip())
        if rest:
            thema = rest[0]
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", html.name)
        datum = m.group(1) if m else ""
        titel = lies_titel(text) or html.stem.replace("_", " ")
        kennung = slug("-".join(list(rel_teile[:-1]) + [html.stem]))
        e = neuer_eintrag("simulationen", kennung, titel)
        e.update({
            "pfad": html.relative_to(quelle).as_posix(),
            "jahr": sim.get("jahr") or jahr, "klasse": sim.get("klasse") or klasse,
            "fach": sim.get("fach") or fach, "thema": sim.get("thema") or thema,
            "einheit": sim.get("einheit") or einheit, "datum": datum,
            "art": sim.get("typ") or "simulation",
            "beschreibung": (re.search(r'<meta\s+name="description"\s+content="([^"]*)"', text, re.I) or [None, ""])[1],
            "start": html.name, "farbe": "#14b8a6",
        })
        if hat_relative_verweise(text):
            e["mehrteilig"] = True
            dateien, zu_gross = dateien_im_ordner(html.parent, max_bytes)
            uebersprungen.extend(f"Simulations/{html.parent.relative_to(quelle).as_posix()}/{u}" for u in zu_gross)
            if not any(r == html.name for r, _ in dateien):
                e["hinweis"] = "zu groß fürs Handy"
                uebersprungen.append(f"Simulations/{e['pfad']} (> {max_bytes // 1048576} MB)")
            for rel, p in dateien:
                jobs.append((f"simulationen/{html.parent.relative_to(quelle).as_posix()}/{rel}", p, e, rel))
        elif html.stat().st_size > max_bytes:
            e["hinweis"] = "zu groß fürs Handy"
            uebersprungen.append(f"Simulations/{e['pfad']} (> {max_bytes // 1048576} MB)")
        else:
            jobs.append((f"simulationen/{e['pfad']}", html, e, html.name))
        eintraege.append(e)
    eintraege.sort(key=lambda x: (x.get("jahr") or "", x.get("klasse") or "", x.get("fach") or "", x.get("thema") or "", x.get("einheit") or "", x.get("datum") or "", x["titel"]))
    return eintraege, jobs, uebersprungen


# ─────────────────────────── Repos (GitHub) ─────────────────────────────────

def qr_raster(text: str):
    """QR-Code als Zeilen aus 0/1 (ohne Rand); None, wenn das Modul qrcode fehlt."""
    try:
        import qrcode
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
        qr.add_data(text)
        qr.make(fit=True)
        return ["".join("1" if z else "0" for z in zeile) for zeile in qr.get_matrix()]
    except Exception:
        return None


def repos_roh():
    """Alle eigenen Repos über gh (eine Zeile JSON je Repo); None bei Fehler."""
    felder = "{name,private,has_pages,archived,fork,language,topics,pushed_at,created_at,html_url,homepage,size,description}"
    try:
        r = subprocess.run(["gh", "api", "--paginate", "user/repos?affiliation=owner&per_page=100",
                            "--jq", ".[] | " + felder], capture_output=True, text=True, timeout=90)
    except Exception as ex:
        return None, f"gh nicht ausführbar: {ex}"
    if r.returncode != 0:
        return None, (r.stderr.strip().splitlines() or ["gh api fehlgeschlagen"])[-1]
    liste = []
    for zeile in r.stdout.splitlines():
        zeile = zeile.strip()
        if zeile:
            try:
                liste.append(json.loads(zeile))
            except Exception:
                pass
    return liste, ""


def repos_signatur():
    """Kurze Signatur der Repo-Liste für veroeffentlichen.py (None bei Fehler)."""
    roh, fehler = repos_roh()
    if roh is None:
        return None
    return sorted([r.get("name", ""), r.get("pushed_at", ""), bool(r.get("private")), bool(r.get("has_pages"))] for r in roh)


def sammle_repos(cfg_repos: dict, alt: dict, ohne_abfrage: bool):
    benutzer = cfg_repos.get("benutzer") or "temmchen"
    portale = {p.lower() for p in (cfg_repos.get("portale") or [])}
    keine_sim = {p.lower() for p in (cfg_repos.get("keine_simulation") or [])}
    roh, fehler = (None, "nicht abgefragt (--ohne-repos)") if ohne_abfrage else repos_roh()
    if roh is None:
        alt_liste = (alt or {}).get("liste") or []
        print(f"  ⚠️  Repo-Liste: {fehler} — behalte die letzte Liste ({len(alt_liste)} Repos).")
        aus = dict(alt or {})
        aus["fehler"] = fehler
        aus.setdefault("liste", [])
        aus.setdefault("stand", "")
        aus["benutzer"] = benutzer
        aus["schueler_apps"] = schueler_apps(cfg_repos)
        return aus
    liste = []
    for r in roh:
        name = r.get("name") or ""
        if not name:
            continue
        pages = ""
        if r.get("has_pages"):
            pages = f"https://{benutzer}.github.io/" if name.lower() == f"{benutzer}.github.io" else f"https://{benutzer}.github.io/{name}/"
        privat = bool(r.get("private"))
        eintrag = {
            "name": name, "beschreibung": r.get("description") or "", "privat": privat,
            "pages": pages, "url": r.get("html_url") or f"https://github.com/{benutzer}/{name}",
            "homepage": r.get("homepage") or "", "gepusht": r.get("pushed_at") or "", "erstellt": r.get("created_at") or "",
            "sprache": r.get("language") or "", "topics": [t for t in (r.get("topics") or []) if isinstance(t, str)],
            "archiviert": bool(r.get("archived")), "fork": bool(r.get("fork")), "groesse_kb": int(r.get("size") or 0),
            "portal": name.lower() in portale,
            "simulation": bool(pages) and not privat and name.lower() not in portale and name.lower() not in keine_sim,
        }
        if pages:
            eintrag["qr"] = qr_raster(pages)
        liste.append(eintrag)
    liste.sort(key=lambda x: x["gepusht"], reverse=True)
    return {"benutzer": benutzer, "stand": datetime.datetime.now().replace(microsecond=0).isoformat(),
            "liste": liste, "fehler": "", "schueler_apps": schueler_apps(cfg_repos)}


def schueler_apps(cfg_repos: dict):
    aus = []
    for a in cfg_repos.get("schueler_apps") or []:
        if isinstance(a, dict) and a.get("adresse"):
            aus.append({"titel": a.get("titel") or a["adresse"], "adresse": a["adresse"], "qr": qr_raster(a["adresse"])})
    return aus


# ─────────────────────────── Alles einsammeln ───────────────────────────────

def sammle(cfg: dict):
    """Alle Bereiche einsammeln. Dateien werden noch nicht gelesen — nur als
    (Schlüssel, Pfad, Eintrag, rel) gemerkt; das Verschlüsseln übernimmt der Build."""
    opt = cfg.get("optionen") or {}
    max_bytes = int(float(opt.get("max_mb_je_datei", 40)) * 1024 * 1024)
    ausschliessen = {str(a).strip().lower() for a in (opt.get("ausschliessen") or [])}
    bereiche = {b: [] for b in BEREICHE}
    jobs, uebersprungen = [], []
    for bereich, pfad in quellen(cfg).items():
        if not pfad.is_dir():
            uebersprungen.append(f"{bereich}: Quellordner fehlt ({pfad})")
            continue
        fn = {"lerndashboards": sammle_lerndashboards, "praesentationen": sammle_praesentationen,
              "simulationen": sammle_simulationen}[bereich]
        e, j, u = fn(pfad, max_bytes, ausschliessen)
        bereiche[bereich] = e
        jobs.extend(j)
        uebersprungen.extend(u)
    manifest = {"v": 2, "portal": PORTAL_ID, "schuljahr": cfg.get("schuljahr") or "", "bereiche": bereiche}
    return manifest, jobs, uebersprungen


# ─────────────────────────── Haupt-Build ────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Dashboard Mobil verschlüsselt bauen")
    parser.add_argument("--liste", action="store_true", help="nur zeigen, was gefunden würde (kein Build)")
    parser.add_argument("--ohne-repos", action="store_true", help="GitHub nicht abfragen, letzte Repo-Liste behalten")
    parser.add_argument("--neu-verschluesseln", action="store_true",
                        help="Tresor mit frischem Schlüssel und frischen IDs neu aufbauen "
                             "(echte Schlüsselrotation; alte Sitzungen auf den Geräten verfallen)")
    args = parser.parse_args()

    if not KONFIG.is_file():
        sys.exit("zugangsdaten.json fehlt — Vorlage: zugangsdaten.beispiel.json")
    cfg = json.loads(KONFIG.read_text(encoding="utf-8"))
    for b, p in quellen(cfg).items():
        print(f"Quelle {b}: {p}")

    manifest, jobs, uebersprungen = sammle(cfg)
    if args.liste:
        for b in BEREICHE:
            print(f"\n[{b}]")
            for e in manifest["bereiche"][b]:
                if e["typ"] == "link":
                    print(f"  🔗 {e['id']:44s} {e['titel']}  →  {e['url']}")
                else:
                    n = sum(1 for j in jobs if j[2] is e)
                    print(f"  🔒 {e['id']:44s} {e['titel']}  ({n} Datei{'en' if n != 1 else ''}{', mehrteilig' if e['mehrteilig'] else ''})")
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
    alt = {"vaults": {}, "dateien": {}, "repos": {}}
    try:
        d = json.loads(BUILD_STATE.read_text(encoding="utf-8"))
        alt = {"vaults": d.get("vaults", {}), "dateien": d.get("dateien", {}), "repos": d.get("repos", {})}
    except Exception:
        pass
    if frisch:
        if VAULTS.exists():
            shutil.rmtree(VAULTS)
        alt["vaults"], alt["dateien"] = {}, {}
        print("🔄 Neuverschlüsselung: der Tresor bekommt einen frischen Schlüssel.")
    VAULTS.mkdir(parents=True, exist_ok=True)

    vorher = alt["vaults"].get(VAULT_NAME)
    if vorher:
        vid = vorher["id"]
        k_vault = base64.b64decode(vorher["key"])
    else:
        vid = secrets.token_hex(8)
        k_vault = secrets.token_bytes(32)
    neu = {"vaults": {VAULT_NAME: {"id": vid, "key": b64(k_vault)}}, "dateien": {}, "repos": {}}

    # ── Repos ──
    print("GitHub-Repos …")
    repos = sammle_repos(cfg.get("repos") or {}, alt.get("repos") or {}, args.ohne_repos)
    neu["repos"] = {k: v for k, v in repos.items() if k != "schueler_apps"}
    manifest["repos"] = repos

    vdir = VAULTS / vid
    (vdir / "f").mkdir(parents=True, exist_ok=True)
    behalten = set()
    zaehler = {"neu": 0, "wiederverwendet": 0}
    gesamt = 0
    fid_je_schluessel = {}
    for schluessel, quelle_datei, ziel, rel in jobs:
        st = quelle_datei.stat()
        if schluessel in fid_je_schluessel:                     # dieselbe Datei in zwei Einträgen
            fid = fid_je_schluessel[schluessel]
        else:
            vorher_d = alt["dateien"].get(schluessel)
            unveraendert = (vorher_d
                            and vorher_d.get("size") == st.st_size
                            and int(vorher_d.get("mtime", -1)) == int(st.st_mtime)
                            and (vdir / "f" / f"{vorher_d['fid']}.enc").exists())
            if unveraendert:
                fid = vorher_d["fid"]                           # Chiffrat bleibt Byte-gleich
                zaehler["wiederverwendet"] += 1
            else:
                # Geänderte Datei → NEUE Kennung, damit ein alter Cache auf dem Gerät
                # nie ein veraltetes Chiffrat für die neue Fassung hält.
                fid = secrets.token_hex(12)
                (vdir / "f" / f"{fid}.enc").write_bytes(verschluessele(k_vault, quelle_datei.read_bytes()))
                zaehler["neu"] += 1
            fid_je_schluessel[schluessel] = fid
            neu["dateien"][schluessel] = {"fid": fid, "size": st.st_size, "mtime": int(st.st_mtime)}
            gesamt += st.st_size
            if st.st_size > 95 * 1024 * 1024:
                print(f"  ⚠️  {quelle_datei.name}: über 95 MB — GitHub-Limit ist 100 MB/Datei!")
        behalten.add(f"{fid}.enc")
        ziel["dateien"][rel] = {"fid": fid, "bytes": st.st_size}
        ziel["groesse"] += st.st_size
        ge = datetime.datetime.fromtimestamp(st.st_mtime).replace(microsecond=0).isoformat()
        if ge > (ziel["geaendert"] or ""):
            ziel["geaendert"] = ge

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
    anzahl = {b: sum(1 for e in manifest["bereiche"][b] if e["typ"] == "tresor" and e["dateien"]) for b in BEREICHE}
    manifest["statistik"] = {
        **anzahl,
        "links": sum(1 for b in BEREICHE for e in manifest["bereiche"][b] if e["typ"] == "link"),
        "repos": len(repos.get("liste") or []),
        "dateien": len(neu["dateien"]),
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
        "v": 2,
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
    print(f"Inhalt: {st['lerndashboards']} Lerndashboards · {st['praesentationen']} Präsentationen · "
          f"{st['simulationen']} Simulationen · {st['links']} Links · {st['repos']} Repos · "
          f"{st['dateien']} Dateien · {gesamt / 1024 / 1024:.1f} MiB")
    for b in BEREICHE:
        for e in manifest["bereiche"][b]:
            if e["typ"] == "tresor":
                print(f"  🔒 {b[:4]} {e['id']}  →  {e['titel']}  ({len(e['dateien'])} Datei(en), {e['groesse'] / 1024 / 1024:.1f} MiB)")
            else:
                print(f"  🔗 {b[:4]} {e['id']}  →  {e['titel']}")
    if uebersprungen:
        print(f"Übersprungen ({len(uebersprungen)}):")
        for u in uebersprungen:
            print(f"  – {u}")
    print("Fertig. → docs/ committen und pushen, Passwörter bleiben lokal.")


if __name__ == "__main__":
    main()
