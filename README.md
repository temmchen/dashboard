# 📱 Dashboard Mobil – Repos, Präsentationen, Lerndashboards und Simulationen auf iPhone und iPad

Verschlüsselte iPhone/iPad-Fassung des Dashboards von Tom Bleyer (LTEtt). Am Mac bündelt Dashboard Pro die
Kacheln GitHub, Präsentationen, Lerndashboards und Simulationen; hier gibt es dieselben vier Bereiche als
Web-App auf **GitHub Pages** – obwohl dieses Repository öffentlich ist, ausschließlich als
**AES-256-GCM-Chiffrat** in `docs/vaults/`. Entschlüsselt wird erst im Browser nach Eingabe des Passworts.
Im Repo steht kein Passwort und kein Klartext.

- Portal: https://temmchen.github.io/dashboard/
- Verknüpfung direkt in einen Eintrag: `https://temmchen.github.io/dashboard/?d=prodi1-dp2et#/5/1`
  (`?d=` Kennung des Eintrags, `#…` Anker des Dashboards bzw. der Präsentation)
- Anleitung für den Alltag und Passwort: `KI/Dashboard Mobil/README.md` bzw. `KI/Passwoerter/` in OneDrive

## Startseite und die vier Bereiche

Nach der Anmeldung zeigt die **Startseite** oben die **Rechner** (`rechner` in zugangsdaten.json, z. B. fx-991DE X
Trainer und RPN42: „Öffnen“ und QR-Code) und darunter vier **Kacheln** wie in Dashboard Pro. Jeder Bereich hat
oben eine **Suche** und **Filter-Chips** (Klasse, bei Simulationen zusätzlich Fach) wie die Filemanager am Mac;
„‹ Start“ führt zurück zur Startseite. Verknüpfung direkt in einen Bereich: `…/dashboard/?b=simulationen`.

| Kachel | Quelle | Was die App zeigt |
| --- | --- | --- |
| **Lerndashboards** | `KI/Lerndashboards/<Ordner>/*.html`; Ordner mit `github.json` + `pages` nur als Link | Karten mit nächster Stunde und „Stunde N starten“; Kompendium und Oszilloskop als öffentliche Links |
| **Simulationen** | `KI/Simulations/Jahr/Klasse/Fach/…/*.html` (ohne `_`-Seiten, build/, Quellcode/) und die öffentlichen Simulations-Repos | Zeilen gruppiert nach Klasse · Fach · Thema, darunter „GitHub Pages“ (Klasse und Fach aus Repo-Name und Topics) mit QR |
| **Präsentationen** | `KI/Keynotes/<Ordner>/*.html` (eine Datei, Filme eingebaut) | Karten mit Klassen, Folien- und Filmzahl; öffnen = Präsentation im Vollbild mit Touch-Leiste (‹ › · Übersicht · Auflösung · Vollbild) |
| **GitHub** | `gh api user/repos` beim Bauen (alle eigenen Repos, auch private) | Liste mit Suche und Filtern (Webseite · Simulationen · Portale · Privat · Archiv), Knöpfe „Seite öffnen“, „GitHub“, **QR-Code** bildschirmfüllend (für den Beamer) |

Verweist eine Simulation auf Dateien neben sich (css/, js/ …), kommt ihr ganzer Ordner verschlüsselt mit; der
Service Worker liefert ihn unter `d/<Kennung>/…` entschlüsselt aus. Alle anderen Einträge sind eine
einzige HTML-Datei: nach dem Entschlüsseln ersetzt `document.write()` die Portalseite durch sie – Adresse
bleibt `…/dashboard/?d=<Kennung>#…`, `localStorage` (Häkchen „gehalten“, Team-Tracker) gehört damit zur
Origin `temmchen.github.io` und bleibt je Gerät erhalten. Überall eingefügt: der Knopf **‹ Dashboard**
(Bedienleiste der Lerndashboards, Touch-Leiste der Präsentationen, sonst unten links).

Neue Module, Präsentationen und Simulationen erscheinen von selbst, sobald ihr Ordner in OneDrive liegt und
einmal veröffentlicht wurde; die Repo-Liste wird bei jeder Veröffentlichung neu geholt.

## Alltag

```bash
/usr/bin/python3 veroeffentlichen.py              # pull · prüfen · bauen · Klartext-Prüfung · commit · push
/usr/bin/python3 veroeffentlichen.py --pruefen    # nur nachsehen: NICHTS-ZU-TUN / OFFEN (Portal-Wächter)
/usr/bin/python3 veroeffentlichen.py --erzwingen  # auch ohne Änderung (nach Passwort-/Code-Änderungen)
/usr/bin/python3 veroeffentlichen.py --nur-pruefung   # nur docs/ auf private Klartexte prüfen
/usr/bin/python3 build.py --liste                 # zeigen, was gefunden würde
```

Bequemer: Doppelklick auf `KI/Dashboard Mobil/Dashboard Mobil veröffentlichen.command`.

## Zugänge

```bash
/usr/bin/python3 verwaltung.py liste
/usr/bin/python3 verwaltung.py passwort "Tom"            # neu würfeln, Tresor neu verschlüsseln
/usr/bin/python3 verwaltung.py setzen "Tom" "wunsch-passwort"
/usr/bin/python3 verwaltung.py zugang "iPad"             # weiterer Zugang mit eigenem Passwort
/usr/bin/python3 verwaltung.py entfernen "iPad"
/usr/bin/python3 verwaltung.py readme                    # PASSWOERTER.md + QR-Code in OneDrive neu schreiben
```

`zugangsdaten.json` liegt **nur lokal** (Verknüpfung nach OneDrive `_Portal-Setup/geheim/`, gitignored).
Passwörter werden vor der Schlüsselableitung normalisiert (NFC, Enden getrimmt, Kleinschreibung) – die
iPhone-Tastatur darf also groß schreiben.

## Technik

```
dashboard/
├── build.py                    sammelt KI/Keynotes, KI/Lerndashboards, KI/Simulations + Repo-Liste (gh) → docs/vaults/
├── veroeffentlichen.py         Ein-Klick-Veröffentlichung, --pruefen für den Wächter, Klartext-Prüfung
├── verwaltung.py               Zugänge, Passwörter, Passwort-Übersicht + QR
├── zugangsdaten.beispiel.json  Vorlage ohne echtes Passwort
├── werkzeuge/
│   ├── pruefen.py              Prüflauf in headless Chrome (iPhone, iPhone quer, iPad, Mac) mit Prüfbildern
│   └── symbole.py              zeichnet die App-Symbole (PNG) neu
└── docs/                       GitHub-Pages-Wurzel
    ├── index.html              Web-App: Anmeldung, Startseite (Rechner, Kacheln), vier Bereiche mit Suche/Filtern, Entschlüsseln, Übergabe
    ├── sw.js                   Service Worker: App-Hülle + Tresordateien offline, d/<Kennung>/… entschlüsselt ausliefern
    ├── manifest.webmanifest, icons/
    └── vaults/                 index.json (Salts, eingewickelte Schlüssel) + <id>/m.enc + <id>/f/<id>.enc
```

Krypto: PBKDF2-HMAC-SHA256 (600 000 Iterationen, 16-B-Salt je Zugang) → AES-256-GCM; ein Tresor-Schlüssel,
je Datei eine Nonce; geänderte Dateien bekommen eine neue Zufalls-Kennung (deshalb darf das Gerät Dateien
dauerhaft zwischenspeichern). Inkrementeller Build über `.build-state.json`: unveränderte Dateien behalten
ihr Chiffrat byte-genau, die Git-Historie wächst nur um Neues. Gleiches Verfahren wie Journal Mobil,
Schuljahr- und CdM-Portal. Der Service Worker bekommt den Tresor-Schlüssel nach der Anmeldung per Nachricht;
mit „angemeldet bleiben“ merkt er ihn in IndexedDB (sonst nur im Speicher – nach einem Neustart des Workers
leitet `d/…` zur Anmeldung um und danach wieder zurück).

Prüfen: `/usr/bin/python3 werkzeuge/pruefen.py [--geraet iphone|ipad|mac|alle] [--url …]` (Anmeldung
falsch/richtig, Startseite mit Rechnern und Kacheln, GitHub mit Suche/Filter/QR, Präsentation mit Touch-Leiste,
Lerndashboard mit Suche und Verknüpfung `?d=…#/2/1`, Simulationen mit Klassen-Filter und mehrteiliger Simulation über
den Service Worker, Rückwege, Abmelden; Prüfbilder in `Pruefbilder/`).

Lokal ansehen: `cd docs && /usr/bin/python3 -m http.server 8427 --bind 127.0.0.1` → http://127.0.0.1:8427/
(Direktes Öffnen der Datei per Doppelklick funktioniert nicht — `fetch()` und der Service Worker brauchen
http/https.) Einmalige Voraussetzung auf einem neuen Mac: `/usr/bin/python3 -m pip install --user cryptography`,
`gh auth login`, dann `KI/Dashboard Mobil/Dashboard Mobil einrichten.command`.

## Lizenz

Programmcode: MIT (siehe `LICENSE`). Die verschlüsselten Inhalte sind nicht Teil der Lizenz.
