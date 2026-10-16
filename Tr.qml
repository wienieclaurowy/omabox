pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "Plural.js" as Plural

// Plugin strings in the Omarchy display language. Stable has no language
// setting or Commons.I18n, so this reads the same files Edge's I18n does and
// falls back to English when they are missing. Catalogs are flat JSON in
// i18n/<code>.json, the layout Edge's Commons.Translations expects.
QtObject {
  id: root

  readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || (Quickshell.env("HOME") + "/.config")
  readonly property string omarchyPath: Quickshell.env("OMARCHY_PATH") || "/usr/share/omarchy"
  readonly property string catalogDir: String(Qt.resolvedUrl("i18n")).replace(/^file:\/\//, "")
  readonly property string languagePath: Quickshell.env("OMARCHY_LANGUAGE_FILE") || (root.configHome + "/omarchy/language")

  property string language: "en"
  readonly property string baseLanguage: language.split("-")[0]
  property string formatLocale: "en-US"
  property string decimal: "."
  property string zeroDigit: "0"
  property bool rightToLeft: false
  // For day and month names: Qt.locale() alone is the system locale, which
  // lags a language switch until the next login.
  readonly property var locale: Qt.locale(formatLocale)

  // Reassigned whole, never mutated, so bindings that called t() re-evaluate.
  property var strings: ({})
  property var englishStrings: ({})
  property var baseStrings: ({})
  property var languageStrings: ({})
  // The catalogs arrive from a child process a moment after load; until English is in, text stays empty
  // instead of showing raw keys.
  property bool ready: false

  function t(key, fallback) {
    if (!root.ready) return fallback !== undefined ? fallback : ""
    var value = root.strings[key]
    if (value && typeof value === "object") value = value.other
    if (typeof value === "string" && value.length > 0) return value
    return fallback !== undefined ? fallback : key
  }

  // Use as Tr.tn(key, n).arg(Tr.formatNumber(n)).
  function tn(key, count, fallback) {
    if (!root.ready) return fallback !== undefined ? fallback : ""
    var layers = [[root.languageStrings, root.language], [root.baseStrings, root.baseLanguage], [root.englishStrings, "en"]]
    for (var i = 0; i < layers.length; i++) {
      var value = Plural.pick(layers[i][0][key], layers[i][1], count)
      if (typeof value === "string" && value.length > 0) return value
    }
    return fallback !== undefined ? fallback : key
  }

  // Ungrouped, with the language's decimal separator and digits.
  function formatNumber(value, decimals) {
    var number = Number(value)
    if (!isFinite(number)) return String(value)
    var text = decimals === undefined ? String(number) : number.toFixed(decimals)
    if (root.decimal !== ".") text = text.replace(".", root.decimal)
    if (root.zeroDigit !== "0") {
      var zero = root.zeroDigit.charCodeAt(0)
      text = text.replace(/[0-9]/g, function(digit) { return String.fromCharCode(zero + digit.charCodeAt(0) - 48) })
    }
    return text
  }

  function parseCatalog(raw) {
    try {
      var parsed = JSON.parse(raw || "{}")
      return (parsed && typeof parsed === "object" && !Array.isArray(parsed)) ? parsed : ({})
    } catch (e) {
      return ({})
    }
  }

  function rebuildStrings() {
    var merged = ({})
    var layers = [root.englishStrings, root.baseStrings, root.languageStrings]
    for (var i = 0; i < layers.length; i++)
      for (var key in layers[i])
        if (typeof layers[i][key] === "string" || (layers[i][key] && typeof layers[i][key] === "object")) merged[key] = layers[i][key]
    root.strings = merged
  }

  function setLanguage(raw) {
    var code = String(raw || "").trim()
    if (!/^[a-z]{2,3}(-[A-Za-z]{2})?$/.test(code)) code = "en"
    root.language = code
  }

  function applyRegistry(raw) {
    var entry = parseCatalog(raw)[root.language] || ({})
    root.formatLocale = entry.formatLocale || (root.language === "en" ? "en-US" : root.language)
    root.decimal = entry.decimal || "."
    root.zeroDigit = entry.zeroDigit || "0"
    root.rightToLeft = entry.direction === "rtl"
  }

  onLanguageChanged: registryReader.read()

  // Every file here, the plugin's catalogs too, comes in through a capped, time-limited child and never through the
  // shell itself: a FIFO or a huge file in its place would block the GUI thread or fill the shell's memory. Until
  // they arrive t() gives keys; at shell start only the bar's tooltip uses it.
  component CappedRead: Process {
    id: reader
    property string path: ""
    property int limit: 1024 * 1024
    property bool stale: false
    // "" for a missing, unreadable or too large file
    signal arrived(string text)

    // command is set here, not bound: onPathChanged runs before a binding on path would update it
    function read() {
      if (path === "") {
        arrived("")
      } else if (running) {
        stale = true
      } else {
        command = ["timeout", "-k", "1", "5", "head", "-c", String(limit + 1), "--", path]
        running = true
      }
    }

    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: reader.arrived(text.length > reader.limit ? "" : text)
    }
    onExited: if (stale) {
      stale = false
      Qt.callLater(reader.read)
    }
  }

  Component.onCompleted: {
    languageReader.read()
    registryReader.read()
    englishReader.read()
  }

  // Watchers only: preload: false never reads.
  property FileView languageFile: FileView {
    path: root.languagePath
    preload: false
    watchChanges: true
    printErrors: false
    onFileChanged: languageReader.read()
  }

  property CappedRead languageReader: CappedRead {
    path: root.languagePath
    limit: 16
    onArrived: function(text) { root.setLanguage(text) }
  }

  // Edge only; on stable the defaults above stand.
  property CappedRead registryReader: CappedRead {
    path: root.omarchyPath + "/default/i18n/locales.json"
    onArrived: function(text) { root.applyRegistry(text) }
  }

  property FileView englishFile: FileView {
    path: root.catalogDir + "/en.json"
    preload: false
    watchChanges: true
    printErrors: false
    onFileChanged: englishReader.read()
  }

  property CappedRead englishReader: CappedRead {
    path: root.catalogDir + "/en.json"
    onArrived: function(text) { root.englishStrings = root.parseCatalog(text); root.ready = true; root.rebuildStrings() }
  }

  property FileView baseFile: FileView {
    path: baseReader.path
    preload: false
    watchChanges: true
    printErrors: false
    onFileChanged: baseReader.read()
  }

  property CappedRead baseReader: CappedRead {
    path: root.baseLanguage !== root.language && root.baseLanguage !== "en" ? root.catalogDir + "/" + root.baseLanguage + ".json" : ""
    onPathChanged: read()
    onArrived: function(text) { root.baseStrings = root.parseCatalog(text); root.rebuildStrings() }
  }

  property FileView languageCatalog: FileView {
    path: languageCatalogReader.path
    preload: false
    watchChanges: true
    printErrors: false
    onFileChanged: languageCatalogReader.read()
  }

  property CappedRead languageCatalogReader: CappedRead {
    path: root.language !== "en" ? root.catalogDir + "/" + root.language + ".json" : ""
    onPathChanged: read()
    onArrived: function(text) { root.languageStrings = root.parseCatalog(text); root.rebuildStrings() }
  }
}
