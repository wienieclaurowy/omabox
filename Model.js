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

function filterLabel(filter, Tr) {
  return filter === "later" ? Tr.t("feed.filterReadLater") : String(filter || "").toUpperCase()
}

// One pass over the %N holes, so a value that itself holds "%2" (a feed title) is never filled in turn.
function fill(template, values) {
  return String(template).replace(/%(\d)/g, function(hole, n) {
    var value = values[Number(n) - 1]
    return value === undefined ? hole : String(value)
  })
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

// Invisible and direction-changing characters, which could make a quoted argument read as something else.
var HIDDEN_CHARS = /[\u00ad\u061c\u180e\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff\ufff9-\ufffb]/g

// argv as a one-line shell command, in full; arguments that need it are quoted JSON-style, so controls and
// invisible characters show as escapes.
function commandLine(argv) {
  return argv.map(function(arg) {
    if (/^[\w@%+=:,.\/-]+$/.test(arg)) return arg
    return JSON.stringify(arg).replace(HIDDEN_CHARS, function(c) { return "\\u" + ("000" + c.charCodeAt(0).toString(16)).slice(-4) })
  }).join(" ")
}

// The confirmation shows the whole command; one too long for the message strip is not offered at all.
var ACTION_SHOWN_MAX = 600

// A stored notification's action runs on a second o while the status line still shows what the first one said it
// would run, for the same notification: Omarchy keeps any app's argv for days. { run: argv or null, pending, message }
function actionStep(row, pending, message, Tr) {
  var argv = notificationArgv(row)
  if (!argv) return { run: null, pending: "", message: Tr.t("notifications.noAction") }
  var command = commandLine(argv)
  if (command.length > ACTION_SHOWN_MAX)
    return { run: null, pending: "", message: Tr.tn("notifications.actionTooLong", command.length).arg(Tr.formatNumber(command.length)) }
  var prompt = fill(Tr.t("notifications.runPrompt"), [command])
  if (pending !== "" && pending === String(row.file || "") && message === prompt) return { run: argv, pending: "", message: "" }
  return { run: null, pending: String(row.file || ""), message: prompt }
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

function relativeTime(iso, now, Tr) {
  if (!iso) return ""
  var then = new Date(iso)
  if (isNaN(then.getTime())) return ""
  var minutes = Math.floor((now.getTime() - then.getTime()) / 60000)
  if (minutes < 1) return Tr.t("time.justNow")
  if (minutes < 60) return Tr.tn("time.minutesAgo", minutes).arg(Tr.formatNumber(minutes))
  var hours = Math.floor(minutes / 60)
  if (hours < 24) return Tr.tn("time.hoursAgo", hours).arg(Tr.formatNumber(hours))
  var days = Math.floor(hours / 24)
  if (days < 7) return Tr.tn("time.daysAgo", days).arg(Tr.formatNumber(days))
  return then.toLocaleDateString(Tr.locale, then.getFullYear() === now.getFullYear() ? Tr.t("time.date") : Tr.t("time.dateYear"))
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
function noteAsItem(row, Tr) {
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
    source: appLabel(row) || Tr.t("notifications.fallbackTitle"),
    icon: { glyph: appGlyph(row) },
    title: row.summary || appLabel(row) || Tr.t("notifications.fallbackTitle"),
    html: html,
    link: "",
    published: new Date(row.timestamp || 0).toISOString(),
    minutes: words > 230 ? Math.round(words / 230) : 0,
    read: true
  }
}

// Empty while deliveries run normally: the panel shows only what needs attention.
function deliveryNotice(state, now, problem, Tr) {
  if (problem) return fill(Tr.t("feed.deliveryFailed"), [problem])
  if (state.paused_until && String(state.paused_until) > now.toISOString())
    return fill(Tr.t("feed.pausedUntil"), [new Date(state.paused_until).toLocaleString(Tr.locale, Tr.t("time.weekdayTime"))])
      + "  ·  omabox pause off"
  if (!state.delivered) return Tr.t("feed.nothingDelivered")
  return ""
}

// appIcon is often a reverse-DNS desktop id ("com.mitchellh.ghostty") when the sender leaves app empty.
function appLabel(row) {
  var name = String(row.app || "")
  if (name) return name
  var icon = String(row.appIcon || "")
  return icon.indexOf("/") >= 0 ? "" : icon.split(".").pop()
}

var WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

// Locale.dayName counts from Sunday = 0; its format argument is Locale.LongFormat 0 or ShortFormat 1, which a
// .pragma library cannot name.
function weekdayOptions(Tr) {
  return WEEKDAYS.map(function(day, index) {
    return { value: day, label: Tr.locale.dayName((index + 1) % 7, 1),
             tooltip: fill(Tr.t("sources.weekdayTooltip"), [Tr.locale.standaloneDayName((index + 1) % 7, 0)]) }
  })
}

function weekdayName(day, Tr) {
  return Tr.locale.standaloneDayName((Math.max(0, WEEKDAYS.indexOf(day)) + 1) % 7, 0)
}

function nextWeekday(day) {
  return WEEKDAYS[(WEEKDAYS.indexOf(day) + 1) % 7]
}

function nextCadence(cadence) {
  return cadence === "daily" ? "weekly" : cadence === "weekly" ? "paused" : "daily"
}

// bin/omabox X_TOKEN_ERROR, stored in items.json in English; the other source errors come from the fetch as they are.
var X_TOKEN_ERROR = "X token rejected: paste a new one in Sources (t)"

function sourceError(error, Tr) {
  return String(error) === X_TOKEN_ERROR ? Tr.t("sources.xTokenRejected") : String(error)
}

function sourceStatus(source, now, Tr) {
  if (source.error) return "✗ " + sourceError(source.error, Tr)
  if (!source.fetched) return Tr.t("sources.neverFetched")
  return "✓ " + relativeTime(source.fetched, now, Tr)
}

// The rejected-token error carries its fix, so the source row shows it unelided.
function errorNeedsFullText(error) {
  return String(error || "").indexOf("X token rejected") === 0
}

// stale: `omabox sources --json`'s { kind: "failing" | "quiet", days } or null.
function staleLabel(stale, Tr) {
  if (!stale) return ""
  return (stale.kind === "failing" ? Tr.tn("sources.failingFor", stale.days) : Tr.tn("sources.quietFor", stale.days))
    .arg(Tr.formatNumber(stale.days))
}

// "  ·  2 mute rules  ·  no reposts" for the source row's status line, "" when nothing is muted.
function muteSummary(source, Tr) {
  var n = source.mute ? source.mute.length : 0
  var parts = n > 0 ? [Tr.tn("sources.muteRules", n).arg(Tr.formatNumber(n))] : []
  if (source.x_hidden && source.x_hidden.reposts) parts.push(Tr.t("sources.noReposts"))
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

// Supervisor for every command the shell runs and reads (python3 -I -c SUPERVISOR LIMIT SECONDS -- argv). It starts
// argv as the leader of a process group of its own under a guard child, so the shell killing it (SIGKILL when a
// Process goes, which no trap sees) still ends the command and everything it started: PR_SET_PDEATHSIG gives the
// guard a SIGTERM, and the guard sends the group TERM, then KILL 10 s later or once only the leader is left. The guard
// keeps the leader unreaped meanwhile, so the group id cannot be reused. The same happens past SECONDS, past LIMIT
// bytes of output, on its own SIGTERM and when its parent goes.
// SECONDS > 0: prints argv's output, stderr merged, then "::exit N" (124 past the deadline), or only "::overflow"
// (splitCliOutput). SECONDS 0: no deadline; stdout passes through as it comes, stderr is left alone, and its exit
// code is argv's (1 past LIMIT).
// Kept free of backslashes, backticks and dollar-brace, which a template literal would change.
var SUPERVISOR = `import os, select, signal, sys, time


class Stop(Exception):
    pass


def stop(*_):
    raise Stop


def emit(data):
    view = memoryview(data)
    while view:
        view = view[os.write(1, view):]


def group_alive(group):
    for entry in os.listdir("/proc"):
        try:
            fields = open("/proc/" + entry + "/stat").read().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if int(fields[2]) == group and fields[0] != "Z":
            return True
    return False


def end_group(group):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        os.killpg(group, signal.SIGTERM)
    except OSError:
        return
    until = time.monotonic() + 10
    while time.monotonic() < until and group_alive(group):
        time.sleep(0.05)
    try:
        os.killpg(group, signal.SIGKILL)
    except OSError:
        pass


def guard(parent, write_end, argv, streaming):
    import ctypes
    leader = None
    try:
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
        ctypes.CDLL(None).prctl(1, signal.SIGTERM)
        if os.getppid() != parent:
            raise Stop
        actions = [(os.POSIX_SPAWN_DUP2, write_end, 1)]
        if not streaming:
            actions.append((os.POSIX_SPAWN_DUP2, write_end, 2))
        try:
            leader = os.posix_spawnp(argv[0], argv, os.environ, file_actions=actions, setpgroup=0, setsigmask=(),
                                     setsigdef=(signal.SIGPIPE, signal.SIGXFSZ, signal.SIGTERM, signal.SIGINT))
        except OSError as error:
            os.write(write_end, (argv[0] + ": " + str(error.strerror) + chr(10)).encode())
            os._exit(126 if isinstance(error, PermissionError) else 127)
        finally:
            os.close(write_end)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})
        os.waitid(os.P_PID, leader, os.WEXITED | os.WNOWAIT)
    except Stop:
        if leader is not None:
            end_group(leader)
    if leader is None:
        os._exit(1)
    code = os.waitstatus_to_exitcode(os.waitpid(leader, 0)[1])
    os._exit(128 - code if code < 0 else code)


def main():
    limit, seconds, argv = int(sys.argv[1]), float(sys.argv[2]), sys.argv[4:]
    streaming = seconds <= 0
    parent, shell = os.getpid(), os.getppid()
    read_end, write_end = os.pipe()
    signal.signal(signal.SIGTERM, stop)
    child = os.fork()
    if child == 0:
        os.close(read_end)
        guard(parent, write_end, argv, streaming)
    os.close(write_end)
    done = os.pidfd_open(child)
    deadline = None if streaming else time.monotonic() + seconds
    out, size, ending, finished = [], 0, None, False
    try:
        while True:
            wait = 1.0 if deadline is None else min(1.0, deadline - time.monotonic())
            if wait <= 0:
                ending = "timeout"
                break
            ready = select.select([read_end] + ([] if finished else [done]), [], [], wait)[0]
            if os.getppid() != shell:
                raise Stop
            if done in ready:
                finished = True
                os.set_blocking(read_end, False)
            if read_end not in ready and not finished:
                continue
            try:
                chunk = os.read(read_end, 65536)
            except BlockingIOError:
                break
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                if streaming:
                    emit(chunk[:len(chunk) - (size - limit)])
                ending = "overflow"
                break
            if streaming:
                emit(chunk)
            else:
                out.append(chunk)
    except (Stop, OSError):
        ending = "stop"
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if ending:
        try:
            os.kill(child, signal.SIGTERM)
        except OSError:
            pass
    code = os.waitstatus_to_exitcode(os.waitpid(child, 0)[1])
    if streaming:
        sys.exit(1 if ending else code)
    if ending == "stop":
        return
    try:
        if ending == "overflow":
            emit(b"::overflow")
        else:
            emit(b"".join(out) + ("::exit " + str(124 if ending == "timeout" else code)).encode())
    except OSError:
        pass


main()
`

function bounded(argv, limit, seconds) {
  return ["python3", "-I", "-c", SUPERVISOR, String(limit), String(seconds), "--"].concat(argv)
}

// For a command that runs as long as the user wants (a video player): only its output is capped.
function capped(argv, limit) {
  return bounded(argv, limit, 0)
}

// Model.bounded limits for the panel's CLI calls: bytes of output and seconds.
var CLI_OUTPUT_BYTES = 8 * 1024 * 1024
var CLI_SECONDS = 600
var SMALL_OUTPUT_BYTES = 64 * 1024

// Characters of a source name (MAX_NAME_CHARS in bin/omabox) and of a message the panel lays out; a message holds a
// whole command to confirm (ACTION_SHOWN_MAX) with room to spare.
var NAME_CHARS = 200
var MESSAGE_CHARS = 1200

// bin/omabox keeps items.json within it (MAX_STATE_BYTES there)
var MAX_STATE_BYTES = 16 * 1024 * 1024

function splitCliOutput(text, Tr) {
  var out = String(text || "")
  if (/::overflow$/.test(out)) return { code: 1, text: Tr.t("cli.outputTooLarge"), overflow: true }
  var match = out.match(/::exit (\d+)\s*$/)
  var code = match ? parseInt(match[1], 10) : 1
  return { code: code, text: cliProblem(code, match ? out.slice(0, match.index) : out, Tr) }
}

// The CLI's output as one message; a missing or too old Python gets a plain explanation instead of the shell's.
function cliProblem(code, text, Tr) {
  var out = String(text || "").trim()
  if (code === 126 || code === 127 || /No module named 'tomllib'/.test(out))
    return Tr.t("cli.needsPython")
  return code === 0 ? out : out.replace(/^omabox: /, "")
}

function snoozeChoices(Tr) {
  return [
    { key: "1", label: Tr.t("snooze.oneHour"), choice: "1h" },
    { key: "2", label: Tr.t("snooze.threeHours"), choice: "3h" },
    { key: "3", label: Tr.t("snooze.tomorrow"), choice: "tomorrow" }
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

function catchupChoices(items, now, Tr) {
  var choices = [
    { key: "a", label: Tr.t("catchup.all"), choice: "all" },
    { key: "d", label: Tr.t("catchup.olderThanDay"), choice: "day" },
    { key: "w", label: Tr.t("catchup.olderThanWeek"), choice: "week" }
  ]
  for (var i = 0; i < choices.length; i++) choices[i].detail = Tr.formatNumber(catchupIds(items, choices[i].choice, now).length)
  return choices
}

// [key, label] pairs; the key is typed as shown.
function hintPairs(view, mode, reading, Tr) {
  var common = [["H/L", Tr.t("hints.feedNotifications")], ["1/2/3", Tr.t("hints.views")], ["?", Tr.t("hints.hide")]]
  if (reading && view === "notifications") return [["j/k", Tr.t("hints.scroll")], ["space/ctrl+d/u", Tr.t("hints.page")],
    ["J/K", Tr.t("hints.nextPrev")], ["oo", Tr.t("hints.runAction")], ["yy", Tr.t("hints.copy")], ["+/-", Tr.t("hints.size")], ["h", Tr.t("hints.back")],
    ["?", Tr.t("hints.hide")]]
  if (reading) return [["j/k", Tr.t("hints.scroll")], ["space/ctrl+d/u", Tr.t("hints.page")], ["]/[", Tr.t("hints.sections")],
    ["J/K", Tr.t("hints.nextPrev")], ["+/-", Tr.t("hints.size")], ["i", Tr.t("hints.media")], ["r", Tr.t("hints.fullArticle")],
    ["C", Tr.t("hints.refreshComments")], ["yy", Tr.t("hints.copyLink")], ["z", Tr.t("hints.snooze")], ["m", Tr.t("hints.later")],
    ["U", Tr.t("hints.update")], ["o", Tr.t("hints.browser")], ["h", Tr.t("hints.back")], ["?", Tr.t("hints.hide")]]
  if (mode === "search") return [["enter", Tr.t("hints.keep")], ["esc", Tr.t("hints.clear")]]
  if (mode === "confirm-clear") return [["y", Tr.t("hints.clear")], ["n", Tr.t("hints.keep")]]
  if (view === "sources") {
    if (mode === "add-url") return [["enter", Tr.t("hints.lookUp")], ["esc", Tr.t("hints.cancel")]]
    if (mode === "add-name" || mode === "rename" || mode === "x-token") return [["enter", Tr.t("hints.save")], ["esc", Tr.t("hints.cancel")]]
    if (mode === "mute") return [["enter", Tr.t("hints.add")], ["tab/shift+tab", Tr.t("hints.pickRule")], ["esc", Tr.t("hints.close")]]
    if (mode === "confirm") return [["y", Tr.t("hints.remove")], ["n", Tr.t("hints.keep")]]
    return [["j/k", Tr.t("hints.move")], ["l", Tr.t("hints.rename")], ["h", Tr.t("hints.back")], ["n", Tr.t("hints.new")], ["c", Tr.t("hints.cadence")],
      ["m", Tr.t("hints.mute")], ["space", Tr.t("hints.pause")], ["x", Tr.t("hints.remove")], ["-/+", Tr.t("hints.deliveryTime")],
      ["w", Tr.t("hints.weeklyDay")], ["t", Tr.t("hints.xToken")]].concat(common)
  }
  if (view === "notifications") return [["j/k", Tr.t("hints.move")], ["l", Tr.t("hints.read")], ["/", Tr.t("hints.search")],
    ["f", Tr.t("hints.filter")], ["oo", Tr.t("hints.runAction")], ["yy", Tr.t("hints.copy")], ["x", Tr.t("hints.remove")], ["X", Tr.t("hints.clearAll")],
    ["d", Tr.t("hints.doNotDisturb")]].concat(common)
  return [["j/k", Tr.t("hints.move")], ["l", Tr.t("hints.read")], ["/", Tr.t("hints.search")], ["f", Tr.t("hints.filter")], ["z", Tr.t("hints.snooze")],
    ["m", Tr.t("hints.later")], ["yy", Tr.t("hints.copyLink")], ["i", Tr.t("hints.media")], ["gg/G", Tr.t("hints.topBottom")], ["o", Tr.t("hints.browser")],
    ["a", Tr.t("hints.markRead")], ["X", Tr.t("hints.clearRead")], ["d", Tr.t("hints.doNotDisturb")]].concat(common)
}

function hintEntries(view, mode, reading, Tr) {
  return hintPairs(view, mode, reading, Tr).map(function(pair) { return { key: pair[0], label: pair[1] } })
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

// Nothing to read but links (Hacker News, title-only feeds), so the reader fetches the article on open. A picture or
// video counts as content: a YouTube post with an empty description must not fetch the watch page.
function linkOnly(item) {
  // Media checked before links go: a video's poster img sits inside its <a href=mp4>.
  var html = String(item && item.html || "")
  if (/<(img|video)\b/i.test(html)) return false
  return html.replace(/<a\b[^>]*>[\s\S]*?<\/a>/gi, "").replace(/<[^>]*>/g, "").replace(/&nbsp;|&#160;/g, "").replace(/[\s·|•,;:\-–—]/g, "") === ""
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

// `omabox replies` reads the post from the link: X status, Reddit comment-page, Bluesky post and Mastodon status
// links qualify (bin/omabox X_POST_RE, REDDIT_POST_RE, BLUESKY_POST_RE, MASTODON_POST_RE), and Hacker News items
// by link or by hn_entry's discussion link (hn_item_ref).
function repliesAvailable(item) {
  var link = String(item && item.link || "")
  return !!item && !item.note && (/^https?:\/\/(www\.|mobile\.)?(x|twitter)\.com\/\w{1,15}\/status\/\d+/i.test(link)
    || /^https?:\/\/((www|old|new|np)\.)?reddit\.com\/r\/\w+\/comments\/\w+/i.test(link)
    || /^https:\/\/bsky\.app\/profile\/[\w.:-]+\/post\/\w+\/?$/i.test(link)
    || /^https:\/\/[\w.-]+\/@\w+(@[\w.-]+)?\/\d+\/?$/i.test(link)
    || /^https:\/\/news\.ycombinator\.com\/item\?id=\d+$/.test(link)
    || /<a href="https:\/\/news\.ycombinator\.com\/item\?id=\d+">Discussion on Hacker News<\/a>/.test(String(item.html || "")))
}

// The post with its stored replies section (bin/omabox replies_markup) under it, the CLI's own words in it
// translated; while a fetch runs, a note sits where that section starts.
function withReplies(item, loading, Tr) {
  if (!item || item.note) return item
  var copy = {}
  for (var key in item) copy[key] = item[key]
  copy.html = localizeMarkup(String(item.html || "")
    + (loading ? "<p class=\"meta\">" + escapeHtml(item.replies_html ? Tr.t("reader.refreshingComments") : Tr.t("reader.loadingComments"))
      + "</p>" : "")
    + (item.replies_html || ""), new Date(), Tr)
  return copy
}

var EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
var STAMP = "(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \\d{1,2}(?: \\d{4})?, \\d\\d:\\d\\d"

// bin/omabox local_stamp: "Sep 20, 14:05" in the year it was written, "Sep 20 2025, 14:05" for another year.
function localStamp(text, now, Tr) {
  var m = /^(\w{3}) (\d{1,2})(?: (\d{4}))?, (\d\d):(\d\d)$/.exec(text)
  if (!m || EN_MONTHS.indexOf(m[1]) < 0) return text
  var date = new Date(m[3] ? Number(m[3]) : now.getFullYear(), EN_MONTHS.indexOf(m[1]), Number(m[2]), Number(m[4]), Number(m[5]))
  if (!m[3] && date.getTime() > now.getTime() + 86400000) date.setFullYear(date.getFullYear() - 1)
  return escapeHtml(date.toLocaleString(Tr.locale, m[3] ? Tr.t("time.stampYear") : Tr.t("time.stamp")))
}

// The first line of each replies section (bin/omabox REPLIES_LINES), stored in English with the post.
var REPLIES_LINES = {
  "Top replies on X, the author's threads first": "reader.repliesX",
  "No replies on X yet": "reader.noRepliesX",
  "Top comments on Reddit, best first": "reader.repliesReddit",
  "No comments on Reddit yet": "reader.noRepliesReddit",
  "Top comments on Hacker News, the author's threads first": "reader.repliesHackerNews",
  "No comments on Hacker News yet": "reader.noRepliesHackerNews",
  "Replies on Bluesky, the author's threads and most liked first": "reader.repliesBluesky",
  "No replies on Bluesky yet": "reader.noRepliesBluesky",
  "Replies on Mastodon, the author's threads and most liked first": "reader.repliesMastodon",
  "No replies on Mastodon yet": "reader.noRepliesMastodon"
}

function repliesLine(line, Tr) {
  return Object.prototype.hasOwnProperty.call(REPLIES_LINES, line) ? Tr.t(REPLIES_LINES[line]) : null
}

// "Replying to @a, @b and 3 others" (bin/omabox replying_to): the names are markup and stay as they are.
function replyingTo(names, Tr) {
  var parts = names.split(" and ")
  var last = parts.pop()
  var head = parts.length > 0 ? parts.join(" and ").split(", ") : []
  var others = /^(\d+) others$/.exec(last)
  if (others) last = escapeHtml(Tr.tn("reader.others", Number(others[1])).arg(Tr.formatNumber(Number(others[1]))))
  var list = head.length > 0 ? fill(escapeHtml(Tr.t("reader.listAnd")), [head.join(escapeHtml(Tr.t("reader.listComma"))), last]) : last
  return fill(escapeHtml(Tr.t("reader.replyingTo")), [list])
}

// bin/omabox writes its own words into the post and comment markup in English: the comments heading and its first
// line, AUTHOR badges, "Replying to", discussion links and comment times. They are swapped here for display only;
// Model.repliesAvailable and the CLI keep matching the stored English.
function localizeMarkup(html, now, Tr) {
  return html
    .replace(/<p class="section">Comments <span class="count">/g,
      "<p class=\"section\">" + escapeHtml(Tr.t("reader.comments")) + " <span class=\"count\">")
    .replace(new RegExp("<p class=\"meta\">([^<]*) · fetched (" + STAMP + ")</p>", "g"), function(match, line, stamp) {
      var text = repliesLine(line, Tr)
      return text === null ? match
        : "<p class=\"meta\">" + fill(escapeHtml(Tr.t("reader.repliesFetched")), [escapeHtml(text), localStamp(stamp, now, Tr)]) + "</p>"
    })
    .replace(/<span class="badge">AUTHOR<\/span>/g, "<span class=\"badge\">" + escapeHtml(Tr.t("reader.authorBadge")) + "</span>")
    .replace(/<p class="replyto">Replying to (.*?)<\/p>/g, function(match, names) {
      return "<p class=\"replyto\">" + replyingTo(names, Tr) + "</p>"
    })
    .replace(new RegExp("<span class=\"meta\">((?:[^<]* · )?)(<a href=\"[^\"]*\">)?(" + STAMP + "|open|on X)(</a>)?</span>", "g"),
      function(match, label, open, when, close) {
        if (!open !== !close) return match
        var text = when === "open" ? escapeHtml(Tr.t("reader.openComment")) : when === "on X" ? escapeHtml(Tr.t("reader.onX"))
          : localStamp(when, now, Tr)
        return "<span class=\"meta\">" + label + (open || "") + text + (close || "") + "</span>"
      })
    .replace(/(<a href="[^"]*">)Discussion on (Hacker News|Reddit)<\/a>/g, function(match, open, site) {
      return open + fill(escapeHtml(Tr.t("reader.discussionOn")), [site]) + "</a>"
    })
    .replace(/>The quoted post is not available\.<\/p>/g, ">" + escapeHtml(Tr.t("reader.quoteUnavailable")) + "</p>")
}

function readingTime(item, Tr) {
  var minutes = item && item.minutes ? item.minutes : 0
  return minutes > 0 ? Tr.tn("reader.minRead", minutes).arg(Tr.formatNumber(minutes)) : ""
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

// Read posts: a share of fg's own contrast, so they recede on low-contrast themes too, where a fixed floor lands
// on fg itself. 2.4 keeps the large bold titles legible; 4.5 stops high-contrast themes fading too little.
function readShade(fg, bg) {
  return readableShade(fg, bg, 0, Math.min(4.5, Math.max(2.4, contrastRatio(fg, bg) * 0.55)))
}

// Editing for InputField, which is read-only to Qt (see there): replaces start..end with insert, control characters
// and line breaks become spaces, and the text stays within limit characters. Returns the text and the cursor.
function spliceField(text, start, end, insert, limit) {
  var value = String(text || "")
  var from = Math.max(0, Math.min(value.length, Math.min(start, end)))
  var to = Math.max(from, Math.min(value.length, Math.max(start, end)))
  var added = String(insert || "").replace(/[\u0000-\u001f\u007f]+/g, " ")
  added = added.slice(0, Math.max(0, limit - (value.length - (to - from))))
  if (/[\ud800-\udbff]$/.test(added)) added = added.slice(0, -1)
  return { text: value.slice(0, from) + added + value.slice(to), cursor: from + added.length }
}

// text cut to at most limit characters (an ellipsis last), never splitting a surrogate pair.
function clip(text, limit) {
  var value = String(text || "")
  if (value.length <= limit) return value
  var cut = value.slice(0, Math.max(0, limit - 1))
  if (/[\ud800-\udbff]$/.test(cut)) cut = cut.slice(0, -1)
  return cut + "\u2026"
}

// One character back or forward from pos, never splitting a surrogate pair.
function charStep(text, pos, forward) {
  var value = String(text || "")
  if (forward) return Math.min(value.length, pos + (/^[\ud800-\udbff][\udc00-\udfff]/.test(value.slice(pos)) ? 2 : 1))
  return Math.max(0, pos - (/[\ud800-\udbff][\udc00-\udfff]$/.test(value.slice(0, pos)) ? 2 : 1))
}

// Start of the word before pos, with the spaces after it (Ctrl+Backspace).
function wordStart(text, pos) {
  var before = String(text || "").slice(0, pos)
  return before.length - before.match(/\S*\s*$/)[0].length
}
