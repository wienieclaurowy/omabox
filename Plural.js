// CLDR cardinal categories for whole counts, matching Omarchy's shell rules
// for the languages these catalogs ship. A plural entry is an object keyed
// by category ({"one": "%1 song", "other": "%1 songs"}); "other" is always
// required, since a missing category falls back to it.

function within(value, low, high) {
  return value >= low && value <= high
}

function category(code, count) {
  var n = Math.abs(Math.trunc(Number(count) || 0))
  var n10 = n % 10
  var n100 = n % 100
  var millions = n !== 0 && n % 1000000 === 0

  switch (String(code || "")) {
  case "ja": case "zh-CN":
    return "other"
  case "fr": case "pt-BR":
    return n <= 1 ? "one" : millions ? "many" : "other"
  case "es-MX": case "it":
    return n === 1 ? "one" : millions ? "many" : "other"
  case "pl":
    if (n === 1) return "one"
    return within(n10, 2, 4) && !within(n100, 12, 14) ? "few" : "many"
  case "ru": case "uk":
    if (n10 === 1 && n100 !== 11) return "one"
    return within(n10, 2, 4) && !within(n100, 12, 14) ? "few" : "many"
  default:
    return n === 1 ? "one" : "other"
  }
}

function pick(entry, code, count) {
  if (typeof entry === "string") return entry
  if (!entry || typeof entry !== "object") return undefined
  var form = entry[category(code, count)]
  if (typeof form === "string" && form.length > 0) return form
  return typeof entry.other === "string" ? entry.other : undefined
}

if (typeof module !== "undefined") {
  module.exports = { category: category, pick: pick }
}
