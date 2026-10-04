#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pruefen.py — Dashboard Mobil · Prüflauf in headless Chrome (nur Standardbibliothek)
====================================================================================

Startet einen lokalen Webserver für docs/ (127.0.0.1), steuert Chrome über das
DevTools-Protokoll (--remote-debugging-pipe) und spielt die Wege durch, die Tom
auf iPhone und iPad geht: Anmeldung (falsch/richtig), Reiter Repos (Suche, Filter,
QR), Präsentation (Touch-Leiste), Lerndashboard (Verknüpfung ?d=…#/2/1, Knopf
„Stunde N starten“), Simulationen (mehrteilig über den Service Worker), Rückwege,
Abmelden. Schreibt Prüfbilder und meldet JavaScript-Fehler.

    /usr/bin/python3 werkzeuge/pruefen.py [--geraet iphone|iphone-quer|ipad|mac|alle] [--bilder ORDNER] [--url ADRESSE]

Das Passwort liest das Werkzeug aus zugangsdaten.json (nur lokal vorhanden).
Nach dem Lauf wird der Webserver beendet; es bleibt nichts laufen.
"""
import argparse
import base64
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
HIER = pathlib.Path(__file__).resolve().parent.parent
DOCS = HIER / 'docs'

GERAETE = {
    # Name: (Breite, Höhe, mobil, Touch, User-Agent)
    'iphone': (390, 844, True, True,
               'Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Mobile/15E148 Safari/604.1'),
    'iphone-quer': (844, 390, True, True,
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Mobile/15E148 Safari/604.1'),
    'ipad': (1180, 820, True, True,
             'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Safari/605.1.15'),
    'mac': (1440, 900, False, False, ''),
}

APP_SICHTBAR = "!document.getElementById('app').classList.contains('versteckt')"


class CDP:
    def __init__(self):
        self.profil = tempfile.mkdtemp(prefix='dm-pruef-')
        r1, w1 = os.pipe()
        r2, w2 = os.pipe()

        def vorbereiten():
            a, b = os.dup(r1), os.dup(w2)
            os.dup2(a, 3)
            os.dup2(b, 4)
            os.set_inheritable(3, True)
            os.set_inheritable(4, True)

        self.p = subprocess.Popen(
            [CHROME, '--headless=new', '--remote-debugging-pipe', f'--user-data-dir={self.profil}',
             '--no-first-run', '--no-default-browser-check', '--hide-scrollbars', '--disable-gpu',
             '--window-size=1920,1080', '--force-device-scale-factor=1', 'about:blank'],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=False, preexec_fn=vorbereiten)
        os.close(r1); os.close(w2)
        self.w = os.fdopen(w1, 'wb', buffering=0)
        self.r = os.fdopen(r2, 'rb', buffering=0)
        self.puffer = b''
        self.nid = 0
        self.ereignisse = []
        self.session = None

    def _lies(self):
        while b'\0' not in self.puffer:
            teil = self.r.read(1 << 20)
            if not teil:
                raise RuntimeError('Chrome hat die Verbindung beendet')
            self.puffer += teil
        roh, self.puffer = self.puffer.split(b'\0', 1)
        return json.loads(roh)

    def befehl(self, methode, params=None, sitzung=True, frist=30):
        self.nid += 1
        n = {'id': self.nid, 'method': methode, 'params': params or {}}
        if sitzung and self.session:
            n['sessionId'] = self.session
        self.w.write(json.dumps(n).encode() + b'\0')
        ende = time.time() + frist
        while time.time() < ende:
            m = self._lies()
            if m.get('id') == self.nid:
                if 'error' in m:
                    raise RuntimeError(f"{methode}: {m['error']}")
                return m.get('result', {})
            self.ereignisse.append(m)
        raise TimeoutError(methode)

    def warte(self, name, frist=15):
        ende = time.time() + frist
        for i, m in enumerate(self.ereignisse):
            if m.get('method') == name:
                del self.ereignisse[i]
                return m
        while time.time() < ende:
            m = self._lies()
            if m.get('method') == name:
                return m
            self.ereignisse.append(m)
        raise TimeoutError(name)

    def vergiss(self, name):
        self.ereignisse = [m for m in self.ereignisse if m.get('method') != name]

    def pumpe(self, sek):
        ende = time.time() + sek
        while time.time() < ende:
            time.sleep(min(0.2, max(0, ende - time.time())))
            self.befehl('Runtime.evaluate', {'expression': '1'})

    def js(self, ausdruck, warten=True):
        r = self.befehl('Runtime.evaluate', {'expression': ausdruck, 'awaitPromise': warten, 'returnByValue': True})
        if 'exceptionDetails' in r:
            d = r['exceptionDetails']
            raise RuntimeError('JS: ' + (d.get('exception', {}).get('description') or d.get('text', '')).split('\n')[0])
        return r['result'].get('value')

    def warte_bis(self, ausdruck, frist=15, schritt=0.25):
        ende = time.time() + frist
        letzter = None
        while time.time() < ende:
            try:
                letzter = self.js(ausdruck, warten=False)
                if letzter:
                    return letzter
            except RuntimeError as e:
                letzter = str(e)
            except Exception as e:          # Seite wird gerade ersetzt / navigiert
                letzter = str(e)
            time.sleep(schritt)
        raise TimeoutError(f'Bedingung nicht erfüllt: {ausdruck[:90]} … (zuletzt: {letzter!r})')

    def navigiere(self, url):
        self.vergiss('Page.loadEventFired')
        self.befehl('Page.navigate', {'url': url})
        self.warte('Page.loadEventFired')

    def fehler(self):
        aus = []
        for m in self.ereignisse:
            if m.get('method') == 'Runtime.exceptionThrown':
                d = m['params']['exceptionDetails']
                aus.append('Uncaught: ' + (d.get('exception', {}).get('description') or d.get('text', '')).split('\n')[0])
            elif m.get('method') == 'Runtime.consoleAPICalled' and m['params'].get('type') in ('error', 'assert'):
                txt = ' '.join(str(a.get('value', a.get('description', ''))) for a in m['params'].get('args', []))
                aus.append('console.' + m['params']['type'] + ': ' + txt[:400])
        self.ereignisse = [m for m in self.ereignisse if m.get('method') not in ('Runtime.exceptionThrown', 'Runtime.consoleAPICalled')]
        return aus

    def bild(self, datei):
        b = self.befehl('Page.captureScreenshot', {'format': 'png'})
        pathlib.Path(datei).write_bytes(base64.b64decode(b['data']))
        return datei

    def schliessen(self):
        try:
            self.befehl('Browser.close', sitzung=False, frist=5)
        except Exception:
            pass
        try:
            self.p.wait(5)
        except Exception:
            self.p.kill()
        shutil.rmtree(self.profil, ignore_errors=True)


def freier_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--geraet', default='alle', help='iphone | iphone-quer | ipad | mac | alle')
    ap.add_argument('--bilder', default=str(HIER / 'Pruefbilder'))
    ap.add_argument('--url', default='', help='statt lokalem Server diese Adresse prüfen, z. B. https://temmchen.github.io/dashboard/')
    a = ap.parse_args()
    bilder = pathlib.Path(a.bilder)
    bilder.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((HIER / 'zugangsdaten.json').read_text(encoding='utf-8'))
    passwort = cfg['zugaenge'][0]['passwort']
    geraete = list(GERAETE) if a.geraet == 'alle' else [a.geraet]

    if a.url:
        server = None
        basis = a.url if a.url.endswith('/') else a.url + '/'
        print(f'Prüfe {basis}')
    else:
        port = freier_port()
        server = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', str(DOCS)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        basis = f'http://127.0.0.1:{port}/'
        time.sleep(0.6)
    probleme = []
    try:
        for g in geraete:
            breite, hoehe, mobil, touch, ua = GERAETE[g]
            print(f'\n═══ {g} ({breite}×{hoehe}) ═══')
            cdp = CDP()
            try:
                ziel = cdp.befehl('Target.createTarget', {'url': 'about:blank'}, sitzung=False)
                s = cdp.befehl('Target.attachToTarget', {'targetId': ziel['targetId'], 'flatten': True}, sitzung=False)
                cdp.session = s['sessionId']
                cdp.befehl('Page.enable')
                cdp.befehl('Runtime.enable')
                cdp.befehl('Emulation.setDeviceMetricsOverride', {'width': breite, 'height': hoehe, 'deviceScaleFactor': 1, 'mobile': mobil})
                if ua:
                    cdp.befehl('Emulation.setUserAgentOverride', {'userAgent': ua})
                if touch:
                    cdp.befehl('Emulation.setTouchEmulationEnabled', {'enabled': True, 'maxTouchPoints': 5})

                def melde(schritt, ok, info=''):
                    print(f"  {'✅' if ok else '❌'} {schritt}{(' — ' + info) if info else ''}")
                    if not ok:
                        probleme.append(f'{g}: {schritt} {info}')

                def js_fehler(wo):
                    for e in cdp.fehler():
                        melde('JS-Fehler ' + wo, False, e)

                def zurueck_zur_app(knopf_js):
                    cdp.vergiss('Page.loadEventFired')
                    cdp.js(knopf_js, warten=False)
                    cdp.warte('Page.loadEventFired', frist=25)
                    cdp.warte_bis(APP_SICHTBAR, frist=25)

                # 1) Anmeldeseite
                cdp.navigiere(basis)
                cdp.pumpe(0.8)
                sichtbar = cdp.js("!document.getElementById('anmeldung').classList.contains('versteckt') && !!document.getElementById('login-pw')")
                melde('Anmeldeseite sichtbar', bool(sichtbar))
                cdp.bild(bilder / f'{g}-01-anmeldung.png')

                # 2) falsches Passwort
                cdp.js("document.getElementById('login-pw').value='falsch-falsch-falsch'; document.getElementById('login-form').requestSubmit();", warten=False)
                status = cdp.warte_bis("(function(){var s=document.getElementById('login-status').textContent; return /Kein Zugang|Fehler|Verbindung/.test(s) ? s : ''})()", frist=20)
                melde('falsches Passwort wird abgelehnt', 'Kein Zugang' in status, status)

                # 3) richtiges Passwort, angemeldet bleiben
                cdp.js(f"document.getElementById('login-merken').checked=true; document.getElementById('login-pw').value={json.dumps(passwort.upper())}; document.getElementById('login-form').requestSubmit();", warten=False)
                cdp.warte_bis(APP_SICHTBAR, frist=25)
                cdp.pumpe(0.8)
                wer = cdp.js("document.getElementById('fuss-wer').textContent")
                melde('Anmeldung (Passwort in GROSSBUCHSTABEN) → App', wer == cfg['zugaenge'][0]['name'], 'Zugang ' + wer)
                melde('Sitzung gemerkt (localStorage)', bool(cdp.js("!!localStorage.getItem('dm_sitzung')")))

                # 4) Reiter Repos
                cdp.js("document.querySelector('#tabs button[data-tab=repos]').click()", warten=False)
                cdp.pumpe(0.3)
                n_repos = cdp.js("document.querySelectorAll('#repos-liste .repo').length")
                repos_info = cdp.js("document.getElementById('repos-info').textContent")
                melde('Reiter Repos zeigt Liste', n_repos >= 10, f'{n_repos} Repos · {repos_info}')
                cdp.bild(bilder / f'{g}-02-repos.png')
                cdp.js("var s=document.getElementById('repos-suche'); s.value='fx991'; s.dispatchEvent(new Event('input'));", warten=False)
                cdp.pumpe(0.2)
                n_such = cdp.js("document.querySelectorAll('#repos-liste .repo').length")
                melde('Suche „fx991“', n_such == 1, f'{n_such} Treffer')
                cdp.js("var s=document.getElementById('repos-suche'); s.value=''; s.dispatchEvent(new Event('input')); document.querySelector('#repos-filter button[data-filter=privat]').click();", warten=False)
                cdp.pumpe(0.2)
                n_priv = cdp.js("document.querySelectorAll('#repos-liste .repo').length")
                melde('Filter „Privat“', n_priv >= 1 and bool(cdp.js("[...document.querySelectorAll('#repos-liste .repo .marke2.privat')].length === document.querySelectorAll('#repos-liste .repo').length")), f'{n_priv} private Repos')
                cdp.js("document.querySelector('#repos-filter button[data-filter=alle]').click(); document.querySelector('#repos-liste button[data-qr]').click();", warten=False)
                cdp.pumpe(0.3)
                qr_ok = cdp.js("!document.getElementById('qr').classList.contains('versteckt') && !!document.querySelector('#qr svg path') && document.querySelector('#qr .qr-url').textContent.startsWith('https://')")
                melde('QR-Code bildschirmfüllend', bool(qr_ok), cdp.js("document.querySelector('#qr .qr-url').textContent"))
                cdp.bild(bilder / f'{g}-03-qr.png')
                cdp.js("document.getElementById('qr').click()", warten=False)
                cdp.pumpe(0.2)
                js_fehler('Repos')

                # 5) Reiter Präsentationen: öffnen, Touch-Leiste, weiterblättern, zurück
                cdp.js("document.querySelector('#tabs button[data-tab=praesentationen]').click()", warten=False)
                cdp.pumpe(0.3)
                n_p = cdp.js("document.querySelectorAll('#praesentationen-liste .karte').length")
                melde('Reiter Präsentationen', n_p >= 1, f'{n_p} Präsentationen')
                cdp.bild(bilder / f'{g}-04-praesentationen.png')
                if n_p:
                    pt = cdp.js("document.querySelector('#praesentationen-liste .k-titel').textContent")
                    cdp.js("document.querySelector('#praesentationen-liste button[data-oeffnen]').click()", warten=False)
                    cdp.warte_bis("!!(window.KI && document.querySelectorAll('section.slide').length > 10 && document.getElementById('dm-bar'))", frist=40)
                    cdp.pumpe(2.0)
                    melde('Präsentation entschlüsselt und gestartet', pt.split(' · ')[0] in cdp.js('document.title'), cdp.js('document.title'))
                    cdp.js("document.body.dispatchEvent(new Event('mousemove',{bubbles:true})); document.getElementById('dm-bar').classList.add('an'); [...document.querySelectorAll('#dm-bar button')].find(b=>b.textContent==='›').click();", warten=False)
                    cdp.pumpe(1.2)
                    melde('Touch-Leiste blättert weiter', True, 'Anker ' + str(cdp.js('location.hash')))
                    cdp.bild(bilder / f'{g}-05-praesentation.png')
                    js_fehler('Präsentation')
                    zurueck_zur_app("[...document.querySelectorAll('#dm-bar button')][0].click()")
                    melde('Rückweg aus der Präsentation', True)

                # 6) Reiter Lerndashboards: öffnen, Verknüpfung, Knopf „Stunde N starten“
                cdp.js("document.querySelector('#tabs button[data-tab=lerndashboards]').click()", warten=False)
                cdp.pumpe(0.3)
                karten = cdp.js("document.querySelectorAll('#lerndashboards-liste .karte').length")
                links = cdp.js("document.querySelectorAll('#lerndashboards-links .link').length")
                melde('Reiter Lerndashboards', karten >= 1, f'{karten} Dashboards, {links} öffentliche Links')
                cdp.bild(bilder / f'{g}-06-lerndashboards.png')
                titel = cdp.js("document.querySelector('#lerndashboards-liste .karte .k-titel').textContent")
                cdp.js("document.querySelector('#lerndashboards-liste button[data-oeffnen]').click()", warten=False)
                cdp.warte_bis("!!(window.KI && document.body.classList.contains('mode-dash') && document.getElementById('dash-inhalt') && document.getElementById('dash-inhalt').children.length)", frist=30)
                cdp.pumpe(1.5)
                melde('Lerndashboard entschlüsselt und gestartet', titel.split(' · ')[0] in cdp.js('document.title'), f'{cdp.js("document.title")} · URL {cdp.js("location.search")}')
                melde('Rückweg-Knöpfe eingefügt', bool(cdp.js("!!document.getElementById('dm-portal') && !!document.querySelector('#ctrl button[title^=\"Zurück\"]')")))
                cdp.bild(bilder / f'{g}-07-dashboard.png')
                js_fehler('Lerndashboard')
                kennung = cdp.js("new URLSearchParams(location.search).get('d')")
                cdp.navigiere('about:blank')     # sonst wäre es nur ein Anker-Sprung in derselben Seite
                cdp.navigiere(f'{basis}?d={urllib.parse.quote(kennung)}#/2/1')
                cdp.warte_bis("!!(window.KI && KI.mode==='show' && KI.lesson===2)", frist=30)
                cdp.pumpe(2.0)
                melde('Verknüpfung ?d=…#/2/1 öffnet Stunde 2', True, f'Folie {cdp.js("KI.index")}')
                cdp.bild(bilder / f'{g}-08-stunde2.png')
                cdp.js("document.body.classList.add('ctrl-on')", warten=False)
                cdp.pumpe(0.4)
                cdp.bild(bilder / f'{g}-09-bedienleiste.png')
                zurueck_zur_app("document.querySelector('#ctrl button[title^=\"Zurück\"]').click()")
                melde('Rückweg „Dashboard“ → App ohne neues Passwort', True)
                js_fehler('')
                cdp.js("document.querySelector('#tabs button[data-tab=lerndashboards]').click()", warten=False)
                cdp.pumpe(0.3)
                nr = cdp.js("(function(){var b=document.querySelector('#lerndashboards-liste button.primaer[data-hash]'); return b ? +b.dataset.hash.split('/')[1] : 0})()")
                if nr:
                    cdp.js("document.querySelector('#lerndashboards-liste button.primaer[data-hash]').click()", warten=False)
                    cdp.warte_bis(f"!!(window.KI && KI.mode==='show' && KI.lesson==={nr})", frist=30)
                    cdp.pumpe(1.0)
                    melde(f'Knopf „Stunde {nr} starten“ öffnet Stunde {nr}', True)
                    zurueck_zur_app("document.querySelector('#ctrl button[title^=\"Zurück\"]').click()")
                else:
                    melde('Knopf „Stunde starten“ vorhanden', False, 'kein Knopf mit data-hash')

                # 7) Reiter Simulationen: mehrteilige Simulation über den Service Worker, einteilige per document.write
                cdp.js("document.querySelector('#tabs button[data-tab=simulationen]').click()", warten=False)
                cdp.pumpe(0.3)
                n_s = cdp.js("document.querySelectorAll('#simulationen-liste .karte').length")
                n_gh = cdp.js("document.querySelectorAll('#simulationen-github .link').length")
                melde('Reiter Simulationen', n_s >= 1, f'{n_s} lokal · {n_gh} GitHub Pages')
                cdp.bild(bilder / f'{g}-10-simulationen.png')
                mehr = cdp.js("(function(){var k=[...document.querySelectorAll('#simulationen-liste .karte')].find(k=>/Dateien/.test(k.textContent)); return k ? k.querySelector('button[data-oeffnen]').dataset.oeffnen : ''})()")
                if mehr:
                    cdp.vergiss('Page.loadEventFired')
                    cdp.js(f"document.querySelector('#simulationen-liste button[data-oeffnen={json.dumps(mehr)}]').click()", warten=False)
                    cdp.warte_bis("!!(location.pathname.indexOf('/d/') >= 0 && document.getElementById('kapitelliste') && document.getElementById('kapitelliste').children.length > 0 && document.getElementById('dm-portal'))", frist=40)
                    cdp.pumpe(1.0)
                    melde('Mehrteilige Simulation über den Service Worker (Skripte geladen)', True, cdp.js('location.pathname') + ' · ' + cdp.js('document.title'))
                    cdp.bild(bilder / f'{g}-11-simulation-sw.png')
                    js_fehler('Simulation (SW)')
                    # Neuladen der Adresse d/… muss ohne neue Anmeldung gehen (Schlüssel in IndexedDB)
                    cdp.navigiere(cdp.js('location.href'))
                    cdp.warte_bis("!!(document.getElementById('kapitelliste') && document.getElementById('kapitelliste').children.length > 0)", frist=30)
                    melde('Neuladen der Simulation ohne neue Anmeldung', True)
                    zurueck_zur_app("document.getElementById('dm-portal').click()")
                    melde('Rückweg aus der Simulation', True)
                else:
                    melde('mehrteilige Simulation vorhanden', False, 'keine Karte mit „Dateien“')
                cdp.js("document.querySelector('#tabs button[data-tab=simulationen]').click()", warten=False)
                cdp.pumpe(0.3)
                eins = cdp.js("(function(){var k=[...document.querySelectorAll('#simulationen-liste .karte')].find(k=>!/Dateien/.test(k.textContent)); return k ? k.querySelector('button[data-oeffnen]').dataset.oeffnen : ''})()")
                if eins:
                    st = cdp.js(f"document.querySelector('#simulationen-liste button[data-oeffnen={json.dumps(eins)}]').closest('.karte').querySelector('.k-titel').textContent")
                    cdp.js(f"document.querySelector('#simulationen-liste button[data-oeffnen={json.dumps(eins)}]').click()", warten=False)
                    cdp.warte_bis("!!(document.getElementById('dm-portal') && document.getElementById('dm-portal').classList.contains('dm-immer'))", frist=30)
                    cdp.pumpe(1.0)
                    melde('Einteilige Simulation gestartet', st.split(' · ')[0] in cdp.js('document.title'), cdp.js('document.title'))
                    cdp.bild(bilder / f'{g}-12-simulation.png')
                    js_fehler('Simulation')
                    zurueck_zur_app("document.getElementById('dm-portal').click()")

                # 8) Abmelden
                cdp.js("document.getElementById('knopf-abmelden').click()", warten=False)
                cdp.pumpe(0.5)
                ab = cdp.js("!document.getElementById('anmeldung').classList.contains('versteckt') && !localStorage.getItem('dm_sitzung') && !sessionStorage.getItem('dm_sitzung')")
                melde('Abmelden löscht die Sitzung', bool(ab))
                js_fehler('')
            except Exception as ex:
                probleme.append(f'{g}: {ex}')
                print(f'  ❌ Abbruch: {ex}')
                try:
                    cdp.bild(bilder / f'{g}-fehler.png')
                except Exception:
                    pass
            finally:
                cdp.schliessen()
    finally:
        if server:
            server.terminate()
    print()
    if probleme:
        print(f'❌ {len(probleme)} Problem(e):')
        for p in probleme:
            print('   ' + p)
        sys.exit(1)
    print(f'✅ Alle Prüfungen bestanden. Prüfbilder: {bilder}')


if __name__ == '__main__':
    main()
