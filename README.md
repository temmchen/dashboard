# 📱 Lerndashboards – iPhone- und iPad-Fassung

Verschlüsselte Web-Fassung der **Lerndashboards** von Tom Bleyer (LTEtt): je Modul ein interaktives
Lerndashboard als eine einzige HTML-Datei (Semesterplan, Stunden-Präsentationen mit Simulationen, Übungen,
Fragen zur Stunde). Am Mac laufen sie lokal aus OneDrive (`KI/Lerndashboards/`, Dashboard Pro → Kachel
„Lerndashboards“); hier liegen sie für **iPhone und iPad** auf **GitHub Pages** – obwohl dieses Repository
öffentlich ist, ausschließlich als **AES-256-GCM-Chiffrat** in `docs/vaults/`. Entschlüsselt wird erst im
Browser nach Eingabe des Passworts; die Seite tauscht sich dann gegen das Dashboard aus, das danach genau so
läuft wie am Mac (Wischen blättert, Tippen zeigt die Bedienleiste mit Lösung · Alle · Übersicht). Im Repo
steht kein Passwort und kein Klartext.

- Portal: https://temmchen.github.io/lerndashboards/
- Verknüpfung direkt in eine Stunde: `https://temmchen.github.io/lerndashboards/?d=prodi1-dp2et#/5/1`
  (`?d=` Kennung des Dashboards = Ordnername klein mit Bindestrichen, `#/Stunde/Folie` wie im Dashboard)
- Anleitung für den Alltag und Passwort: `KI/Lerndashboards Mobil/README.md` bzw. `KI/Passwoerter/` in OneDrive

## Was veröffentlicht wird

`build.py` geht durch die Unterordner von `KI/Lerndashboards/` (Feld `quelle` in `zugangsdaten.json`):

| Ordner enthält … | wird … |
| --- | --- |
| `github.json` mit `pages` | als **Link** auf die öffentliche GitHub-Pages-Seite gezeigt (Oszilloskop, Kompendium) |
| eine HTML-Datei oben im Ordner | **verschlüsselt** in den Tresor gelegt; Titel, Klasse, Modul, Stunden/Teile mit Datum kommen aus dem eingebetteten `<script id="meta">`, die Beschreibung aus `README.md` |
| weder noch (oder Name mit `.`/`_` vorn, oder in `optionen.ausschliessen`) | übersprungen |

Neue Module erscheinen also von selbst, sobald ihr Ordner in `KI/Lerndashboards/` liegt und einmal
veröffentlicht wurde. Die Übersicht zeigt je Dashboard die nächste Stunde (bzw. den nächsten Teil) mit
Startknopf.

## Alltag

Inhalte werden am Mac gepflegt (Quellcode → `build.sh` des Moduls). Veröffentlichen — nur wenn sich etwas geändert hat:

```bash
/usr/bin/python3 veroeffentlichen.py              # pull · prüfen · bauen · Klartext-Prüfung · commit · push
/usr/bin/python3 veroeffentlichen.py --pruefen    # nur nachsehen: NICHTS-ZU-TUN / OFFEN (Portal-Wächter)
/usr/bin/python3 veroeffentlichen.py --erzwingen  # auch ohne Änderung (nach Passwort-/Code-Änderungen)
/usr/bin/python3 veroeffentlichen.py --nur-pruefung   # nur docs/ auf private Klartexte prüfen
```

Bequemer: Doppelklick auf `KI/Lerndashboards Mobil/Lerndashboards veröffentlichen.command`.

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
lerndashboards/
├── build.py                    liest KI/Lerndashboards/ → verschlüsselt nach docs/vaults/
├── veroeffentlichen.py         Ein-Klick-Veröffentlichung, --pruefen für den Wächter, Klartext-Prüfung
├── verwaltung.py               Zugänge, Passwörter, Passwort-Übersicht + QR
├── zugangsdaten.beispiel.json  Vorlage ohne echtes Passwort
├── werkzeuge/
│   ├── pruefen.py              Prüflauf in headless Chrome (iPhone, iPhone quer, iPad, Mac) mit Prüfbildern
│   └── symbole.py              zeichnet die App-Symbole (PNG) neu
└── docs/                       GitHub-Pages-Wurzel
    ├── index.html              Web-App: Anmeldung, Übersicht, Entschlüsseln und Übergabe an das Dashboard
    ├── sw.js                   Service Worker: App-Hülle + Tresordateien offline
    ├── manifest.webmanifest, icons/
    └── vaults/                 index.json (Salts, eingewickelte Schlüssel) + <id>/m.enc + <id>/f/<id>.enc
```

Krypto: PBKDF2-HMAC-SHA256 (600 000 Iterationen, 16-B-Salt je Zugang) → AES-256-GCM; ein Tresor-Schlüssel,
je Datei eine Nonce; geänderte Dateien bekommen eine neue Zufalls-Kennung (deshalb darf das Gerät Dateien
dauerhaft zwischenspeichern). Inkrementeller Build über `.build-state.json`: unveränderte Dateien behalten
ihr Chiffrat byte-genau, die Git-Historie wächst nur um Neues. Gleiches Verfahren wie Journal Mobil,
Schuljahr- und CdM-Portal.

Übergabe an das Dashboard: Nach dem Entschlüsseln ersetzt `document.write()` die Portalseite durch die
HTML-Datei des Dashboards – Adresse bleibt `…/lerndashboards/?d=<Kennung>#/Stunde/Folie`, `localStorage`
(Häkchen „gehalten“, Team-Tracker) gehört damit zur Origin `temmchen.github.io` und bleibt je Gerät erhalten.
Das Portal fügt unten links (Startseite) bzw. in die Bedienleiste (Folien) den Knopf **‹ Lerndashboards**
ein, der zur Übersicht zurückführt. Die Referentenansicht (Taste S) öffnet wie am Mac ein zweites Fenster.

Prüfen: `/usr/bin/python3 werkzeuge/pruefen.py` (Anmeldung falsch/richtig, Übersicht, Dashboards öffnen,
Verknüpfung `?d=…#/2/1`, Rückweg, Abmelden; Prüfbilder in `Pruefbilder/`).

Lokal ansehen: `cd docs && /usr/bin/python3 -m http.server 8427 --bind 127.0.0.1` → http://127.0.0.1:8427/
(Direktes Öffnen der Datei per Doppelklick funktioniert nicht — `fetch()` und der Service Worker brauchen
http/https.) Einmalige Voraussetzung auf einem neuen Mac: `/usr/bin/python3 -m pip install --user cryptography`,
dann `KI/Lerndashboards Mobil/Lerndashboards einrichten.command`.

## Lizenz

Programmcode: MIT (siehe `LICENSE`). Die verschlüsselten Unterrichtsinhalte sind nicht Teil der Lizenz.
