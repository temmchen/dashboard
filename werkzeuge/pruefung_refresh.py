#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pruefung_refresh.py — Dashboard Mobil · Prüft den Knopf ↻ (Aktualisieren) mit einer simulierten Veröffentlichung
===================================================================================================================

Kopiert docs/ in einen Temp-Ordner, startet dort einen lokalen Webserver (127.0.0.1), meldet sich in
headless Chrome an (Profil iPhone) und spielt durch, was am Mac „veröffentlichen“ auf dem Gerät auslöst:

  1. ↻ ohne Änderung                       → „Schon aktuell · Stand …“, Stand im Kopf unverändert
  2. simulierte Veröffentlichung (Manifest entschlüsseln, eine Simulation + ein Repo anhängen, neu
     verschlüsseln, neuer Build in index.json) → ↻ → „Aktualisiert · Stand … · 2 neue Einträge“,
     neuer Stand im Kopf, Eintrag in der Simulationsliste, Repo-Zahl +1; Service-Worker-Cache ohne ?t=-Einträge
  3. stille Aktualisierung über das Ereignis „online“ (wie beim Zurückkehren in die App)
  4. Neustart der Seite mit gespeicherter Sitzung zeigt den neuen Stand ohne Anmeldung
  5. Tresor „neu verschlüsselt“ (anderer Tresor im Index) → ↻ → Anmeldeseite mit Hinweis

    /usr/bin/python3 werkzeuge/pruefung_refresh.py [--bilder ORDNER]

Passwort: Umgebungsvariable DM_PASSWORT, sonst zugangsdaten.json neben werkzeuge/, sonst die des
Repos ~/Documents/GitHub/dashboard (nur gelesen). Das Repo und docs/ werden nicht verändert.
"""
import argparse
import base64
import datetime
import json
import os
import pathlib
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pruefen import CDP, GERAETE, freier_port, APP_SICHTBAR  # noqa: E402

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    sys.exit("Fehlendes Paket: /usr/bin/python3 -m pip install --user cryptography")

HIER = pathlib.Path(__file__).resolve().parent.parent
DOCS = HIER / 'docs'
REPO = pathlib.Path.home() / 'Documents' / 'GitHub' / 'dashboard'
TOAST = "(function(){var t=document.getElementById('toast'); return t.classList.contains('zeig') ? t.textContent : ''})()"


# ─────────────────────────── Krypto wie build.py / index.html ───────────────────────────

def norm(pw):
    return unicodedata.normalize('NFC', str(pw or '')).strip().lower()


def b64d(s):
    return base64.b64decode(s)


def tresor_schluessel(docs, passwort):
    """Index lesen, Passwort → KEK → Tresor-Schlüssel K (wie die Anmeldung im Browser)."""
    idx = json.loads((docs / 'vaults' / 'index.json').read_text(encoding='utf-8'))
    for pr in idx['principals']:
        kek = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b64d(pr['salt']),
                         iterations=int(idx['kdf']['iter'])).derive(norm(passwort).encode('utf-8'))
        for v in idx['vaults']:
            for w in v['wraps']:
                if w['p'] != pr['id']:
                    continue
                try:
                    nutz = json.loads(AESGCM(kek).decrypt(b64d(w['iv']), b64d(w['ct']), None))
                    return idx, v['id'], b64d(nutz['k'])
                except Exception:
                    pass
    sys.exit('Passwort passt zu keinem Tresor im Index.')


def entschluessele(k, daten):
    return AESGCM(k).decrypt(daten[:12], daten[12:], None)


def verschluessele(k, klar):
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(k).encrypt(nonce, klar, None)


def veroeffentliche(docs, vid, k, aendern):
    """Simulierte Veröffentlichung: Manifest ändern, neu verschlüsseln, neuer Build in index.json."""
    m_pfad = docs / 'vaults' / vid / 'm.enc'
    m = json.loads(entschluessele(k, m_pfad.read_bytes()))
    aendern(m)
    jetzt = datetime.datetime.now().replace(microsecond=0).isoformat()
    m['erstellt'] = jetzt
    m['build'] = secrets.token_hex(6)
    m_pfad.write_bytes(verschluessele(k, json.dumps(m, ensure_ascii=False).encode('utf-8')))
    idx_pfad = docs / 'vaults' / 'index.json'
    idx = json.loads(idx_pfad.read_text(encoding='utf-8'))
    idx['build'] = m['build']
    idx['erstellt'] = jetzt
    idx_pfad.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding='utf-8')
    return jetzt


def neue_simulation(m):
    m['bereiche']['simulationen'].append({
        'typ': 'tresor', 'bereich': 'simulationen', 'id': 'pruefung-refresh-simulation',
        'titel': 'Prüfung Refresh · neue Simulation', 'beschreibung': 'Prüfeintrag', 'klasse': 'DP2ET', 'klassen': [],
        'modul': '', 'fach': 'ELTEC3', 'jahr': '2026-2027', 'thema': 'Prüfung Refresh', 'einheit': '', 'datum': '2026-10-04',
        'farbe': '#14b8a6', 'start': 'index.html', 'dateien': {}, 'mehrteilig': False, 'groesse': 0, 'geaendert': '',
        'hinweis': 'Prüfeintrag ohne Datei'})


def neues_repo(name):
    def f(m):
        m.setdefault('repos', {}).setdefault('liste', []).append({
            'name': name, 'beschreibung': 'Prüf-Repo für den Knopf ↻', 'privat': False, 'pages': '',
            'url': f'https://github.com/temmchen/{name}', 'homepage': '', 'gepusht': '2026-10-04T12:00:00Z',
            'erstellt': '', 'sprache': '', 'topics': [], 'archiviert': False, 'fork': False, 'groesse_kb': 0,
            'portal': False, 'simulation': False})
    return f


def repo_zahl(cdp):
    import re
    t = cdp.js("document.getElementById('info-repos').textContent")
    m = re.match(r'(\d+) Repos', t)
    return int(m.group(1)) if m else -1


def passwort_finden():
    pw = os.environ.get('DM_PASSWORT')
    if pw:
        return pw
    for konfig in (HIER / 'zugangsdaten.json', REPO / 'zugangsdaten.json'):
        if konfig.is_file():
            return json.loads(konfig.read_text(encoding='utf-8'))['zugaenge'][0]['passwort']
    sys.exit('Passwort fehlt: DM_PASSWORT setzen oder zugangsdaten.json bereitstellen.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bilder', default=str(HIER / 'Pruefbilder-refresh'))
    ap.add_argument('--schnell', action='store_true', help='ohne die 60-s-Wartezeit für die stille Prüfung (visibilitychange)')
    a = ap.parse_args()
    bilder = pathlib.Path(a.bilder)
    bilder.mkdir(parents=True, exist_ok=True)
    passwort = passwort_finden()

    tmp = pathlib.Path(tempfile.mkdtemp(prefix='dm-refresh-'))
    docs = tmp / 'docs'
    shutil.copytree(DOCS, docs)
    idx, vid, k = tresor_schluessel(docs, passwort)
    print(f'Tresor {vid}, Build {idx["build"]} — Arbeitskopie {docs}')

    port = freier_port()
    server = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', str(docs)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    basis = f'http://127.0.0.1:{port}/'
    time.sleep(0.6)
    probleme = []
    breite, hoehe, mobil, touch, ua = GERAETE['iphone']
    cdp = CDP()
    try:
        ziel = cdp.befehl('Target.createTarget', {'url': 'about:blank'}, sitzung=False)
        s = cdp.befehl('Target.attachToTarget', {'targetId': ziel['targetId'], 'flatten': True}, sitzung=False)
        cdp.session = s['sessionId']
        cdp.befehl('Page.enable')
        cdp.befehl('Runtime.enable')
        cdp.befehl('Emulation.setDeviceMetricsOverride', {'width': breite, 'height': hoehe, 'deviceScaleFactor': 1, 'mobile': mobil})
        cdp.befehl('Emulation.setUserAgentOverride', {'userAgent': ua})
        cdp.befehl('Emulation.setTouchEmulationEnabled', {'enabled': True, 'maxTouchPoints': 5})

        def melde(schritt, ok, info=''):
            print(f"  {'✅' if ok else '❌'} {schritt}{(' — ' + info) if info else ''}")
            if not ok:
                probleme.append(f'{schritt} {info}')

        def js_fehler(wo):
            for e in cdp.fehler():
                melde('JS-Fehler ' + wo, False, e)

        def toast_mit(muster, frist=20):
            return cdp.warte_bis(f"(function(){{var t=document.getElementById('toast'); return t.classList.contains('zeig') && t.textContent.indexOf({json.dumps(muster)})>=0 ? t.textContent : ''}})()", frist=frist)

        def knopf_frei():
            cdp.warte_bis("!document.getElementById('knopf-aktualisieren').disabled", frist=15)

        # Anmelden (angemeldet bleiben), Startseite
        cdp.navigiere(basis)
        cdp.pumpe(0.8)
        cdp.js(f"document.getElementById('login-merken').checked=true; document.getElementById('login-pw').value={json.dumps(passwort)}; document.getElementById('login-form').requestSubmit();", warten=False)
        cdp.warte_bis(APP_SICHTBAR, frist=30)
        cdp.pumpe(1.0)
        stand0 = cdp.js("document.getElementById('kopf-stand').textContent")
        melde('Anmeldung → App, Stand im Kopf', bool(stand0), stand0)
        melde('Knopf ↻ sichtbar im Kopf', bool(cdp.js("(function(){var b=document.getElementById('knopf-aktualisieren'); var r=b.getBoundingClientRect(); return r.width>=36 && r.height>=36 && !b.disabled})()")))
        cdp.bild(bilder / 'iphone-01-start.png')

        # 1) ↻ ohne Änderung
        cdp.js("document.getElementById('knopf-aktualisieren').click()", warten=False)
        t = toast_mit('Schon aktuell')
        melde('↻ ohne Änderung → „Schon aktuell“', 'Schon aktuell' in t and cdp.js("document.getElementById('kopf-stand').textContent") == stand0, t)
        knopf_frei()
        cdp.bild(bilder / 'iphone-02-schon-aktuell.png')
        js_fehler('(Schon aktuell)')
        cdp.pumpe(4.5)                                            # Toast ausblenden lassen

        # 2) simulierte Veröffentlichung: + Simulation + Repo → ↻
        repos_vorher = repo_zahl(cdp)
        sim_vorher = cdp.js("document.getElementById('info-simulationen').textContent")

        def aenderung1(m):
            neue_simulation(m)
            neues_repo('pruefung-refresh-repo')(m)
        jetzt1 = veroeffentliche(docs, vid, k, aenderung1)
        cdp.js("document.getElementById('knopf-aktualisieren').click()", warten=False)
        t = toast_mit('Aktualisiert')
        melde('↻ nach Veröffentlichung → „Aktualisiert … 2 neue Einträge“', '2 neue Einträge' in t, t)
        knopf_frei()
        stand1 = cdp.js("document.getElementById('kopf-stand').textContent")
        melde('Stand im Kopf erneuert', stand1 != stand0 and jetzt1[11:16] in stand1, f'{stand0} → {stand1}')
        melde('Repo-Zahl +1', repo_zahl(cdp) == repos_vorher + 1, f'{repos_vorher} → {repo_zahl(cdp)}')
        cdp.js("document.querySelector('#kacheln button[data-ansicht=simulationen]').click()", warten=False)
        cdp.pumpe(0.3)
        drin = cdp.js("[...document.querySelectorAll('#liste-simulationen .z-titel')].some(z => z.textContent.indexOf('Prüfung Refresh') >= 0)")
        melde('Neue Simulation steht in der Liste', bool(drin), cdp.js("document.getElementById('info-simulationen').textContent") + f' (vorher {sim_vorher})')
        cdp.bild(bilder / 'iphone-03-aktualisiert.png')
        schluessel = cdp.js("caches.open('dm-v2').then(c => c.keys()).then(ks => ks.map(k => k.url))")
        mit_zusatz = [u for u in (schluessel or []) if '?' in u]
        melde('Service-Worker-Cache ohne ?t=-Einträge', not mit_zusatz and any(u.endswith('/vaults/index.json') for u in (schluessel or [])),
              f'{len(schluessel or [])} Einträge' + (', mit Zusatz: ' + ', '.join(mit_zusatz[:3]) if mit_zusatz else ''))
        js_fehler('(Aktualisiert)')
        cdp.pumpe(4.5)

        # 3) stille Aktualisierung über „online“
        veroeffentliche(docs, vid, k, neues_repo('pruefung-refresh-repo-2'))
        cdp.js("window.dispatchEvent(new Event('online'))", warten=False)
        t = toast_mit('1 neuer Eintrag')
        melde('Stille Aktualisierung (Ereignis „online“)', '1 neuer Eintrag' in t and repo_zahl(cdp) == repos_vorher + 2, t)
        melde('Ansicht Simulationen bleibt offen', bool(cdp.js("!document.getElementById('ansicht-simulationen').classList.contains('versteckt')")))
        js_fehler('(online)')
        cdp.pumpe(4.5)
        erwartet = repos_vorher + 2

        # 3b) still über „visibilitychange“ am Dokument (Zurückkehren in die App) – gedrosselt: 60 s nach der letzten Prüfung
        if not a.schnell:
            veroeffentliche(docs, vid, k, neues_repo('pruefung-refresh-repo-sichtbar'))
            cdp.js("document.dispatchEvent(new Event('visibilitychange'))", warten=False)
            cdp.pumpe(2.0)
            melde('visibilitychange kurz nach der letzten Prüfung löst nichts aus (Drossel)', repo_zahl(cdp) == erwartet, f'{repo_zahl(cdp)} Repos')
            print('  … warte 61 s (Drossel der stillen Prüfung)')
            cdp.pumpe(61)
            cdp.js("document.dispatchEvent(new Event('visibilitychange'))", warten=False)
            t = toast_mit('1 neuer Eintrag')
            erwartet += 1
            melde('Stille Aktualisierung (Ereignis „visibilitychange“ am Dokument)', '1 neuer Eintrag' in t and repo_zahl(cdp) == erwartet, t)
            js_fehler('(visibilitychange)')
            cdp.pumpe(4.5)

        # 4) Neustart mit gespeicherter Sitzung zeigt den neuen Stand ohne Anmeldung
        veroeffentliche(docs, vid, k, neues_repo('pruefung-refresh-repo-3'))
        erwartet += 1
        cdp.navigiere(basis)
        cdp.warte_bis(APP_SICHTBAR, frist=30)
        cdp.pumpe(1.0)
        melde('Neustart: gespeicherte Sitzung, neuer Stand ohne Anmeldung', repo_zahl(cdp) == erwartet, f'{repo_zahl(cdp)} Repos · ' + cdp.js("document.getElementById('kopf-stand').textContent"))
        melde('Neustart: Build der Sitzung gespeichert', bool(cdp.js(f"JSON.parse(localStorage.getItem('dm_sitzung')).build === {json.dumps(json.loads((docs / 'vaults' / 'index.json').read_text())['build'])}")))
        cdp.js("document.getElementById('knopf-aktualisieren').click()", warten=False)
        t = toast_mit('Schon aktuell')
        melde('Nach Neustart ↻ → „Schon aktuell“', 'Schon aktuell' in t, t)
        knopf_frei()
        js_fehler('(Neustart)')
        cdp.pumpe(4.5)

        # 5) Tresor neu verschlüsselt: anderer Tresor im Index → ↻ → Anmeldung
        idx_pfad = docs / 'vaults' / 'index.json'
        idx2 = json.loads(idx_pfad.read_text(encoding='utf-8'))
        idx2['vaults'][0]['id'] = 'ffffffffffffffff'
        idx2['vaults'][0]['manifest'] = 'vaults/ffffffffffffffff/m.enc'
        idx2['build'] = secrets.token_hex(6)
        idx_pfad.write_text(json.dumps(idx2, ensure_ascii=False, indent=1), encoding='utf-8')
        cdp.js("document.getElementById('knopf-aktualisieren').click()", warten=False)
        status = cdp.warte_bis("(function(){var s=document.getElementById('login-status').textContent; return !document.getElementById('anmeldung').classList.contains('versteckt') && s ? s : ''})()", frist=20)
        melde('Tresor neu verschlüsselt → Anmeldeseite mit Hinweis', 'neu verschlüsselt' in status and not cdp.js("!!localStorage.getItem('dm_sitzung')"), status)
        cdp.bild(bilder / 'iphone-04-neu-verschluesselt.png')
        js_fehler('(neu verschlüsselt)')
    except Exception as ex:
        probleme.append(str(ex))
        print(f'  ❌ Abbruch: {ex}')
        try:
            cdp.bild(bilder / 'iphone-fehler.png')
        except Exception:
            pass
    finally:
        cdp.schliessen()
        server.terminate()
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if probleme:
        print(f'❌ {len(probleme)} Problem(e):')
        for p in probleme:
            print('   ' + p)
        sys.exit(1)
    print(f'✅ Alle Prüfungen bestanden. Prüfbilder: {bilder}')


if __name__ == '__main__':
    main()
