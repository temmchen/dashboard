/* Dashboard Mobil – Service Worker
   Aufgaben
   1. App-Hülle (HTML, Icons) offline halten, verschlüsselte Tresordateien zwischenspeichern.
      Alles bleibt verschlüsselt im Cache; entschlüsselt wird nur mit dem Tresor-Schlüssel,
      den die Seite nach der Anmeldung schickt (Nachricht {typ:"tresor"}).
   2. Mehrteilige Einträge (Simulationen mit css/, js/ …) entschlüsselt ausliefern:
      Adressen unter <scope>d/<Kennung>/<Datei> werden aus vaults/<id>/f/<fid>.enc
      entschlüsselt beantwortet – mit Range-Unterstützung (Video, PDF) und dem
      Rückweg-Knopf in HTML-Seiten.

   Strategien
   - Hülle, Index und Manifest: network-first, Cache als Rückfall. Die Seite holt Index und
     Manifest mit frischer Adresse (?t=…, gegen den Zwischenspeicher von GitHub Pages); im Cache
     liegt die Antwort trotzdem unter der Adresse ohne Zusatz – ein Eintrag je Datei.
   - Tresordateien (vaults/…/f/….enc): cache-first – die Kennung (fid) ändert sich,
     sobald der Inhalt sich ändert, der Cache kann also nie veralten.
   - Fremde Origins werden nicht angefasst.

   Der Tresor-Schlüssel liegt nur im Speicher dieses Workers; mit „angemeldet bleiben“ zusätzlich
   in IndexedDB (wie die Sitzung der Seite in localStorage), damit er einen Neustart des Workers
   überlebt. Ohne Schlüssel leitet d/… zur Anmeldeseite um (?d=<Kennung>&r=<Datei>). */

const CACHE = "dm-v2";
const HUELLE = [
  "./", "./index.html", "./manifest.webmanifest",
  "./icons/icon-180.png", "./icons/icon-192.png", "./icons/icon-512.png"
];
const MIME = {
  html: "text/html; charset=utf-8", htm: "text/html; charset=utf-8", js: "text/javascript; charset=utf-8",
  mjs: "text/javascript; charset=utf-8", css: "text/css; charset=utf-8", json: "application/json; charset=utf-8",
  svg: "image/svg+xml", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", webp: "image/webp",
  ico: "image/x-icon", woff: "font/woff", woff2: "font/woff2", ttf: "font/ttf", otf: "font/otf",
  mp4: "video/mp4", webm: "video/webm", mp3: "audio/mpeg", m4a: "audio/mp4", wav: "audio/wav", vtt: "text/vtt",
  pdf: "application/pdf", txt: "text/plain; charset=utf-8", md: "text/markdown; charset=utf-8",
  csv: "text/csv; charset=utf-8", xml: "application/xml"
};

const tresore = new Map();          // vid → {key: CryptoKey, roh: Uint8Array, dateien: {"<id>/<rel>": fid}}
const klar = new Map();             // fid → ArrayBuffer (zuletzt entschlüsselte Dateien, für Range-Anfragen)
let klarBytes = 0;
const KLAR_MAX = 64 * 1024 * 1024;

/* ─────────────────────────── Installation ─────────────────────────── */
self.addEventListener("install", ev => {
  ev.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await Promise.all(HUELLE.map(async p => {
      try { await cache.add(new Request(p, { cache: "reload" })); } catch (e) { /* offline o. ä. */ }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", ev => {
  ev.waitUntil((async () => {
    const namen = await caches.keys();
    await Promise.all(namen.filter(n => n !== CACHE).map(n => caches.delete(n)));
    try {                                                  // Altlasten: Einträge mit ?…-Zusatz (frühere Fassung)
      const cache = await caches.open(CACHE);
      for (const r of await cache.keys()) if (r.url.includes("?")) await cache.delete(r);
    } catch (e) { /* egal */ }
    await self.clients.claim();
  })());
});

/* ─────────────────────────── IndexedDB (nur mit „angemeldet bleiben“) ─────────────────────────── */
function idb() {
  return new Promise((res, rej) => {
    const o = indexedDB.open("dm-sw", 1);
    o.onupgradeneeded = () => o.result.createObjectStore("tresor");
    o.onsuccess = () => res(o.result);
    o.onerror = () => rej(o.error);
  });
}
async function idbSchreiben(k, v) {
  const db = await idb();
  return new Promise((res, rej) => {
    const t = db.transaction("tresor", "readwrite");
    t.objectStore("tresor").put(v, k);
    t.oncomplete = () => res();
    t.onerror = () => rej(t.error);
  });
}
async function idbAlle() {
  const db = await idb();
  return new Promise((res, rej) => {
    const t = db.transaction("tresor", "readonly");
    const r = t.objectStore("tresor").getAll();
    r.onsuccess = () => res(r.result || []);
    r.onerror = () => rej(r.error);
  });
}
async function idbLeeren() {
  const db = await idb();
  return new Promise((res, rej) => {
    const t = db.transaction("tresor", "readwrite");
    t.objectStore("tresor").clear();
    t.oncomplete = () => res();
    t.onerror = () => rej(t.error);
  });
}

/* ─────────────────────────── Nachrichten der Seite ─────────────────────────── */
async function tresorAufnehmen(d, merken) {
  const roh = d.k instanceof Uint8Array ? d.k : new Uint8Array(d.k);
  const key = await crypto.subtle.importKey("raw", roh, { name: "AES-GCM" }, false, ["decrypt"]);
  tresore.set(d.vid, { key, roh, dateien: d.dateien || {} });
  if (merken) {
    try { await idbSchreiben(d.vid, { vid: d.vid, k: roh, dateien: d.dateien || {} }); } catch (e) { /* kein IndexedDB */ }
  }
}
self.addEventListener("message", ev => {
  const d = ev.data || {};
  const antwort = typ => { try { ev.source && ev.source.postMessage({ typ }); } catch (e) { /* egal */ } };
  if (d.typ === "tresor") {
    ev.waitUntil((async () => {
      try { await tresorAufnehmen(d, !!d.merken); antwort("tresor-ok"); }
      catch (e) { antwort("tresor-fehler"); }
    })());
  } else if (d.typ === "vergessen") {
    tresore.clear(); klar.clear(); klarBytes = 0;
    ev.waitUntil(idbLeeren().catch(() => {}).then(() => antwort("vergessen-ok")));
  }
});

/* ─────────────────────────── Hilfen ─────────────────────────── */
function relPfad(url) {
  const scope = self.registration.scope;                // z. B. https://…/dashboard/
  return url.href.startsWith(scope) ? url.href.slice(scope.length).split("?")[0].split("#")[0] : null;
}
const istTresordatei = p => /^vaults\/[^/]+\/f\/[^/]+\.enc$/.test(p);
const istHuelle = p =>
  p === "" || p === "index.html" || p === "manifest.webmanifest" || p === "sw.js" ||
  p.startsWith("icons/") ||
  p === "vaults/index.json" || /^vaults\/[^/]+\/m\.enc$/.test(p);
const mimeVon = p => MIME[(p.split(".").pop() || "").toLowerCase()] || "application/octet-stream";

async function tresorFuer(schluessel) {
  for (const [vid, t] of tresore) if (t.dateien[schluessel]) return { vid, t, fid: t.dateien[schluessel] };
  // Worker neu gestartet? Schlüssel aus IndexedDB nachladen (nur mit „angemeldet bleiben“).
  try {
    for (const g of await idbAlle()) {
      if (!tresore.has(g.vid)) await tresorAufnehmen(g, false);
    }
  } catch (e) { /* kein IndexedDB */ }
  for (const [vid, t] of tresore) if (t.dateien[schluessel]) return { vid, t, fid: t.dateien[schluessel] };
  return null;
}

async function entschluesselt(vid, t, fid) {
  const alt = klar.get(fid);
  if (alt) return alt;
  const antwort = await cacheFirst(new Request(new URL(`vaults/${vid}/f/${fid}.enc`, self.registration.scope).href));
  if (!antwort || !antwort.ok) throw new Error("Tresordatei fehlt (" + (antwort && antwort.status) + ")");
  const bytes = new Uint8Array(await antwort.arrayBuffer());
  if (bytes.length < 13) throw new Error("Datei beschädigt");
  const puffer = await crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.slice(0, 12) }, t.key, bytes.slice(12));
  klar.set(fid, puffer); klarBytes += puffer.byteLength;
  while (klarBytes > KLAR_MAX && klar.size > 1) {         // ältesten Eintrag verwerfen
    const [erst, p] = klar.entries().next().value;
    klar.delete(erst); klarBytes -= p.byteLength;
  }
  return puffer;
}

/* Rückweg-Knopf für ausgelieferte HTML-Seiten (gleiche Logik wie in docs/index.html). */
function rueckwegHtml() {
  const basis = self.registration.scope;
  const ziel = JSON.stringify(basis);
  return `
<style id="dm-css">
#dm-portal{position:fixed;z-index:60;bottom:calc(env(safe-area-inset-bottom,0px) + 12px);left:calc(env(safe-area-inset-left,0px) + 12px);display:none;align-items:center;gap:6px;height:32px;padding:0 12px;border-radius:16px;border:1px solid rgba(255,255,255,.16);background:rgba(7,10,18,.78);color:#aab4c6;font:600 12.5px/1 -apple-system,BlinkMacSystemFont,"SF Pro Text",sans-serif;text-decoration:none;-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px)}
body.mode-dash #dm-portal,#dm-portal.dm-immer{display:inline-flex}
#dm-portal:hover{color:#fff;border-color:rgba(255,255,255,.32)}
#dm-bar{position:fixed;z-index:60;left:50%;bottom:calc(env(safe-area-inset-bottom,0px) + 14px);transform:translateX(-50%);display:flex;flex-wrap:wrap;justify-content:center;gap:6px;max-width:96vw;padding:6px;border-radius:16px;border:1px solid rgba(255,255,255,.14);background:rgba(7,10,18,.8);-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);opacity:0;pointer-events:none;transition:opacity .25s}
#dm-bar.an{opacity:1;pointer-events:auto}
#dm-bar button{display:inline-flex;align-items:center;gap:6px;height:40px;padding:0 13px;border-radius:11px;border:none;background:transparent;color:#aab4c6;font:650 14px -apple-system,BlinkMacSystemFont,"SF Pro Text",sans-serif;cursor:pointer}
#dm-bar button:hover{background:rgba(255,255,255,.08);color:#fff}
@media (max-width:640px){#ctrl{flex-wrap:wrap;justify-content:center;max-width:96vw}}
@media print{#dm-portal,#dm-bar{display:none!important}}
</style>
<a id="dm-portal" href="${basis.replace(/"/g, "&quot;")}" title="Zurück zum Dashboard">‹ Dashboard</a>
<script>(function(){var ziel=${ziel};function zurueck(e){e.preventDefault();e.stopPropagation();location.replace(ziel);}
var a=document.getElementById('dm-portal');if(a)a.addEventListener('click',zurueck);
var c=document.getElementById('ctrl');
if(c){var k=document.createElement('button');k.type='button';k.title='Zurück zum Dashboard';k.innerHTML='<svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/><path d="M4 12h16"/></svg>Dashboard';k.addEventListener('click',zurueck);c.insertBefore(k,c.firstChild);}
else if(window.KI&&document.querySelector('section.slide')){var b=document.createElement('div');b.id='dm-bar';
var defs=[['‹ Dashboard',null],['‹','ArrowLeft'],['›','ArrowRight'],['Übersicht','o'],['Auflösung','a'],['Vollbild','f']];
defs.forEach(function(d){var x=document.createElement('button');x.type='button';x.textContent=d[0];x.addEventListener('click',function(e){e.stopPropagation();if(!d[1]){zurueck(e);return;}document.dispatchEvent(new KeyboardEvent('keydown',{key:d[1],bubbles:true,cancelable:true}));zeig();});b.appendChild(x);});
document.body.appendChild(b);var t;function zeig(){b.classList.add('an');clearTimeout(t);t=setTimeout(function(){b.classList.remove('an');},2800);}
window.addEventListener('touchstart',zeig,{passive:true});window.addEventListener('mousemove',zeig);zeig();}
else if(a){a.classList.add('dm-immer');}
})();<\/script>
`;
}

function mitRueckweg(puffer) {
  let html = new TextDecoder().decode(puffer);
  const i = html.lastIndexOf("</body>");
  const zusatz = rueckwegHtml();
  html = i >= 0 ? html.slice(0, i) + zusatz + html.slice(i) : html + zusatz;
  return new TextEncoder().encode(html).buffer;
}

function antwortMitBereich(req, puffer, mime) {
  const gesamt = puffer.byteLength;
  const kopf = { "Content-Type": mime, "Accept-Ranges": "bytes", "Cache-Control": "no-store" };
  const r = req.headers.get("range");
  if (r) {
    const m = /bytes=(\d*)-(\d*)/.exec(r);
    if (m) {
      let a = m[1] ? +m[1] : 0, b = m[2] ? +m[2] : gesamt - 1;
      if (!m[1] && m[2]) { a = Math.max(0, gesamt - +m[2]); b = gesamt - 1; }
      if (a >= gesamt) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${gesamt}` } });
      b = Math.min(b, gesamt - 1);
      const teil = puffer.slice(a, b + 1);
      return new Response(teil, { status: 206, headers: { ...kopf, "Content-Range": `bytes ${a}-${b}/${gesamt}`, "Content-Length": String(teil.byteLength) } });
    }
  }
  return new Response(puffer, { status: 200, headers: { ...kopf, "Content-Length": String(gesamt) } });
}

async function liefereEintrag(req, kennung, rel) {
  const schluessel = kennung + "/" + rel;
  const g = await tresorFuer(schluessel);
  if (!g) {
    // Kein Schlüssel (Worker neu gestartet ohne „angemeldet bleiben“ oder abgemeldet):
    // zurück zur Seite, die nach der Anmeldung wieder hierher führt.
    const ziel = new URL(self.registration.scope);
    ziel.searchParams.set("d", kennung);
    ziel.searchParams.set("r", rel);
    return req.mode === "navigate" ? Response.redirect(ziel.href, 302) : new Response("Nicht angemeldet", { status: 401 });
  }
  try {
    let puffer = await entschluesselt(g.vid, g.t, g.fid);
    const mime = mimeVon(rel);
    if (mime.startsWith("text/html")) puffer = mitRueckweg(puffer);
    return antwortMitBereich(req, puffer, mime);
  } catch (e) {
    return new Response("Fehler beim Entschlüsseln: " + (e && e.message || e), { status: 500, headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }
}

/* ─────────────────────────── Anfragen ─────────────────────────── */
self.addEventListener("fetch", ev => {
  const req = ev.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;       // fremde Origins nicht anfassen
  const p = relPfad(url);
  if (p === null) return;

  const m = /^d\/([^/]+)\/(.+)$/.exec(p);
  if (m) {
    ev.respondWith(liefereEintrag(req, decodeURIComponent(m[1]), decodeURIComponent(m[2])));
  } else if (istTresordatei(p)) {
    ev.respondWith(cacheFirst(req));
  } else if (istHuelle(p) || req.mode === "navigate") {
    ev.respondWith(networkFirst(req));
  }
});

async function cacheFirst(req) {
  const cache = await caches.open(CACHE);
  const treffer = await cache.match(req, { ignoreSearch: true });
  if (treffer) return treffer;
  const antwort = await fetch(req);
  if (antwort && antwort.ok) cache.put(req, antwort.clone()).catch(() => {});
  return antwort;
}

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  // Im Cache ohne ?t=…/?d=…-Zusatz ablegen: je Datei genau ein Eintrag, der jüngste gewinnt.
  const schluessel = req.url.includes("?") ? new Request(req.url.split("?")[0]) : req;
  try {
    const antwort = await fetch(req);
    if (antwort && antwort.ok) cache.put(schluessel, antwort.clone()).catch(() => {});
    return antwort;
  } catch (e) {
    const treffer = await cache.match(schluessel, { ignoreSearch: true })
      || (req.mode === "navigate" ? await cache.match("./index.html") : null);
    if (treffer) return treffer;
    throw e;
  }
}
