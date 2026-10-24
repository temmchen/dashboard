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

**Aktualisieren (↻ oben rechts):** holt `vaults/index.json` und das Manifest frisch – mit Zusatz `?t=…`, also am
Zwischenspeicher von GitHub Pages (bis zu 10 Minuten) vorbei –, zeichnet bei neuem Build alle Listen neu und
meldet „Kein neuer Stand vom Mac · zuletzt veröffentlicht …“ oder „Aktualisiert · veröffentlicht … · n neue
Einträge“. ↻ holt nur, was der Mac veröffentlicht hat – neue Repos, Module, Präsentationen und Simulationen
veröffentlicht der **Portal-Wächter** am Mac alle 20 Minuten von selbst (`_Portal-Setup/portal-waechter.py`, seit
04.10.2026 auch für Dashboard Mobil; Ruhezeit 5 min in den drei Quellordnern). Dasselbe passiert still, wenn
die App wieder in den Vordergrund kommt (frühestens eine Minute nach der letzten Prüfung) oder das Netz
zurückkehrt; beim Start mit gespeicherter Sitzung wird der Build ohnehin abgeglichen. Wurde der Tresor neu
verschlüsselt (neues Passwort, `--neu-verschluesseln`), führt ↻ zur Anmeldung. ↻ prüft außerdem, ob es eine neue
Fassung der App selbst (index.html, sw.js) gibt, und lädt die Seite dann einmal neu – eine Web-App auf dem
Home-Bildschirm bleibt sonst tagelang bei der alten Fassung.

## Todo (seit 24.10.2026)

Ganz oben auf der Startseite steht ein Block **Todo**: Zähler als Ampel-Pillen („3 dringend“ rot · „12 offen“ gelb ·
„2 erledigt“ grün für gerade Abgehaktes), darunter die nächsten fünf Aufgaben (Streifen und Pille in der
Bereichsfarbe, Art-Symbol, Titel, Klasse/Fach, Fälligkeit „heute“, „morgen“, „Mo 27.10.“, „überfällig seit 2 Tagen“)
und „Alle anzeigen“; dazu eine eigene **Kachel Todo** in der Kachelreihe (✓, rosa Verlauf #FB7185 → #9F1239 wie die
Mac-Kachel, Zähler als Untertitel). **Ampel** je Aufgabe als Punkt vor dem Titel: rot = Priorität hoch, überfällig oder
heute fällig · gelb = offen, nicht dringend · grün = erledigt (gesendet). Die eigene Ansicht **Todo** (`…/dashboard/?b=todo`, „‹ Start“ zurück) hat oben eine Suche (Titel,
Notiz, Klasse, Fach, Tags), Filter-Chips je Bereich (Privat, CdM, Promotion, LTEtt – Mehrfachauswahl, gemerkt im Gerät
unter `localStorage` `dm-todo-filter`) und die Gruppen Überfällig · Heute · Morgen · Diese Woche (bis Sonntag) · Später ·
Ohne Datum. Karten: linker Streifen in Bereichsfarbe, ‼ bei Priorität hoch, Status „In Arbeit“/„Wartet“, Schritte
„☑ 2/5“ (erledigt/gesamt), Tippen klappt die Notiz auf. iPad (ab 740 px): Suche und Filter links, Liste rechts;
auf der Startseite die nächsten Aufgaben zweispaltig.

| | |
| --- | --- |
| **Quelle** | `KI/Todo/daten/todos.json` und `KI/Todo/kategorien.json` der Todo-App am Mac (Ordner nach Konvention neben der Quelle `simulationen`; sonst `zugangsdaten.json` → `todo`; für Testläufe Umgebungsvariable `DM_TODO` = Ordner mit einer Kopie). `daten/sicherungen/` wird nicht gelesen. |
| **Manifest** | Feld `todo`: `{stand, bereiche:[{id,name,kurz,farbe,symbol}], arten:{id:{name,symbol}}, aufgaben:[…], kategorien, rueckweg}` – nur offene Aufgaben (ohne `erledigt` und `geloescht`) mit `id, titel, notiz` (max. 300 Zeichen), `bereich, unter, fach, art, prio, faellig, status, tags, schritte:{offen,gesamt}`, sortiert nach Fälligkeit (ohne Datum zuletzt), dann Priorität. Fehlt todos.json: `todo: null`, der Block entfällt. |
| **Ohne Rückweg** | Fehlt `todo-rueckweg.json` (Manifest `todo.rueckweg: null`), ist die Ansicht nur lesend und zeigt die Anleitung „am Mac in Dashboard Pro → Kachel Todo → Menü → ‚Rückweg vom iPhone einrichten‘“. |
| **Veröffentlichung** | `veroeffentlichen.py` nimmt `todo/todos.json`, `todo/kategorien.json`, `todo/kategorien.py` und (nur Größe/Zeit) `geheim/todo-rueckweg.json` ins Inventar; eine Änderung macht `--pruefen` zu `OFFEN`, der **Portal-Wächter** veröffentlicht beim nächsten Lauf (alle 20 min). Sofort: Knopf „Mobil veröffentlichen“ der Todo-App (`POST /api/mobil`) oder `Dashboard Mobil veröffentlichen.command`; danach am Gerät ↻. Die Klartext-Prüfung sucht Titel und Notizen offener Aufgaben in `docs/` (außer im App-Code `index.html`/`sw.js`). |

### Rückweg: abhaken und erfassen am iPhone/iPad (seit 24.10.2026 abends)

Ist der Rückweg eingerichtet, hat jede Karte links einen runden **Haken**: Tippen → Karte grau/durchgestrichen,
„✓ gesendet“, 5 s lang **„Rückgängig“** (nimmt die Änderung aus der Warteschlange; war sie schon unterwegs, geht
`offen` hinterher). Aufgeklappt (Tippen auf die Karte): Notiz, **Verschieben** „Heute“ · „Morgen“ · „+1 Woche“ und
**Löschen** (Rückfrage; am Mac landet die Aufgabe im Papierkorb, 90 Tage wiederherstellbar). **„+ Aufgabe“** oben in
der Ansicht bzw. **+** im Startseiten-Block öffnet das Formular (iPhone: Blatt von unten, iPad: mittig): Bereich als
Farbknöpfe (zuletzt gewählter bleibt), Klasse/Modul/Teil als Auswahlrad (Beschriftung aus `unterLabel`, letzte Wahl je
Bereich gemerkt), bei LTEtt Fach (Fächer der Klasse zuerst, aus `faecherJeUnter`; hat die Klasse genau eines, ist es
vorgewählt), „Was ist zu tun?“ (Arten mit Symbol), Fälligkeit (Heute · Morgen · Diese Woche = Freitag · Nächste Woche =
Freitag · 📅 Datum · ohne; mit Stundenplan zusätzlich **„Nächste Stunde · Di 27.10.“** und „Übernächste“ aus
`kategorien.stunden[Klasse|Fach]` bzw. `[Klasse]`, automatisch gewählt, bis man selbst ein Datum antippt), Priorität,
Titel optional (leer → „Art · Klasse · Fach“ wie am Mac), Notiz. Neue Aufgaben (`id` `m-JJJJMMTT-<6 hex>`) stehen
sofort in der Liste, Pille **„ausstehend“** bis der Mac sie übernommen hat.

| | |
| --- | --- |
| **Ablauf** | Handy → `PUT https://api.github.com/repos/<repo>/contents/aenderungen/<JJJJMMTT-HHMMSS>-<6 hex>.json` ins **private** Repo `temmchen/todo-aenderungen` → am Mac holt `KI/Todo/abgleich.py` (launchd alle 5 min, außerdem beim Öffnen der Todo-App) die Dateien ab, wendet sie auf `todos.json` an (Mac gewinnt bei Konflikten), löscht sie im Repo und veröffentlicht Dashboard Mobil neu → das Handy sieht den übernommenen Stand nach ↻ bzw. beim nächsten Öffnen. |
| **Was gesendet wird** | Eine Datei je Sendevorgang mit allen wartenden Änderungen: `{"v":1, "zeit", "geraet", "aenderungen":[…]}` mit `{"typ":"neu","aufgabe":{id,titel,notiz,bereich,unter,fach,art,prio,faellig}}`, `{"typ":"erledigt"\|"offen"\|"loeschen","id"}`, `{"typ":"verschieben","id","faellig"}` (Vertrag: `RUECKWEG-VERTRAG.md` der Mac-Seite). Abhaken und Löschen werden kurz gesammelt (Rückgängig-Frist), Neues sofort gesendet. |
| **Warteschlange** | `localStorage` `dm-todo-ausstehend` (noch nicht gesendet) – bei Fehler/offline bleibt alles dort und geht beim nächsten Öffnen, bei Fokus/Rückkehr in die App oder wenn das Netz wiederkommt erneut raus. `dm-todo-gesendet`: gesendete Änderungen als Überlagerung, bis das Manifest sie enthält (Stand `todo.stand` neuer als die Sendezeit **und** Aufgabe fehlt bzw. ist da/hat das neue Datum); nach 3 Tagen verworfen. Statuszeile oben: „2 Änderungen warten · zuletzt gesendet 19:02 · 1 Änderung noch nicht am Mac übernommen“. |
| **Token** | Fein-granulares GitHub-Token nur für dieses eine Repo (Contents: Lesen/Schreiben) in `_Portal-Setup/geheim/todo-rueckweg.json` (`{"repo","token","seit"}`, angelegt von Dashboard Pro). `build.py` legt `{repo, token}` **nur ins verschlüsselte Manifest** (`todo.rueckweg`); `veroeffentlichen.py` bricht ab, wenn der Token-Wert irgendwo in `docs/` (auch im App-Code) oder in einer Datei im Git-Index im Klartext steht, und nimmt die Datei ins Inventar (neues/widerrufenes Token → Veröffentlichung). Testläufe: `DM_RUECKWEG=<Pfad>`. |
| **Kategorien** | `todo.kategorien` = `{bereiche:[{id,name,kurz,farbe,symbol,unterLabel,unter,faecher,faecherJeUnter}], arten:[…], prioritaeten:[…], stunden?}` aus `KI/Todo/kategorien.py` → `kategorien_laden()` (Klassen/Fächer aus Stundenplan und Référentiels); fehlt das Modul, direkt `kategorien.json`. |

## Zuordnung zu Klassen und Fächern (seit 05.10.2026)

Jede Simulation trägt unter dem Titel ihre **Zuordnung** (Klasse · Fach/Modul) als Chips – dieselbe Zuordnung,
die am Mac die Filemanager verwalten – und einen Knopf **„Zuordnung“**. Die Filter-Chips *Klasse* und *Fach*
richten sich danach.

| Quelle | Woher | Rang |
| --- | --- | --- |
| **auf diesem Gerät** (gestrichelt gelb) | Knopf „Zuordnung“ in der App: Klassen- und Fach-Chips antippen, jede Änderung wird sofort im Gerät gespeichert (`localStorage` `dm-zuordnung`) | gewinnt |
| **vom Mac** | `zuordnung.json` im Ordner der Simulation bzw. `Simulations-Filemanager/zuordnungen.json` für GitHub-Repos (`@github/<repo>`) – gepflegt in Dashboard Pro › Simulationen › Vorschau › „Zuordnung“; kommt mit der nächsten Veröffentlichung aufs Handy | danach |
| **automatisch** | Klasse/Fach aus Ordnerpfad, Repo-Name, Topics oder Beschreibung | Rückfall |

Die Chips des Editors sind die **Klassen und Module des Journal de Classe** (`manifest.klassenliste`, über
`zuordnung.py` des Simulations-Filemanagers gelesen), dazu „Allgemein“ und bereits zugeordnete Kürzel.
**„Wie am Mac“** löscht die Festlegung des Geräts; stimmt sie mit der veröffentlichten überein, verschwindet
sie von selbst. Die Festlegung am Gerät gilt nur dort (wie die Häkchen „gehalten“) – der Mac erfährt nichts
davon; für alle Geräte gilt der Weg über Dashboard Pro. `veroeffentlichen.py` erkennt geänderte
`zuordnungen.json`, `zuordnung.json` und Journal-Klassen als Änderung und baut dann neu.
Pfade nach Konvention neben der Quelle `simulationen` (KI-Ordner), sonst in `zugangsdaten.json` → `zuordnung`
(`modul`, `zentral`, `journal`).

## Alltag

```bash
/usr/bin/python3 veroeffentlichen.py              # pull · prüfen · bauen · Klartext-Prüfung · commit · push
/usr/bin/python3 veroeffentlichen.py --pruefen    # nur nachsehen: NICHTS-ZU-TUN / OFFEN (Portal-Wächter)
/usr/bin/python3 veroeffentlichen.py --erzwingen  # auch ohne Änderung (nach Passwort-/Code-Änderungen)
/usr/bin/python3 veroeffentlichen.py --nur-pruefung   # nur docs/ auf private Klartexte prüfen
/usr/bin/python3 build.py --liste                 # zeigen, was gefunden würde
```

Bequemer: Doppelklick auf `KI/Dashboard Mobil/Dashboard Mobil veröffentlichen.command`. Automatisch: der
**Portal-Wächter** (`_Portal-Setup/portal-waechter.py`, launchd alle 20 min) ruft `veroeffentlichen.py --pruefen`
auf und veröffentlicht bei `OFFEN` selbst – auch eine geänderte Repo-Liste; `gh` findet `build.py` dafür auch
ohne Homebrew im PATH (`/opt/homebrew/bin/gh`). Push-Daten der Portale (`repos.portale`) zählen nicht als
Änderung, sonst zöge jede Journal-Mobil-Veröffentlichung einen neuen Dashboard-Build nach sich.

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
├── build.py                    sammelt KI/Keynotes, KI/Lerndashboards, KI/Simulations, KI/Todo + Repo-Liste (gh) → docs/vaults/
├── veroeffentlichen.py         Ein-Klick-Veröffentlichung, --pruefen für den Wächter, Klartext-Prüfung
├── verwaltung.py               Zugänge, Passwörter, Passwort-Übersicht + QR
├── zugangsdaten.beispiel.json  Vorlage ohne echtes Passwort
├── werkzeuge/
│   ├── pruefen.py              Prüflauf in headless Chrome (iPhone, iPhone quer, iPad, Mac) mit Prüfbildern
│   ├── pruefung_refresh.py     Knopf ↻ mit simulierter Veröffentlichung (Temp-Kopie von docs/, Manifest neu verschlüsselt)
│   ├── pruefung_safari.py      dasselbe in WebKit: Safari über safaridriver oder --wkwebview (WKWebView, ohne Safari-Freigabe)
│   ├── webkit_treiber.swift    WKWebView als Prüf-Browser für pruefung_safari.py --wkwebview (swiftc)
│   └── symbole.py              zeichnet die App-Symbole (PNG) neu
└── docs/                       GitHub-Pages-Wurzel
    ├── index.html              Web-App: Anmeldung, Startseite (Todo, Kameras, Rechner, Kacheln), vier Bereiche + Todo mit Suche/Filtern, Aktualisieren ↻, Entschlüsseln, Übergabe
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
falsch/richtig, Startseite mit Rechnern und Kacheln, Knopf ↻ „Kein neuer Stand vom Mac“, GitHub mit Suche/Filter/QR, Präsentation
mit Touch-Leiste, Lerndashboard mit Suche und Verknüpfung `?d=…#/2/1`, Simulationen mit Klassen-Filter und mehrteiliger
Simulation über den Service Worker, Rückwege, Abmelden; Prüfbilder in `Pruefbilder/`). Ohne `zugangsdaten.json`
(Arbeitskopie) kommt das Passwort aus der Umgebungsvariable `DM_PASSWORT`.
`/usr/bin/python3 werkzeuge/pruefung_refresh.py [--schnell]` spielt den Knopf ↻ mit einer simulierten Veröffentlichung
durch (Temp-Kopie von docs/: Manifest entschlüsseln, Einträge anhängen, neu verschlüsseln, neuer Build → „Aktualisiert … 2
neue Einträge“, stille Aktualisierung über „online“ und – nach 61 s Wartezeit, ohne `--schnell` – „visibilitychange“,
Neustart mit gespeicherter Sitzung, Tresor neu verschlüsselt → Anmeldung).
Dasselbe in **WebKit**, der Engine von Safari auf iPhone und iPad: `werkzeuge/pruefung_safari.py --wkwebview` (WKWebView
über `webkit_treiber.swift`, braucht keine Freigabe; zeigt kurz ein Fenster) oder ohne `--wkwebview` in Safari selbst
(einmalig Safari → Entwickler → „Entfernte Automation erlauben“).

Lokal ansehen: `cd docs && /usr/bin/python3 -m http.server 8427 --bind 127.0.0.1` → http://127.0.0.1:8427/
(Direktes Öffnen der Datei per Doppelklick funktioniert nicht — `fetch()` und der Service Worker brauchen
http/https.) Einmalige Voraussetzung auf einem neuen Mac: `/usr/bin/python3 -m pip install --user cryptography`,
`gh auth login`, dann `KI/Dashboard Mobil/Dashboard Mobil einrichten.command`.

## Lizenz

Programmcode: MIT (siehe `LICENSE`). Die verschlüsselten Inhalte sind nicht Teil der Lizenz.
