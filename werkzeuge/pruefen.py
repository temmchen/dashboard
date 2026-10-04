#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pruefen.py — Lerndashboards · Prüflauf in headless Chrome (nur Standardbibliothek)
===================================================================================

Startet einen lokalen Webserver für docs/ (127.0.0.1), steuert Chrome über das
DevTools-Protokoll (--remote-debugging-pipe) und spielt die Wege durch, die Tom
auf iPhone und iPad geht: Anmeldung (falsch/richtig), Übersicht, Dashboard öffnen,
Tiefenverknüpfung ?d=…#/Stunde/Folie, Rückweg zur Übersicht, Abmelden. Schreibt
Prüfbilder und meldet JavaScript-Fehler.

    /usr/bin/python3 werkzeuge/pruefen.py [--geraet iphone|ipad|mac|alle] [--bilder ORDNER]

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


class CDP:
    def __init__(self):
        self.profil = tempfile.mkdtemp(prefix='ld-pruef-')
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
            time.sleep(schritt)
        raise TimeoutError(f'Bedingung nicht erfüllt: {ausdruck[:80]} … (zuletzt: {letzter!r})')

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
    ap.add_argument('--url', default='', help='statt lokalem Server diese Adresse prüfen, z. B. https://temmchen.github.io/lerndashboards/')
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

                # 1) Anmeldeseite
                cdp.befehl('Page.navigate', {'url': basis})
                cdp.warte('Page.loadEventFired')
                cdp.pumpe(0.8)
                sichtbar = cdp.js("!document.getElementById('anmeldung').classList.contains('versteckt') && !!document.getElementById('login-pw')")
                melde('Anmeldeseite sichtbar', bool(sichtbar))
                cdp.bild(bilder / f'{g}-1-anmeldung.png')

                # 2) falsches Passwort
                cdp.js("document.getElementById('login-pw').value='falsch-falsch-falsch'; document.getElementById('login-form').requestSubmit();", warten=False)
                status = cdp.warte_bis("(function(){var s=document.getElementById('login-status').textContent; return /Kein Zugang|Fehler|Verbindung/.test(s) ? s : ''})()", frist=20)
                melde('falsches Passwort wird abgelehnt', 'Kein Zugang' in status, status)

                # 3) richtiges Passwort, angemeldet bleiben
                cdp.js(f"document.getElementById('login-merken').checked=true; document.getElementById('login-pw').value={json.dumps(passwort.upper())}; document.getElementById('login-form').requestSubmit();", warten=False)
                cdp.warte_bis("!document.getElementById('app').classList.contains('versteckt')", frist=25)
                cdp.pumpe(0.6)
                karten = cdp.js("document.querySelectorAll('#liste .karte').length")
                links = cdp.js("document.querySelectorAll('#links .link').length")
                melde('Anmeldung (Passwort in GROSSBUCHSTABEN) → Übersicht', karten >= 1, f'{karten} Dashboards, {links} öffentliche Links')
                wer = cdp.js("document.getElementById('fuss-wer').textContent")
                melde('Zugang erkannt', wer == cfg['zugaenge'][0]['name'], wer)
                gemerkt = cdp.js("!!localStorage.getItem('ld_sitzung')")
                melde('Sitzung gemerkt (localStorage)', bool(gemerkt))
                cdp.bild(bilder / f'{g}-2-uebersicht.png')
                for e in cdp.fehler():
                    melde('JS-Fehler Portal', False, e)

                # 4) erstes Dashboard öffnen
                titel = cdp.js("document.querySelector('#liste .karte .k-titel').textContent")
                cdp.js("document.querySelector('#liste button[data-oeffnen]').click()", warten=False)
                cdp.warte_bis("!!(window.KI && document.body.classList.contains('mode-dash') && document.getElementById('dash-inhalt') && document.getElementById('dash-inhalt').children.length)", frist=30)
                cdp.pumpe(1.5)
                dtitel = cdp.js('document.title')
                melde('Dashboard entschlüsselt und gestartet', titel.split(' · ')[0] in dtitel, f'{dtitel} · URL {cdp.js("location.search")}')
                knopf = cdp.js("!!document.getElementById('ld-portal') && !!document.querySelector('#ctrl button[title^=\"Zurück\"]')")
                melde('Rückweg-Knöpfe eingefügt', bool(knopf))
                cdp.bild(bilder / f'{g}-3-dashboard.png')
                for e in cdp.fehler():
                    melde('JS-Fehler Dashboard', False, e)

                # 5) Stunde über die Verknüpfung ?d=…#/2/1 (Sitzung bleibt im Browser).
                #    Erst über about:blank, sonst wäre es nur ein Anker-Sprung in derselben Seite.
                kennung = cdp.js("new URLSearchParams(location.search).get('d')")
                cdp.befehl('Page.navigate', {'url': 'about:blank'})
                cdp.warte('Page.loadEventFired')
                cdp.ereignisse = [m for m in cdp.ereignisse if m.get('method') != 'Page.loadEventFired']
                cdp.befehl('Page.navigate', {'url': f'{basis}?d={urllib.parse.quote(kennung)}#/2/1'})
                cdp.warte('Page.loadEventFired')
                cdp.warte_bis("!!(window.KI && KI.mode==='show' && KI.lesson===2)", frist=30)
                cdp.pumpe(2.0)
                melde('Tiefenverknüpfung ?d=…#/2/1 öffnet Stunde 2', True, f'Folie {cdp.js("KI.index")}')
                cdp.bild(bilder / f'{g}-4-stunde2.png')
                # Bedienleiste antippen (zeigt Knöpfe) und Rückweg nehmen
                cdp.js("document.body.classList.add('ctrl-on')", warten=False)
                cdp.pumpe(0.4)
                cdp.bild(bilder / f'{g}-5-bedienleiste.png')
                cdp.js("document.querySelector('#ctrl button[title^=\"Zurück\"]').click()", warten=False)
                cdp.warte('Page.loadEventFired')
                cdp.warte_bis("!document.getElementById('app').classList.contains('versteckt')", frist=25)
                melde('Rückweg „Lerndashboards“ → Übersicht ohne neues Passwort', True)
                for e in cdp.fehler():
                    melde('JS-Fehler', False, e)

                # 5b) Knopf „Stunde N starten“ der Übersicht öffnet direkt die nächste Stunde
                nr = cdp.js("(function(){var b=document.querySelector('#liste button.primaer[data-hash]'); return b ? +b.dataset.hash.split('/')[1] : 0})()")
                if nr:
                    cdp.js("document.querySelector('#liste button.primaer[data-hash]').click()", warten=False)
                    cdp.warte_bis(f"!!(window.KI && KI.mode==='show' && KI.lesson==={nr})", frist=30)
                    cdp.pumpe(1.5)
                    melde(f'Knopf „Stunde {nr} starten“ öffnet Stunde {nr}', True, f'Folie {cdp.js("KI.index")}')
                    cdp.bild(bilder / f'{g}-5b-naechste-stunde.png')
                    for e in cdp.fehler():
                        melde('JS-Fehler', False, e)
                    cdp.js("document.querySelector('#ctrl button[title^=\"Zurück\"]').click()", warten=False)
                    cdp.warte('Page.loadEventFired')
                    cdp.warte_bis("!document.getElementById('app').classList.contains('versteckt')", frist=25)
                else:
                    melde('Knopf „Stunde starten“ vorhanden', False, 'kein Knopf mit data-hash')

                # 6) zweites Dashboard (falls vorhanden)
                n = cdp.js("document.querySelectorAll('#liste .karte').length")
                if n >= 2:
                    t2 = cdp.js("document.querySelectorAll('#liste .karte .k-titel')[1].textContent")
                    cdp.js("document.querySelectorAll('#liste .karte')[1].querySelector('button[data-oeffnen]').click()", warten=False)
                    cdp.warte_bis("!!(window.KI && document.body.classList.contains('mode-dash') && document.getElementById('dash-inhalt') && document.getElementById('dash-inhalt').children.length)", frist=30)
                    cdp.pumpe(1.5)
                    melde('zweites Dashboard gestartet', t2.split(' · ')[0] in cdp.js('document.title'), cdp.js('document.title'))
                    cdp.bild(bilder / f'{g}-6-dashboard2.png')
                    for e in cdp.fehler():
                        melde('JS-Fehler Dashboard 2', False, e)
                    cdp.js("document.getElementById('ld-portal').click()", warten=False)
                    cdp.warte('Page.loadEventFired')
                    cdp.warte_bis("!document.getElementById('app').classList.contains('versteckt')", frist=25)

                # 7) Abmelden
                cdp.js("document.getElementById('knopf-abmelden').click()", warten=False)
                cdp.pumpe(0.4)
                ab = cdp.js("!document.getElementById('anmeldung').classList.contains('versteckt') && !localStorage.getItem('ld_sitzung') && !sessionStorage.getItem('ld_sitzung')")
                melde('Abmelden löscht die Sitzung', bool(ab))
                for e in cdp.fehler():
                    melde('JS-Fehler', False, e)
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
