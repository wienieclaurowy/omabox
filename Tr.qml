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

  function t(key, fallback) {
    var value = root.strings[key]
    if (value && typeof value === "object") value = value.other
    if (typeof value === "string" && value.length > 0) return value
    return fallback !== undefined ? fallback : key
  }

  // Use as Tr.tn(key, n).arg(Tr.formatNumber(n)).
  function tn(key, count, fallback) {
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

  onLanguageChanged: registryFile.reload()

  // FileView reports a load on a later event-loop turn, which would leave
  // the first frame showing raw keys; text() with blockLoading reads now.
  Component.onCompleted: {
    root.setLanguage(languageFile.text())
    root.applyRegistry(registryFile.text())
    root.englishStrings = root.parseCatalog(englishFile.text())
    if (baseFile.path !== "") root.baseStrings = root.parseCatalog(baseFile.text())
    if (languageCatalog.path !== "") root.languageStrings = root.parseCatalog(languageCatalog.text())
    root.rebuildStrings()
  }

  property FileView languageFile: FileView {
    path: Quickshell.env("OMARCHY_LANGUAGE_FILE") || (root.configHome + "/omarchy/language")
    watchChanges: true
    printErrors: false
    blockLoading: true
    onLoaded: root.setLanguage(text())
    onLoadFailed: root.setLanguage("")
    onFileChanged: reload()
  }

  // Edge only; on stable the defaults above stand.
  property FileView registryFile: FileView {
    id: registryFile
    path: root.omarchyPath + "/default/i18n/locales.json"
    printErrors: false
    blockLoading: true
    onLoaded: root.applyRegistry(text())
    onLoadFailed: root.applyRegistry("")
  }

  property FileView englishFile: FileView {
    path: root.catalogDir + "/en.json"
    watchChanges: true
    printErrors: false
    blockLoading: true
    onLoaded: { root.englishStrings = root.parseCatalog(text()); root.rebuildStrings() }
    onLoadFailed: { root.englishStrings = ({}); root.rebuildStrings() }
    onFileChanged: reload()
  }

  property FileView baseFile: FileView {
    path: root.baseLanguage !== root.language && root.baseLanguage !== "en" ? root.catalogDir + "/" + root.baseLanguage + ".json" : ""
    watchChanges: true
    printErrors: false
    blockLoading: true
    onLoaded: { root.baseStrings = root.parseCatalog(text()); root.rebuildStrings() }
    onLoadFailed: { root.baseStrings = ({}); root.rebuildStrings() }
    onPathChanged: if (path === "") { root.baseStrings = ({}); root.rebuildStrings() }
    onFileChanged: reload()
  }

  property FileView languageCatalog: FileView {
    path: root.language !== "en" ? root.catalogDir + "/" + root.language + ".json" : ""
    watchChanges: true
    printErrors: false
    blockLoading: true
    onLoaded: { root.languageStrings = root.parseCatalog(text()); root.rebuildStrings() }
    onLoadFailed: { root.languageStrings = ({}); root.rebuildStrings() }
    onPathChanged: if (path === "") { root.languageStrings = ({}); root.rebuildStrings() }
    onFileChanged: reload()
  }
}
