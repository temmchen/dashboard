#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pruefung_safari.py — Dashboard Mobil · Knopf ↻ in Safari (WebKit – dieselbe Engine wie Safari auf iPhone und iPad)
=====================================================================================================================

Steuert Safari am Mac über safaridriver (WebDriver, nur Standardbibliothek) und spielt dasselbe durch wie
werkzeuge/pruefung_refresh.py in Chrome: Anmeldung, ↻ ohne Änderung („Schon aktuell“), simulierte
Veröffentlichung in einer Temp-Kopie von docs/ → ↻ („Aktualisiert … 2 neue Einträge“, Stand neu, Eintrag in der
Liste, Repo-Zahl +1, Service-Worker-Cache ohne ?t=), stille Aktualisierung (Ereignisse „online“ und
„visibilitychange“), Neustart mit gespeicherter Sitzung, Tresor neu verschlüsselt → Anmeldung.

    /usr/bin/python3 werkzeuge/pruefung_safari.py [--bilder ORDNER] [--schnell] [--wkwebview]

Einmalige Voraussetzung am Mac (ohne --wkwebview): Safari → Einstellungen → Erweitert → „Funktionen für
Webentwickler anzeigen“, dann Menü „Entwickler“ → „Entfernte Automation erlauben“ (oder: safaridriver --enable).
Safari öffnet während der Prüfung sichtbar ein Fenster („Automation“) und schließt es danach wieder.
--wkwebview nimmt stattdessen WebKit direkt (WKWebView über werkzeuge/webkit_treiber.swift, wird mit swiftc
gebaut): dieselbe Engine wie Safari, braucht keine Freigabe in Safari; zeigt kurz ein eigenes Fenster.
--schnell lässt die 60-Sekunden-Wartezeit für die stille Prüfung beim Zurückkehren in die App aus.
Passwort wie bei pruefung_refresh.py (DM_PASSWORT oder zugangsdaten.json). Repo und docs/ bleiben unverändert.
"""
import argparse
import base64
import json
import pathlib
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pruefen import freier_port  # noqa: E402
from pruefung_refresh import DOCS, HIER, neue_simulation, neues_repo, passwort_finden, tresor_schluessel, veroeffentliche  # noqa: E402

APP_SICHTBAR = "return !document.getElementById('app').classList.contains('versteckt')"
FEHLERSAMMLER = ("window.__dmFehler = window.__dmFehler || []; if(!window.__dmFaenger){ window.__dmFaenger = true;"
                 " window.addEventListener('error', e => window.__dmFehler.push('Uncaught: ' + e.message));"
                 " window.addEventListener('unhandledrejection', e => window.__dmFehler.push('Promise: ' + (e.reason && e.reason.message || e.reason))); }")


class Safari:
    """Kleiner W3C-WebDriver-Client für safaridriver."""

    def __init__(self):
        self.port = freier_port()
        self.p = subprocess.Popen(['safaridriver', '-p', str(self.port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ende = time.time() + 15
        while time.time() < ende:
            try:
                self.ruf('GET', '/status')
                break
            except Exception:
                time.sleep(0.3)
        else:
            raise RuntimeError('safaridriver startet nicht')
        st, antwort = self.ruf('POST', '/session', {'capabilities': {'alwaysMatch': {'browserName': 'Safari'}}})
        wert = antwort.get('value') or {}
        if st != 200 or not wert.get('sessionId'):
            self.p.terminate()                         # sonst bleibt safaridriver liegen
            raise RuntimeError('Safari-Sitzung: ' + str(wert.get('message') or antwort))
        self.sid = wert['sessionId']
        self.basis = f'/session/{self.sid}'

    def ruf(self, methode, pfad, body=None):
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{pfad}', method=methode,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or '{}')

    def befehl(self, methode, pfad, body=None):
        st, antwort = self.ruf(methode, self.basis + pfad, body)
        if st != 200:
            w = antwort.get('value') or {}
            raise RuntimeError(f"{pfad}: {w.get('error')} – {w.get('message')}")
        return antwort.get('value')

    def navigiere(self, url):
        self.befehl('POST', '/url', {'url': url})
        self.js(FEHLERSAMMLER)

    def js(self, script, *args):
        """script wie eine Funktion: 'return …'."""
        return self.befehl('POST', '/execute/sync', {'script': script, 'args': list(args)})

    def js_async(self, script):
        """script bekommt den Rückruf als letztes Argument (arguments[arguments.length-1])."""
        return self.befehl('POST', '/execute/async', {'script': script, 'args': []})

    def warte_bis(self, ausdruck, frist=20, schritt=0.25):
        ende = time.time() + frist
        letzter = None
        while time.time() < ende:
            try:
                letzter = self.js(ausdruck)
                if letzter:
                    return letzter
            except Exception as e:
                letzter = str(e)
            time.sleep(schritt)
        raise TimeoutError(f'Bedingung nicht erfüllt: {ausdruck[:90]} … (zuletzt: {letzter!r})')

    def fehler(self):
        try:
            aus = self.js('var f = window.__dmFehler || []; window.__dmFehler = []; return f;') or []
        except Exception:
            aus = []
        return aus

    def bild(self, datei):
        b = self.befehl('GET', '/screenshot')
        pathlib.Path(datei).write_bytes(base64.b64decode(b))

    def schliessen(self):
        try:
            self.ruf('DELETE', self.basis)
        except Exception:
            pass
        self.p.terminate()
        try:
            self.p.wait(5)
        except Exception:
            self.p.kill()


class WebKitTreiber:
    """WKWebView (werkzeuge/webkit_treiber.swift) – dieselbe Engine wie Safari, ohne Safari-Fernsteuerung.
    Gleiche Schnittstelle wie Safari: navigiere, js ('return …'), js_async, warte_bis, fehler, bild, schliessen."""

    def __init__(self):
        quelle = pathlib.Path(__file__).resolve().parent / 'webkit_treiber.swift'
        self.ordner = pathlib.Path(tempfile.mkdtemp(prefix='dm-webkit-'))
        binaer = self.ordner / 'webkit_treiber'
        r = subprocess.run(['swiftc', '-O', str(quelle), '-o', str(binaer)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError('swiftc: ' + (r.stderr.strip().splitlines() or ['Fehler'])[-1])
        self.p = subprocess.Popen([str(binaer)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        hallo = self._lies(30)
        if not hallo.get('bereit'):
            raise RuntimeError('WebKit-Treiber startet nicht: ' + str(hallo))
        self.user_agent = hallo.get('userAgent') or ''

    def _lies(self, frist=90):
        import select
        bereit, _, _ = select.select([self.p.stdout], [], [], frist)
        if not bereit:
            raise TimeoutError('WebKit-Treiber antwortet nicht')
        zeile = self.p.stdout.readline()
        if not zeile:
            raise RuntimeError('WebKit-Treiber hat sich beendet')
        return json.loads(zeile)

    def _befehl(self, **d):
        self.p.stdin.write(json.dumps(d, ensure_ascii=False) + '\n')
        self.p.stdin.flush()
        a = self._lies()
        if not a.get('ok'):
            raise RuntimeError(a.get('error') or 'Fehler')
        return a.get('value')

    def navigiere(self, url):
        self._befehl(cmd='navigate', url=url)
        self.js(FEHLERSAMMLER)

    def js(self, script, *args):
        return self._befehl(cmd='js', script=script)

    def js_async(self, script):
        return self._befehl(cmd='js_async', script=script)

    def sichtbarkeit(self):
        return self._befehl(cmd='visibility')

    warte_bis = Safari.warte_bis
    fehler = Safari.fehler

    def bild(self, datei):
        self._befehl(cmd='screenshot', file=str(datei))

    def schliessen(self):
        try:
            self.p.stdin.write('{"cmd":"quit"}\n'); self.p.stdin.flush()
            self.p.wait(5)
        except Exception:
            self.p.kill()
        shutil.rmtree(self.ordner, ignore_errors=True)


def repo_zahl(sf):
    import re
    t = sf.js("return document.getElementById('info-repos').textContent")
    m = re.match(r'(\d+) Repos', t or '')
    return int(m.group(1)) if m else -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bilder', default=str(HIER / 'Pruefbilder-safari'))
    ap.add_argument('--schnell', action='store_true', help='ohne die 60-s-Wartezeit für visibilitychange')
    ap.add_argument('--wkwebview', action='store_true', help='WebKit direkt (WKWebView) statt Safari über safaridriver')
    a = ap.parse_args()
    if a.wkwebview and a.bilder == str(HIER / 'Pruefbilder-safari'):
        a.bilder = str(HIER / 'Pruefbilder-webkit')
    bilder = pathlib.Path(a.bilder)
    bilder.mkdir(parents=True, exist_ok=True)
    passwort = passwort_finden()

    tmp = pathlib.Path(tempfile.mkdtemp(prefix='dm-safari-'))
    docs = tmp / 'docs'
    shutil.copytree(DOCS, docs)
    idx, vid, k = tresor_schluessel(docs, passwort)
    port = freier_port()
    server = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', str(docs)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    basis = f'http://127.0.0.1:{port}/'
    time.sleep(0.6)
    probleme = []
    sf = None
    try:
        sf = WebKitTreiber() if a.wkwebview else Safari()
        version = sf.js('return navigator.userAgent')
        print(f'{"WKWebView" if a.wkwebview else "Safari"} (WebKit): {version}')
        if a.wkwebview:
            print(f'  Sichtbarkeit des Dokuments: {sf.sichtbarkeit()}')
        else:
            try:
                sf.befehl('POST', '/window/rect', {'width': 480, 'height': 920})
            except Exception:
                pass

        def melde(schritt, ok, info=''):
            print(f"  {'✅' if ok else '❌'} {schritt}{(' — ' + info) if info else ''}")
            if not ok:
                probleme.append(f'{schritt} {info}')

        def js_fehler(wo):
            for e in sf.fehler():
                melde('JS-Fehler ' + wo, False, str(e))

        def toast_mit(muster, frist=25):
            return sf.warte_bis(f"var t=document.getElementById('toast'); return t.classList.contains('zeig') && t.textContent.indexOf({json.dumps(muster)})>=0 ? t.textContent : ''", frist=frist)

        def knopf_frei():
            sf.warte_bis("return !document.getElementById('knopf-aktualisieren').disabled", frist=15)

        # Anmelden, angemeldet bleiben
        sf.navigiere(basis)
        time.sleep(0.8)
        sf.js(f"document.getElementById('login-merken').checked=true; document.getElementById('login-pw').value={json.dumps(passwort)}; document.getElementById('login-form').requestSubmit();")
        sf.warte_bis(APP_SICHTBAR, frist=40)
        time.sleep(1.0)
        stand0 = sf.js("return document.getElementById('kopf-stand').textContent")
        melde('Anmeldung → App, Stand im Kopf', bool(stand0), stand0)
        melde('Knopf ↻ sichtbar', bool(sf.js("var b=document.getElementById('knopf-aktualisieren'); var r=b.getBoundingClientRect(); return r.width>=36 && r.height>=36 && !b.disabled")))
        sw = sf.js_async("var cb=arguments[arguments.length-1]; if(!('serviceWorker' in navigator)){cb('kein SW');return;} navigator.serviceWorker.ready.then(r=>cb(r.active?'aktiv':'nicht aktiv')).catch(e=>cb('Fehler '+e)); setTimeout(()=>cb('Zeit'),8000);")
        melde('Service Worker in Safari', sw == 'aktiv', str(sw))
        sf.bild(bilder / 'safari-01-start.png')

        # 1) ↻ ohne Änderung
        sf.js("document.getElementById('knopf-aktualisieren').click()")
        t = toast_mit('Schon aktuell')
        melde('↻ ohne Änderung → „Schon aktuell“', 'Schon aktuell' in t and sf.js("return document.getElementById('kopf-stand').textContent") == stand0, t)
        knopf_frei()
        js_fehler('(Schon aktuell)')
        time.sleep(4.5)

        # 2) simulierte Veröffentlichung → ↻
        repos_vorher = repo_zahl(sf)

        def aenderung1(m):
            neue_simulation(m)
            neues_repo('pruefung-refresh-repo')(m)
        jetzt1 = veroeffentliche(docs, vid, k, aenderung1)
        sf.js("document.getElementById('knopf-aktualisieren').click()")
        t = toast_mit('Aktualisiert')
        melde('↻ nach Veröffentlichung → „Aktualisiert … 2 neue Einträge“', '2 neue Einträge' in t, t)
        knopf_frei()
        stand1 = sf.js("return document.getElementById('kopf-stand').textContent")
        melde('Stand im Kopf erneuert', stand1 != stand0 and jetzt1[11:16] in stand1, f'{stand0} → {stand1}')
        melde('Repo-Zahl +1', repo_zahl(sf) == repos_vorher + 1, f'{repos_vorher} → {repo_zahl(sf)}')
        sf.js("document.querySelector('#kacheln button[data-ansicht=simulationen]').click()")
        time.sleep(0.3)
        drin = sf.js("return [...document.querySelectorAll('#liste-simulationen .z-titel')].some(z => z.textContent.indexOf('Prüfung Refresh') >= 0)")
        melde('Neue Simulation steht in der Liste', bool(drin), sf.js("return document.getElementById('info-simulationen').textContent"))
        sf.bild(bilder / 'safari-02-aktualisiert.png')
        schluessel = sf.js_async("var cb=arguments[arguments.length-1]; caches.open('dm-v2').then(c=>c.keys()).then(ks=>cb(ks.map(k=>k.url))).catch(e=>cb(['Fehler '+e]));") or []
        mit_zusatz = [u for u in schluessel if '?' in u]
        melde('Service-Worker-Cache ohne ?t=-Einträge', not mit_zusatz and any(u.endswith('/vaults/index.json') for u in schluessel),
              f'{len(schluessel)} Einträge' + (', mit Zusatz: ' + ', '.join(mit_zusatz[:3]) if mit_zusatz else ''))
        js_fehler('(Aktualisiert)')
        time.sleep(4.5)

        # 3) still über „online“
        veroeffentliche(docs, vid, k, neues_repo('pruefung-refresh-repo-2'))
        sf.js("window.dispatchEvent(new Event('online'))")
        t = toast_mit('1 neuer Eintrag')
        melde('Stille Aktualisierung (Ereignis „online“)', '1 neuer Eintrag' in t and repo_zahl(sf) == repos_vorher + 2, t)
        melde('Ansicht Simulationen bleibt offen', bool(sf.js("return !document.getElementById('ansicht-simulationen').classList.contains('versteckt')")))
        js_fehler('(online)')
        time.sleep(4.5)

        # 3b) still über „visibilitychange“ (Zurückkehren in die App) – gedrosselt auf 60 s nach der letzten Prüfung.
        #     Die Seite prüft nur, wenn sie wirklich sichtbar ist (document.visibilityState) – sonst Schritt überspringen.
        erwartet = repos_vorher + 2
        sichtbar = sf.js("return document.visibilityState") == 'visible'
        if not a.schnell and not sichtbar:
            print('  – visibilitychange-Schritt übersprungen: das Prüffenster gilt als „hidden“ (die Seite prüft nur sichtbar)')
        if not a.schnell and sichtbar:
            veroeffentliche(docs, vid, k, neues_repo('pruefung-refresh-repo-sichtbar'))
            sf.js("document.dispatchEvent(new Event('visibilitychange'))")
            time.sleep(2.0)
            melde('visibilitychange kurz nach der letzten Prüfung löst nichts aus (Drossel)', repo_zahl(sf) == erwartet, f'{repo_zahl(sf)} Repos')
            print('  … warte 61 s (Drossel der stillen Prüfung)')
            time.sleep(61)
            sf.js("document.dispatchEvent(new Event('visibilitychange'))")
            t = toast_mit('1 neuer Eintrag')
            erwartet += 1
            melde('Stille Aktualisierung (Ereignis „visibilitychange“ am Dokument)', '1 neuer Eintrag' in t and repo_zahl(sf) == erwartet, t)
            js_fehler('(visibilitychange)')
            time.sleep(4.5)

        # 4) Neustart mit gespeicherter Sitzung
        veroeffentliche(docs, vid, k, neues_repo('pruefung-refresh-repo-3'))
        erwartet += 1
        sf.navigiere(basis)
        sf.warte_bis(APP_SICHTBAR, frist=40)
        time.sleep(1.0)
        melde('Neustart: gespeicherte Sitzung, neuer Stand ohne Anmeldung', repo_zahl(sf) == erwartet, f'{repo_zahl(sf)} Repos · ' + sf.js("return document.getElementById('kopf-stand').textContent"))
        build = json.loads((docs / 'vaults' / 'index.json').read_text())['build']
        melde('Neustart: Build der Sitzung gespeichert', bool(sf.js(f"return JSON.parse(localStorage.getItem('dm_sitzung')).build === {json.dumps(build)}")))
        sf.js("document.getElementById('knopf-aktualisieren').click()")
        t = toast_mit('Schon aktuell')
        melde('Nach Neustart ↻ → „Schon aktuell“', 'Schon aktuell' in t, t)
        knopf_frei()
        js_fehler('(Neustart)')
        time.sleep(4.5)

        # 5) Tresor neu verschlüsselt
        idx_pfad = docs / 'vaults' / 'index.json'
        idx2 = json.loads(idx_pfad.read_text(encoding='utf-8'))
        idx2['vaults'][0]['id'] = 'ffffffffffffffff'
        idx2['vaults'][0]['manifest'] = 'vaults/ffffffffffffffff/m.enc'
        idx2['build'] = secrets.token_hex(6)
        idx_pfad.write_text(json.dumps(idx2, ensure_ascii=False, indent=1), encoding='utf-8')
        sf.js("document.getElementById('knopf-aktualisieren').click()")
        status = sf.warte_bis("var s=document.getElementById('login-status').textContent; return !document.getElementById('anmeldung').classList.contains('versteckt') && s ? s : ''", frist=25)
        melde('Tresor neu verschlüsselt → Anmeldeseite mit Hinweis', 'neu verschlüsselt' in status and not sf.js("return !!localStorage.getItem('dm_sitzung')"), status)
        sf.bild(bilder / 'safari-03-neu-verschluesselt.png')
        js_fehler('(neu verschlüsselt)')
    except Exception as ex:
        probleme.append(str(ex))
        print(f'  ❌ Abbruch: {ex}')
        if 'Remote Automation' in str(ex) or 'Entfernte Automation' in str(ex) or 'session not created' in str(ex):
            print('     → Safari: Menü „Entwickler“ → „Entfernte Automation erlauben“ einschalten (oder: safaridriver --enable).')
        try:
            if sf:
                sf.bild(bilder / 'safari-fehler.png')
        except Exception:
            pass
    finally:
        if sf:
            sf.schliessen()
        server.terminate()
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if probleme:
        print(f'❌ {len(probleme)} Problem(e):')
        for p in probleme:
            print('   ' + p)
        sys.exit(1)
    print(f'✅ Alle Prüfungen in Safari bestanden. Prüfbilder: {bilder}')


if __name__ == '__main__':
    main()
