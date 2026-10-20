// webkit_treiber.swift — Dashboard Mobil · WebKit (WKWebView) als Prüf-Browser, gesteuert über stdin/stdout
// =========================================================================================================
// Dieselbe Browser-Engine wie Safari auf iPhone, iPad und Mac, ohne „Entfernte Automation“ in Safari.
// Befehle: eine JSON-Zeile je Befehl auf stdin, eine JSON-Zeile Antwort auf stdout.
//   {"cmd":"navigate","url":"http://…"}         → {"ok":true} nach dem Laden (oder {"ok":false,"error":…})
//   {"cmd":"js","script":"return 1+1"}          → {"ok":true,"value":2}   (Skript wie ein Funktionsrumpf)
//   {"cmd":"js_async","script":"…"}             → wartet auf den Rückruf arguments[arguments.length-1](wert)
//   {"cmd":"screenshot","file":"/tmp/x.png"}    → {"ok":true}
//   {"cmd":"visibility"}                        → {"ok":true,"value":"visible|hidden"}
//   {"cmd":"quit"}
// Bauen: swiftc -O webkit_treiber.swift -o webkit_treiber   (wird von pruefung_safari.py --wkwebview erledigt)

import AppKit
import Foundation
import WebKit

final class Treiber: NSObject, WKNavigationDelegate {
    let webView: WKWebView
    let window: NSWindow
    var ladeAntwort: (() -> Void)?

    override init() {
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .default()
        webView = WKWebView(frame: NSRect(x: 0, y: 0, width: 390, height: 844), configuration: cfg)
        window = NSWindow(contentRect: NSRect(x: 60, y: 80, width: 390, height: 844),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Dashboard Mobil · WebKit-Prüfung"
        window.contentView = webView
        super.init()
        webView.navigationDelegate = self
        window.makeKeyAndOrderFront(nil)
        // Sichtbar nach vorn holen: nur so ist document.visibilityState "visible" (stille Prüfung beim Zurückkehren).
        NSApp.activate(ignoringOtherApps: true)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if let f = ladeAntwort { ladeAntwort = nil; f() }
    }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        ladeAntwort = nil; antworte(["ok": false, "error": "Laden: " + error.localizedDescription])
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        ladeAntwort = nil; antworte(["ok": false, "error": "Laden (provisorisch): " + error.localizedDescription])
    }
    func webView(_ webView: WKWebView, didReceive challenge: URLAuthenticationChallenge,
                 completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        // Lokaler Prüfserver mit selbst signiertem Zertifikat darf durch (nur 127.0.0.1).
        if let trust = challenge.protectionSpace.serverTrust, challenge.protectionSpace.host == "127.0.0.1" {
            completionHandler(.useCredential, URLCredential(trust: trust))
        } else {
            completionHandler(.performDefaultHandling, nil)
        }
    }
}

func antworte(_ d: [String: Any]) {
    var obj = d
    if let data = try? JSONSerialization.data(withJSONObject: obj, options: [.fragmentsAllowed]),
       let s = String(data: data, encoding: .utf8) {
        print(s); fflush(stdout); return
    }
    obj["value"] = String(describing: d["value"] ?? "")           // nicht JSON-fähig → als Text
    if let data = try? JSONSerialization.data(withJSONObject: obj, options: [.fragmentsAllowed]),
       let s = String(data: data, encoding: .utf8) {
        print(s); fflush(stdout)
    } else {
        print("{\"ok\":false,\"error\":\"Antwort nicht kodierbar\"}"); fflush(stdout)
    }
}

func jsErgebnis(_ wert: Any?, _ fehler: Error?) {
    if let e = fehler as NSError? {
        let msg = (e.userInfo["WKJavaScriptExceptionMessage"] as? String) ?? e.localizedDescription
        antworte(["ok": false, "error": "JS: " + msg])
    } else {
        antworte(["ok": true, "value": wert ?? NSNull()])
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
app.finishLaunching()
let treiber = Treiber()

// Frischer Speicher (localStorage, Caches, Service Worker) dieser Prüf-Instanz – Safari bleibt unberührt.
var bereit = false
WKWebsiteDataStore.default().removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast) { bereit = true }
while !bereit { RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05)) }
antworte(["ok": true, "bereit": true, "userAgent": treiber.webView.value(forKey: "userAgent") as? String ?? ""])

func befehl(_ zeile: String) {
    guard let data = zeile.data(using: .utf8),
          let d = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
          let cmd = d["cmd"] as? String else {
        antworte(["ok": false, "error": "Befehl unlesbar"]); return
    }
    switch cmd {
    case "navigate":
        guard let u = d["url"] as? String, let url = URL(string: u) else { antworte(["ok": false, "error": "url fehlt"]); return }
        treiber.ladeAntwort = { antworte(["ok": true]) }
        treiber.webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
    case "js":
        let s = d["script"] as? String ?? ""
        treiber.webView.evaluateJavaScript("(function(){ \(s) })()") { w, e in jsErgebnis(w, e) }
    case "js_async":
        let s = d["script"] as? String ?? ""
        let rumpf = "return await new Promise(function(cb){ (function(){ \(s) }).apply(null, [cb]); });"
        treiber.webView.callAsyncJavaScript(rumpf, arguments: [:], in: nil, in: .page) { r in
            switch r {
            case .success(let w): jsErgebnis(w, nil)
            case .failure(let e): jsErgebnis(nil, e)
            }
        }
    case "screenshot":
        let datei = d["file"] as? String ?? "/tmp/webkit.png"
        treiber.webView.takeSnapshot(with: nil) { bild, e in
            guard let bild = bild, let tiff = bild.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
                  let png = rep.representation(using: .png, properties: [:]) else {
                antworte(["ok": false, "error": "Bild: " + (e?.localizedDescription ?? "?")]); return
            }
            do { try png.write(to: URL(fileURLWithPath: datei)); antworte(["ok": true]) }
            catch { antworte(["ok": false, "error": "Bild schreiben: \(error)"]) }
        }
    case "visibility":
        treiber.webView.evaluateJavaScript("document.visibilityState") { w, e in jsErgebnis(w, e) }
    case "quit":
        exit(0)
    default:
        antworte(["ok": false, "error": "unbekannter Befehl " + cmd])
    }
}

DispatchQueue.global().async {
    while let zeile = readLine() {
        DispatchQueue.main.async { befehl(zeile) }
    }
    DispatchQueue.main.async { exit(0) }
}
// Echte AppKit-Ereignisschleife: nur so bekommt WebKit mit, dass das Fenster sichtbar ist
// (document.visibilityState "visible"); ein bloßer RunLoop.main.run() lässt die Seite „hidden“.
app.run()
