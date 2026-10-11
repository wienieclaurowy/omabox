.pragma library

function parseState(text) {
  var state
  try {
    state = JSON.parse(text || "{}")
  } catch (e) {
    state = {}
  }
  if (!state || typeof state !== "object") state = {}
  if (!Array.isArray(state.items)) state.items = []
  if (!state.installed || typeof state.installed !== "object") state.installed = {}
  if (!state.errors || typeof state.errors !== "object") state.errors = {}
  return state
}

// overrides: id -> fields changed in the panel (read, later, snoozed_until) before the CLI's write comes back
// through the file watch. Snoozed posts stay hidden until their time passes.
function feedItems(state, overrides, now) {
  var nowIso = (now || new Date()).toISOString()
  var items = []
  for (var i = 0; i < state.items.length; i++) {
    var copy = {}
    for (var key in state.items[i]) copy[key] = state.items[i][key]
    var change = overrides ? overrides[copy.id] : null
    if (change) for (var field in change) copy[field] = change[field]
    if (copy.snoozed_until && String(copy.snoozed_until) > nowIso) continue
    if (copy.cleared) continue
    items.push(copy)
  }
  items.sort(function(a, b) { return String(b.published).localeCompare(String(a.published)) })
  return items
}

// filter: "" all, "later" the read-later queue, anything else a source name. query matches title, summary and excerpt.
function filterItems(items, filter, query) {
  var q = String(query || "").trim().toLowerCase()
  return items.filter(function(item) {
    if (filter === "later" && !item.later) return false
    if (filter && filter !== "later" && item.source !== filter) return false
    if (!q) return true
    return (String(item.title) + " " + String(item.summary || "") + " " + String(item.excerpt || "") + " " + item.source
      + (item.repost ? " " + item.repost.name : "")).toLowerCase().indexOf(q) >= 0
  })
}

function nextFilter(current, items) {
  var ring = [""]
  var sources = []
  var anyLater = false
  for (var i = 0; i < items.length; i++) {
    if (sources.indexOf(items[i].source) < 0) sources.push(items[i].source)
    if (items[i].later) anyLater = true
  }
  ring = ring.concat(sources)
  if (anyLater || current === "later") ring.push("later")
  var index = ring.indexOf(current)
  return ring[(index + 1) % ring.length]
}

// Notifications filter by app (appLabel); query matches app, summary and body.
function filterNotes(rows, filter, query) {
  var q = String(query || "").trim().toLowerCase()
  return rows.filter(function(row) {
    if (filter && appLabel(row) !== filter) return false
    if (!q) return true
    return (appLabel(row) + " " + String(row.summary || "") + " " + plainBody(row.body)).toLowerCase().indexOf(q) >= 0
  })
}

function nextNoteFilter(current, rows) {
  var ring = [""]
  for (var i = 0; i < rows.length; i++) {
    var app = appLabel(rows[i])
    if (app && ring.indexOf(app) < 0) ring.push(app)
  }
  return ring[(ring.indexOf(current) + 1) % ring.length]
}

// Read posts the feed's clear hides: read-later ones stay (snoozed ones are not in items).
function clearableIds(items) {
  var ids = []
  for (var i = 0; i < items.length; i++) if (items[i].read && !items[i].later) ids.push(items[i].id)
  return ids
}

function filterLabel(filter) {
  return filter === "later" ? "READ LATER" : String(filter || "").toUpperCase()
}

function imagePaths(html, imageDir) {
  var paths = []
  var re = /omabox-img:([0-9a-f]{20}\.(?:png|jpg|gif|webp))/g
  var match
  while ((match = re.exec(String(html || ""))) !== null) paths.push(imageDir + "/" + match[1])
  return paths
}

// The post's video files in document order: bin/omabox wraps each video's poster in a link to its file.
function videoUrls(html) {
  var urls = []
  var re = /<a href="([^"]*)"><img src="omabox-poster:/g
  var match
  while ((match = re.exec(String(html || ""))) !== null) urls.push(unescapeHtml(match[1]))
  return urls
}

function unescapeHtml(text) {
  return text.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, "\"").replace(/&#x27;|&#39;/g, "'")
    .replace(/&amp;/g, "&")
}

// Section labels (h1/h2 "h", h3+ "sub", the comments "section") in document order, as plain text, for ]/[ jumps.
function headingLabels(html) {
  var labels = []
  var re = /<p class="(?:h|sub|section)">([\s\S]*?)<\/p>/g
  var match
  while ((match = re.exec(String(html || ""))) !== null) {
    var text = unescapeHtml(match[1].replace(/<[^>]*>/g, "")).trim()
    if (text) labels.push(text)
  }
  return labels
}

// Omarchy stores a notification's action as a JSON argv; same structural checks as its own NotificationLogic.parseExecArgv.
function notificationArgv(row) {
  var parsed
  try { parsed = JSON.parse(String(row && row.execArgv || "")) } catch (e) { return null }
  if (!Array.isArray(parsed) || parsed.length === 0) return null
  for (var i = 0; i < parsed.length; i++) if (typeof parsed[i] !== "string") return null
  if (parsed[0] === "" || parsed[0].charAt(0) === "-") return null
  return parsed
}

function unreadCount(items) {
  var n = 0
  for (var i = 0; i < items.length; i++) if (!items[i].read) n++
  return n
}

function compareVersions(a, b) {
  var pa = String(a).split("."), pb = String(b).split(".")
  for (var i = 0; i < Math.max(pa.length, pb.length); i++) {
    var x = parseInt(pa[i] || "0", 10), y = parseInt(pb[i] || "0", 10)
    if (x !== y) return x < y ? -1 : 1
  }
  return 0
}

function versionTag(item, installed) {
  var mine = installed ? installed[item.source] : ""
  if (!mine || !item.version) return ""
  var cmp = compareVersions(item.version, mine)
  if (cmp === 0) return "installed"
  return cmp > 0 ? "newer" : ""
}

function relativeTime(iso, now) {
  if (!iso) return ""
  var then = new Date(iso)
  if (isNaN(then.getTime())) return ""
  var minutes = Math.floor((now.getTime() - then.getTime()) / 60000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return minutes + "m ago"
  var hours = Math.floor(minutes / 60)
  if (hours < 24) return hours + "h ago"
  var days = Math.floor(hours / 24)
  if (days < 7) return days + "d ago"
  if (then.getFullYear() === now.getFullYear()) return Qt.formatDate(then, "MMM d")
  return Qt.formatDate(then, "MMM d yyyy")
}

// "<file name>\t<json>" per line from Omarchy's history dir and Omabox's archive; the same file can appear in both.
function parseHistory(text) {
  var rows = []
  var seen = {}
  var lines = String(text || "").split("\n")
  for (var i = 0; i < lines.length; i++) {
    var tab = lines[i].indexOf("\t")
    if (tab <= 0) continue
    var name = lines[i].slice(0, tab)
    if (seen[name]) continue
    try {
      var row = JSON.parse(lines[i].slice(tab + 1))
      if (!row || typeof row !== "object") continue
      row.file = name
      seen[name] = true
      rows.push(row)
    } catch (e) {}
  }
  rows.sort(function(a, b) { return (b.timestamp || 0) - (a.timestamp || 0) })
  return rows
}

// Notification bodies may carry markup; the panel renders them as PlainText, so tags are only stripped for looks.
function plainBody(body) {
  return String(body || "").replace(/<[^>]*>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, "\"").replace(/&#39;/g, "'").replace(/&amp;/g, "&").trim()
}

function escapeHtml(text) {
  return String(text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

// A notification shaped like a feed item so the reader can show its full text: plain body, escaped, paragraphs
// on blank lines, line breaks kept, bare URLs linked. Summary is the title; the app glyph stands in for a source icon.
function noteAsItem(row) {
  var body = escapeHtml(plainBody(row.body))
  body = body.replace(/https?:\/\/[^\s<>"]+/g, function(url) {
    var clean = url.replace(/[.,;:!?)\]']+$/, "")
    return "<a href=\"" + clean + "\">" + clean + "</a>" + url.slice(clean.length)
  })
  var html = body.split(/\n{2,}/).map(function(paragraph) { return "<p>" + paragraph.replace(/\n/g, "<br>") + "</p>" }).join("")
  var words = String(row.body || "").split(/\s+/).filter(function(w) { return w !== "" }).length
  return {
    id: "note:" + row.file,
    note: true,
    source: appLabel(row) || "Notification",
    icon: { glyph: appGlyph(row) },
    title: row.summary || appLabel(row) || "Notification",
    html: html,
    link: "",
    published: new Date(row.timestamp || 0).toISOString(),
    minutes: words > 230 ? Math.round(words / 230) : 0,
    read: true
  }
}

function deliveredLabel(state, now, at, problem) {
  if (problem) return "Delivery failed: " + problem
  if (state.paused_until && String(state.paused_until) > now.toISOString())
    return "Deliveries paused until " + Qt.formatDateTime(new Date(state.paused_until), "ddd HH:mm") + "  ·  omabox pause off"
  if (!state.delivered) return "Nothing delivered yet. The first delivery starts within a minute."
  return "Delivered " + relativeTime(state.delivered, now) + (at ? "  ·  daily at " + at : "")
}

// appIcon is often a reverse-DNS desktop id ("com.mitchellh.ghostty") when the sender leaves app empty.
function appLabel(row) {
  var name = String(row.app || "")
  if (name) return name
  var icon = String(row.appIcon || "")
  return icon.indexOf("/") >= 0 ? "" : icon.split(".").pop()
}

var WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
var WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

function weekdayOptions() {
  return WEEKDAYS.map(function(day, index) {
    return { value: day, label: WEEKDAY_NAMES[index].slice(0, 3), tooltip: WEEKDAY_NAMES[index] + " (w cycles)" }
  })
}

function weekdayName(day) {
  var index = WEEKDAYS.indexOf(day)
  return index < 0 ? WEEKDAY_NAMES[0] : WEEKDAY_NAMES[index]
}

function nextWeekday(day) {
  return WEEKDAYS[(WEEKDAYS.indexOf(day) + 1) % 7]
}

function nextCadence(cadence) {
  return cadence === "daily" ? "weekly" : cadence === "weekly" ? "paused" : "daily"
}

function sourceStatus(source, now) {
  if (source.error) return "✗ " + source.error
  if (!source.fetched) return "never fetched"
  return "✓ " + relativeTime(source.fetched, now)
}

// The rejected-token error (bin/omabox X_TOKEN_ERROR) carries its fix, so the source row shows it unelided.
function errorNeedsFullText(error) {
  return String(error || "").indexOf("X token rejected") === 0
}

// stale: `omabox sources --json`'s { kind: "failing" | "quiet", days } or null.
function staleLabel(stale) {
  if (!stale) return ""
  return (stale.kind === "failing" ? "failing for " : "no new posts for ") + stale.days + " days"
}

// "  ·  2 mute rules  ·  no reposts" for the source row's status line, "" when nothing is muted.
function muteSummary(source) {
  var n = source.mute ? source.mute.length : 0
  var parts = n > 0 ? [n + (n === 1 ? " mute rule" : " mute rules")] : []
  if (source.x_hidden && source.x_hidden.reposts) parts.push("no reposts")
  return parts.map(function(part) { return "  ·  " + part }).join("")
}

// X sources are stored as the local RSSHub route; people know them as x.com/<handle>.
function shortUrl(url) {
  var text = String(url || "")
  var x = text.match(/^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\/twitter\/user\/([\w]+)/)
  if (x) return "x.com/" + x[1]
  return text.replace(/^https?:\/\//, "").replace(/^www\./, "")
}

// link when it is an absolute http(s) URL, else "": stored posts may predate the CLI's own check.
function webLink(link) {
  var text = String(link || "").trim()
  return /^https?:\/\/[^\/\s]/i.test(text) ? text : ""
}

// Qt.resolvedUrl gives a file: URL; Process needs the path.
function localPath(url) {
  return decodeURIComponent(String(url).replace(/^file:\/\//, ""))
}

// Output of `bash -c '"$@" 2>&1; echo "::exit $?"'`.
function splitCliOutput(text) {
  var out = String(text || "")
  var match = out.match(/::exit (\d+)\s*$/)
  var code = match ? parseInt(match[1], 10) : 1
  return { code: code, text: cliProblem(code, match ? out.slice(0, match.index) : out) }
}

// The CLI's output as one message; a missing or too old Python gets a plain explanation instead of the shell's.
function cliProblem(code, text) {
  var out = String(text || "").trim()
  if (code === 126 || code === 127 || /No module named 'tomllib'/.test(out))
    return "Omabox needs Python 3.11 or newer as python3."
  return code === 0 ? out : out.replace(/^omabox: /, "")
}

function snoozeChoices() {
  return [
    { key: "1", label: "1h", choice: "1h" },
    { key: "2", label: "3h", choice: "3h" },
    { key: "3", label: "tomorrow", choice: "tomorrow" }
  ]
}

// choice: "1h" | "3h" | "tomorrow" (at the delivery time, HH:MM local, 08:00 when unknown).
function snoozeUntil(choice, now, delivery) {
  var at = /^\d\d:\d\d$/.test(delivery || "") ? delivery.split(":") : ["08", "00"]
  var until = choice === "tomorrow"
    ? new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, Number(at[0]), Number(at[1]), 0)
    : new Date(now.getTime() + (choice === "3h" ? 3 : 1) * 3600000)
  return until.toISOString().replace(/\.\d{3}Z$/, "Z")
}

// choice: "all" | "day" | "week" (published longer ago than that). items: the feed as listed, so the source
// filter and search apply and snoozed posts are already left out.
function catchupIds(items, choice, now) {
  var cutoff = choice === "day" ? now.getTime() - 86400000 : choice === "week" ? now.getTime() - 7 * 86400000 : null
  var ids = []
  for (var i = 0; i < items.length; i++) {
    if (items[i].read) continue
    if (cutoff !== null && !(new Date(items[i].published).getTime() <= cutoff)) continue
    ids.push(items[i].id)
  }
  return ids
}

function catchupChoices(items, now) {
  var choices = [
    { key: "a", label: "all", choice: "all" },
    { key: "d", label: "older than a day", choice: "day" },
    { key: "w", label: "older than a week", choice: "week" }
  ]
  for (var i = 0; i < choices.length; i++) choices[i].detail = String(catchupIds(items, choices[i].choice, now).length)
  return choices
}

function hints(view, mode, reading) {
  if (reading && view === "notifications") return "j/k scroll  ·  space/ctrl+d/u page  ·  J/K next/prev  ·  o run action  ·  yy copy  ·  +/- size  ·  h back  ·  ? hide"
  if (reading) return "j/k scroll  ·  space/ctrl+d/u page  ·  ]/[ sections  ·  J/K next/prev  ·  +/- size  ·  i media  ·  r full article  ·  C refresh comments  ·  yy copy link  ·  z snooze  ·  m later  ·  U update  ·  o browser  ·  h back  ·  ? hide"
  if (mode === "search") return "enter keep  ·  esc clear"
  if (mode === "confirm-clear") return "y clear  ·  n keep"
  if (view === "sources") {
    if (mode === "add-url") return "enter look up  ·  esc cancel"
    if (mode === "add-name") return "enter save  ·  esc cancel"
    if (mode === "rename") return "enter save  ·  esc cancel"
    if (mode === "mute") return "enter add  ·  tab/shift+tab pick a rule to edit or clear  ·  esc close"
    if (mode === "confirm") return "y remove  ·  n keep"
    if (mode === "x-token") return "enter save  ·  esc cancel"
    return "j/k move  ·  l rename  ·  h back  ·  n new  ·  c cadence  ·  m mute  ·  space pause  ·  x remove  ·  -/+ delivery time  ·  w weekly day  ·  t X token  ·  H/L feed/notifications  ·  1/2/3 views  ·  ? hide"
  }
  if (view === "notifications") return "j/k move  ·  l read  ·  / search  ·  f filter  ·  o run action  ·  yy copy  ·  x remove  ·  X clear all  ·  d do not disturb  ·  H/L feed/notifications  ·  1/2/3 views  ·  ? hide"
  return "j/k move  ·  l read  ·  / search  ·  f filter  ·  z snooze  ·  m later  ·  yy copy link  ·  i media  ·  gg/G top/bottom  ·  o browser  ·  a mark read  ·  X clear read  ·  d do not disturb  ·  H/L feed/notifications  ·  1/2/3 views  ·  ? hide"
}

// Hint strings are "key label  ·  key label"; the key is the first word.
function hintEntries(view, mode, reading) {
  return hints(view, mode, reading).split("  ·  ").map(function(part) {
    var space = part.indexOf(" ")
    return space < 0 ? { key: part, label: "" } : { key: part.slice(0, space), label: part.slice(space + 1) }
  })
}

// Qt rich text CSS: one selector per rule (grouped selectors are not reliable), colours as solid #rrggbb, sizes in px.
function readerCss(t) {
  var gap = t.gap
  function rule(selector, body) { return selector + " { " + body + " } " }
  var faint = "color: " + t.faint + "; font-size: " + t.small + "px;"
  return "<style>"
    + rule("p", "margin-top: 0px; margin-bottom: " + gap + "px; line-height: 150%;")
    + rule("div", "line-height: 150%;")
    + rule("ul", "margin-top: 0px; margin-bottom: " + gap + "px;")
    + rule("ol", "margin-top: 0px; margin-bottom: " + gap + "px;")
    + rule("li", "margin-bottom: " + Math.round(gap / 2) + "px; line-height: 145%;")
    + rule("a", "color: " + t.accent + "; text-decoration: none;")
    + rule(".h", "color: " + t.accent + "; font-family: '" + t.mono + "'; font-size: " + t.caption + "px; font-weight: 700;"
      + " text-transform: uppercase; letter-spacing: 1.5px; margin-top: " + Math.round(gap * 1.8) + "px; margin-bottom: "
      + Math.round(gap * 0.6) + "px;")
    + rule(".pic", "line-height: 100%; margin-top: " + Math.round(gap / 2) + "px; margin-bottom: " + Math.round(gap / 2) + "px;")
    + rule(".card", "margin-top: " + Math.round(gap / 2) + "px; margin-bottom: " + gap + "px; line-height: 140%;")
    + rule(".card a", "color: " + t.fg + "; text-decoration: none;")
    + rule(".sub", "font-weight: 700; margin-top: " + gap + "px; margin-bottom: " + Math.round(gap * 0.4) + "px;")
    + rule(".credit", faint) + rule(".credit a", faint)
    + rule(".meta", faint) + rule(".meta a", faint)
    // Comments (bin/omabox replies_markup). Qt paints hr in its background colour; table cells take CSS padding
    // but not CSS width, so renderHtml writes the avatar and face cell sizes as attributes.
    + rule(".rule", "background-color: " + t.line + "; margin-top: " + gap * 2 + "px; margin-bottom: 0px;")
    + rule(".section", "font-size: " + t.heading + "px; font-weight: 700; margin-top: " + gap + "px; margin-bottom: "
      + Math.round(gap * 0.2) + "px;")
    + rule(".count", "color: " + t.faint + "; font-weight: 400;")
    + rule(".comment", "margin-top: " + Math.round(gap * 1.4) + "px;")
    + rule(".opcomment", "margin-top: " + Math.round(gap * 1.4) + "px; background-color: " + t.opBg + ";")
    + rule(".opface", "padding-top: " + t.pad + "px; padding-bottom: " + t.pad + "px; padding-left: " + t.pad + "px;")
    + rule(".opcell", "padding-top: " + t.pad + "px; padding-bottom: " + t.pad + "px; padding-right: " + t.pad + "px;")
    + rule(".who", "margin-top: 0px; margin-bottom: 0px;")
    + rule(".said", "margin-top: 0px; margin-bottom: 0px; line-height: 130%;")
    + rule(".opname", "color: " + t.accent + "; font-weight: 700;")
    // Quoted post under an X post (bin/omabox quote_markup): a tinted card, its text in .who/.said like a comment.
    + rule(".quote", "margin-top: " + Math.round(gap / 2) + "px; background-color: " + t.quoteBg + ";")
    + rule(".quotecell", "padding-top: " + t.pad + "px; padding-bottom: " + t.pad + "px; padding-left: " + t.pad
      + "px; padding-right: " + t.pad + "px;")
    // "Replying to @a and @b" over an X reply's text and inside a quote card; the names keep the link colour like X.
    + rule(".replyto", faint + " margin-top: 0px; margin-bottom: " + Math.round(gap * 0.4) + "px;")
    + rule(".badge", "color: " + t.accent + "; font-family: '" + t.mono + "'; font-size: " + t.caption + "px; font-weight: 700;"
      + " letter-spacing: 1px;")
    + rule("code", "font-family: '" + t.mono + "'; background-color: " + t.codeBg + ";")
    + rule("pre", "font-family: '" + t.mono + "'; background-color: " + t.codeBg + ";")
    + "</style>"
}

// `omabox article` needs a web link; X and other short posts are the whole post already. profiles: X sources only.
function articleAvailable(item, profiles) {
  if (!item || item.note || item.short) return false
  var link = String(item.link || "")
  if (!/^https?:\/\//i.test(link) || /^https?:\/\/([^\/?#]*\.)?(x|twitter)\.com([\/:?#]|$)/i.test(link)) return false
  return !(profiles && profiles[item.source])
}

// The post as the reader shows it: the stored full article in place of the feed html, unless feedVersion.
function articleView(item, feedVersion) {
  if (!item || !item.full_html || feedVersion) return item
  var copy = {}
  for (var key in item) copy[key] = item[key]
  copy.html = item.full_html
  copy.summary = item.full_summary || ""
  copy.minutes = item.full_minutes || item.minutes
  copy.showingFull = true
  return copy
}

// `omabox replies` reads the account and post id from the link, so only X status links qualify.
function repliesAvailable(item) {
  return !!item && !item.note && /^https?:\/\/(www\.|mobile\.)?(x|twitter)\.com\/\w{1,15}\/status\/\d+/i.test(String(item.link || ""))
}

// The post with its stored replies section (bin/omabox replies_markup) under it; while a fetch runs, a note
// sits where that section starts.
function withReplies(item, loading) {
  if (!item || (!item.replies_html && !loading)) return item
  var copy = {}
  for (var key in item) copy[key] = item[key]
  copy.html = String(item.html || "")
    + (loading ? "<p class=\"meta\">" + (item.replies_html ? "Refreshing comments…" : "Loading comments…") + "</p>" : "")
    + (item.replies_html || "")
  return copy
}

function readingTime(item) {
  var minutes = item && item.minutes ? item.minutes : 0
  return minutes > 0 ? minutes + " min read" : ""
}

// bin/omabox stores pictures as <img src="omabox-img:NAME" width height> refs into its cache, video posters the same
// way as omabox-poster:, comment avatars as <img src="omabox-avatar:NAME"> and quoted authors' with class="mini";
// nothing else is an <img>. faces: {avatar, gap, pad} px for comments, mini for a quoted author.
function renderHtml(html, imageDir, maxWidth, faces) {
  var column = faces.avatar + faces.gap
  // Picture paragraphs get their own class: the 150% reading line height would add half the picture's height below it.
  return String(html || "").replace(/<p>(<img src="omabox-img:|<a href="[^"]*"><img src="omabox-poster:)/g, "<p class=\"pic\">$1")
    .replace(/<img src="omabox-(?:img|poster):([0-9a-f]{20}\.(?:png|jpg|gif|webp))" width="(\d+)" height="(\d+)"(?: depth="(\d)")?>/g,
    function(match, name, width, height, depth) {
      var w = parseInt(width, 10), h = parseInt(height, 10)
      // A comment picture sits depth text columns in; 60% keeps a meme from outweighing the thread.
      // depth 0: a quoted post's picture, inside the card's padding.
      var room = depth === undefined ? maxWidth : depth === "0" ? maxWidth - 2 * faces.pad
        : Math.min(maxWidth - parseInt(depth, 10) * (column + 2 * faces.pad), maxWidth * 0.6)
      var scaled = Math.max(1, Math.min(w, Math.floor(room)))
      return "<img src=\"file://" + imageDir + "/" + name + "\" width=\"" + scaled + "\" height=\"" + Math.round(h * scaled / w) + "\">"
    })
    .replace(/<img src="omabox-avatar:([0-9a-f]{20}\.(?:png|jpg|gif|webp))">/g, function(match, name) {
      return "<img src=\"file://" + imageDir + "/" + name + "\" width=\"" + faces.avatar + "\" height=\"" + faces.avatar + "\">"
    })
    // A quoted author's face sits in the text line; Qt stands an inline image on the baseline unless told middle.
    .replace(/<img src="omabox-avatar:([0-9a-f]{20}\.(?:png|jpg|gif|webp))" class="mini">/g, function(match, name) {
      return "<img src=\"file://" + imageDir + "/" + name + "\" width=\"" + faces.mini + "\" height=\"" + faces.mini
        + "\" style=\"vertical-align: middle\">"
    })
    .replace(/<td class="face"/g, "<td class=\"face\" width=\"" + column + "\"")
    .replace(/<td class="opface"/g, "<td class=\"opface\" width=\"" + (column + faces.pad) + "\"")
}

// The objectIndex-th inline object (U+FFFC) of the rendered html as { kind: "picture", index } among
// Model.imagePaths or { kind: "video", index } among Model.videoUrls; null for a comment avatar.
function mediaAt(html, objectIndex) {
  var refs = String(html || "").match(/omabox-(?:img|avatar|poster):[0-9a-f]{20}\.(?:png|jpg|gif|webp)/g) || []
  if (objectIndex < 0 || objectIndex >= refs.length) return null
  var scheme = refs[objectIndex].slice(0, refs[objectIndex].indexOf(":") + 1)
  if (scheme === "omabox-avatar:") return null
  var index = 0
  for (var i = 0; i < objectIndex; i++) if (refs[i].indexOf(scheme) === 0) index++
  return { kind: scheme === "omabox-img:" ? "picture" : "video", index: index }
}

var APP_GLYPHS = [
  [/ghostty|alacritty|kitty|foot|terminal|wezterm|konsole/, 0xF018D],
  [/firefox|chrom|brave|browser|zen|qutebrowser/, 0xF059F],
  [/signal|whatsapp|telegram|discord|slack|element|message/, 0xF0361],
  [/mail|thunderbird|proton|geary/, 0xF01EE],
  [/omatube|spotify|mpv|music|player|audio/, 0xF075A],
  [/screenshot|capture|grim|hyprshot/, 0xF0E51],
  [/update|pacman|yay|package/, 0xF06B0],
  [/battery|power/, 0xF0079],
  [/bluetooth/, 0xF00AF],
  [/network|wifi|nm-applet/, 0xF05A9],
  [/voxtype|dictation|microphone/, 0xF036C],
  [/calendar|reminder|clock/, 0xF00ED]
]

// Omarchy's own glyph field wins; then the app id and summary are matched by kind; the bell is the fallback.
function appGlyph(row) {
  if (row.glyph) return String(row.glyph)
  var hay = (String(row.app || "") + " " + String(row.appIcon || "") + " " + String(row.summary || "")).toLowerCase()
  for (var i = 0; i < APP_GLYPHS.length; i++)
    if (APP_GLYPHS[i][0].test(hay)) return String.fromCodePoint(APP_GLYPHS[i][1])
  return String.fromCodePoint(0xF009A)
}

function luminance(c) {
  function channel(v) { return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
  return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b)
}

function contrastRatio(a, b) {
  var la = luminance(a), lb = luminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

// fg at opacity alpha over bg, made opaque; alpha rises until the WCAG ratio reaches minRatio, so a theme where the
// faded text already reads keeps its look and the others get only as much ink as they need.
function readableShade(fg, bg, alpha, minRatio) {
  function mix(a) { return Qt.rgba(fg.r * a + bg.r * (1 - a), fg.g * a + bg.g * (1 - a), fg.b * a + bg.b * (1 - a), 1) }
  for (var a = alpha; a < 1; a += 0.01) if (contrastRatio(mix(a), bg) >= minRatio) return mix(a)
  return mix(1)
}
