import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "io.github.wienieclaurowy.omabox"
  ipcTarget: "io.github.wienieclaurowy.omabox"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  readonly property color fg: bar ? bar.foreground : Color.foreground
  // Secondary text, solid: dim is for text read as text (excerpts, read titles), faint for small meta and hints.
  // Targets sit above WCAG's 4.5 and 3 because antialiased thin text renders lighter than its colour.
  readonly property color dim: Model.readableShade(fg, opaqueCard, 0.6, 4.9)
  readonly property color faint: Model.readableShade(fg, opaqueCard, 0.4, 3.4)
  // The same two on the cursor row's fill.
  readonly property color selectedDim: Model.readableShade(fg, selectedCard, 0.6, 4.9)
  readonly property color selectedFaint: Model.readableShade(fg, selectedCard, 0.4, 3.4)
  readonly property color opaqueCard: Qt.rgba(cardColor.r, cardColor.g, cardColor.b, 1)
  readonly property color selectedCard: Qt.tint(opaqueCard, Style.selectedFillFor(fg, Color.accent))
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  // ttf-ia-writer tags every Quattro file as weight 80, so Qt picks Bold unless the style is named explicitly.
  readonly property string readingFont: setting("readingFont", "iA Writer Quattro S")
  readonly property color cardColor: Color.popups.background
  // Reader width follows the measure (characters per line), not pixels, so theme font sizes keep ~70ch lines.
  readonly property int readingMeasure: Math.max(45, Math.min(100, Number(setting("readingMeasure", 70)) || 70))
  readonly property real readingCharWidth: readingMetrics.advanceWidth / readingMetrics.text.length
  readonly property int readerWidth: Math.max(Style.space(520), Math.round(readingCharWidth * readingMeasure))

  readonly property string home: Quickshell.env("HOME")
  readonly property string omaboxBin: Model.localPath(Qt.resolvedUrl("bin/omabox"))
  readonly property string imageDir: (Quickshell.env("XDG_CACHE_HOME") || (home + "/.cache")) + "/omabox/images"
  readonly property string historyDir: home + "/.local/state/omarchy/notifications/history"
  readonly property string notificationSettingsPath: home + "/.local/state/omarchy/notifications.json"

  // feed | notifications | sources
  property string view: "feed"
  // sources view only: list | add-url | add-name | rename | mute | confirm
  property string mode: "list"
  property int cursor: 0
  property string readingId: ""
  property bool pendingG: false
  property bool pendingY: false
  property int pendingRead: -1
  // feed filter: "" all, "later" the read-later queue, or a source name; notifications: an app. query is the / search.
  // Both reset when the view changes.
  property string filter: ""
  property string query: ""
  // Feed item id whose snooze picker is open (row or reader header), "" when closed.
  property string snoozePickerId: ""
  property bool catchupOpen: false
  // Index into muteRules of the rule Tab put in the mute field for editing, -1 when the field adds a new one.
  property int mutePick: -1
  property date now: new Date()
  property var notifications: []
  property bool dnd: false
  property var sources: []
  property var discovered: null
  property bool busy: false
  property string message: ""
  property bool messageError: false
  property bool viaReturn: false
  property var cliQueue: []
  // HH:MM of the daily delivery (`omabox delivery`), "" until loaded; -/+ in sources move it, deliveryApply saves.
  property string deliveryTime: ""
  property string weeklyDay: "mon"
  property var cliDone: null
  // The welcome card shows on the feed until it is dismissed once; dismissing saves `welcomed` in shell.json.
  readonly property bool welcomed: setting("welcomed", false) === true
  readonly property bool welcoming: !welcomed && view === "feed" && !reading && mode === "list"
  readonly property bool overlayShown: welcoming || (view === "sources" && mode === "x-token")
  // X profile URL whose lookup stopped for a missing or rejected X token; looked up again once one is saved.
  property string pendingXUrl: ""
  property bool xTokenSaved: false
  property string tokenToSend: ""

  readonly property bool hintsVisible: setting("hints", false) === true
  readonly property bool typing: mode === "add-url" || mode === "add-name" || mode === "rename" || mode === "mute" || mode === "search"
    || mode === "x-token"
  readonly property bool confirming: mode === "confirm" || mode === "confirm-clear"
  readonly property var allItems: hostWidget ? hostWidget.items : []
  readonly property var items: Model.filterItems(allItems, filter, query)
  readonly property int readerFontSize: Style.font.title + Math.max(-4, Math.min(10, Number(setting("readerFontDelta", 0)) || 0))
  readonly property string archiveDir: (Quickshell.env("XDG_STATE_HOME") || (home + "/.local/state")) + "/omabox/notifications"
  readonly property var feedState: hostWidget ? hostWidget.feedState : Model.parseState("")
  readonly property var noteRows: Model.filterNotes(notifications, filter, query)
  readonly property var rows: view === "feed" ? items : view === "notifications" ? noteRows : sources
  readonly property var errorSources: Object.keys(feedState.errors || {})
  readonly property var list: view === "feed" ? feedList : view === "notifications" ? notificationList : sourceList
  // The reader shows feed posts and, as note: items, notifications (Model.noteAsItem).
  readonly property bool reading: readingId !== "" && (view === "feed" || view === "notifications")
  // Found by id, not cursor: deliveries, snoozes waking and filters move or drop rows under the open post.
  readonly property int readingIndex: {
    if (!reading) return -1
    var list = view === "notifications" ? noteRows : items
    for (var i = 0; i < list.length; i++)
      if ((view === "notifications" ? "note:" + list[i].file : list[i].id) === readingId) return i
    return -1
  }
  readonly property var readingPost: readingIndex < 0 ? null
    : view === "notifications" ? Model.noteAsItem(noteRows[readingIndex]) : items[readingIndex]
  // A stored full article is what the reader shows; feedVersionId is the post switched back to its feed html.
  property string feedVersionId: ""
  // Stays set after the viewer or player closes, until the next open(): the reader keeps its body (and scroll) meanwhile.
  property bool viewingMedia: false
  // "<post id>:<video index>" while the player loads that video; the reader shows it on the video's play badge.
  property string openingVideo: ""
  property string articleLoadingId: ""
  // Replies fetch in their own Process, off the CLI queue (real X request, starts RSSHub: 4-60 s).
  // repliesFailed: ids whose fetch errored this session; only C retries them.
  property string repliesLoadingId: ""
  property var repliesFailed: ({})
  readonly property var readingItem: Model.withReplies(Model.articleView(readingPost, feedVersionId !== "" && feedVersionId === readingId),
    repliesLoadingId !== "" && repliesLoadingId === readingId)
  readonly property var scroller: reading ? reader.flick : list
  readonly property string readerCss: Model.readerCss({
    gap: Style.space(10),
    accent: "" + Color.accent,
    fg: "" + fg,
    faint: "" + faint,
    codeBg: "" + Qt.tint(cardColor, Util.alpha(fg, 0.09)),
    quoteBg: "" + Qt.tint(cardColor, Util.alpha(fg, 0.06)),
    small: Style.font.bodySmall,
    caption: Style.font.caption,
    heading: Style.font.heading + Style.space(4),
    mono: fontFamily,
    line: "" + Qt.tint(cardColor, Util.alpha(fg, 0.2)),
    opBg: "" + Qt.tint(cardColor, Util.alpha(Color.accent, 0.12)),
    pad: commentFaces.pad
  })
  readonly property var commentFaces: ({ avatar: Style.space(30), gap: Style.space(10), pad: Style.space(8), mini: Style.space(22) })
  readonly property string clearQuestion: {
    if (view === "notifications") return "Clear all " + notifications.length + (notifications.length === 1 ? " notification?" : " notifications?")
    var count = Model.clearableIds(items).length
    return "Clear " + count + (count === 1 ? " read post" : " read posts") + " from the feed? Read later stays."
  }
  readonly property var currentSource: view === "sources" && cursor < sources.length ? sources[cursor] : null
  readonly property var muteRules: currentSource && currentSource.mute ? currentSource.mute : []
  // Lists and the reader take what the screen leaves after the panel's own chrome; the Style caps keep their usual
  // size on taller screens. `panel` is the KeyboardPanel below, whose availableCardHeight is the screen minus bar and gaps.
  readonly property real bodyMaxHeight: panel.availableCardHeight > 0 ? panel.availableCardHeight - panel.verticalContentInset : 1e6
  // What the body shows under the lists.
  readonly property real tailHeight: [listSeparator, statusLine, confirmRow, hintsFlow]
    .reduce(function(sum, item) { return sum + (item.visible ? item.height + body.spacing : 0) }, 0)

  function listHeight(list) {
    return Math.min(Style.space(560), list.contentHeight, Math.max(Style.space(120), bodyMaxHeight - list.y - tailHeight))
  }

  onItemsChanged: keepPlace(feedList, items, "id")
  onReadingIndexChanged: {
    if (readingIndex >= 0) root.cursor = readingIndex
    else if (reading) Qt.callLater(closeGoneReader)
  }
  onNoteRowsChanged: keepPlace(notificationList, noteRows, "file")

  // A new JS array as model resets a ListView to its top, and the rows change on every read mark, snooze and file
  // write. Models are set here instead, and the rows that were on screen go back to the same place.
  function keepPlace(view, rows, key) {
    var current = view.model || []
    var top = view.atYBeginning ? -1 : view.indexAt(0, view.contentY + 1)
    var anchors = []
    for (var k = top; top >= 0 && k < current.length && anchors.length < 8; k++) {
      var row = view.itemAtIndex(k)
      if (row) anchors.push({ key: current[k][key], offset: row.y - view.contentY })
    }
    view.model = rows
    for (var a = 0; a < anchors.length; a++) {
      for (var i = 0; i < rows.length; i++) {
        if (rows[i][key] !== anchors[a].key) continue
        view.positionViewAtIndex(i, ListView.Beginning)
        view.contentY -= anchors[a].offset
        return
      }
    }
  }

  function open() {
    var requested = hostWidget ? hostWidget.takeRequestedView() : ""
    root.now = new Date()
    root.viewingMedia = false
    root.readingId = ""
    root.mode = "list"
    root.message = ""
    root.filter = ""
    root.query = ""
    var requestedRead = hostWidget ? hostWidget.takeRequestedRead() : -1
    var requestedPost = hostWidget ? hostWidget.takeRequestedPost() : ""
    showView(requested || "feed")
    loadDelivery()
    // The notification list loads asynchronously; its reader opens once the list arrives.
    if (requestedPost) openPostById(requestedPost)
    else if (requestedRead >= 0 && root.view === "notifications") root.pendingRead = requestedRead
    else if (requestedRead >= 0) openReader(requestedRead)
    root.controller.show()
  }

  function close() {
    if (typing) focusCatcher()
    root.mode = "list"
    root.controller.hide()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.open()
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function persistSettings(values) {
    var entry = { id: root.moduleName }
    for (var existing in root.settings) if (existing !== "id") entry[existing] = root.settings[existing]
    for (var key in values) entry[key] = values[key]
    root.settings = entry
    if (root.hostWidget) root.hostWidget.settings = entry
    if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  function showView(value) {
    closePickers()
    if (typing) focusCatcher()
    if (value !== root.view) {
      root.filter = ""
      root.query = ""
    }
    root.view = value
    root.mode = "list"
    root.message = ""
    root.readingId = ""
    if (value === "notifications") refreshNotifications()
    if (value === "sources") refreshSources()
    root.cursor = firstSelectable()
    Qt.callLater(function() { root.list.positionViewAtBeginning() })
  }

  function selectable(index) {
    if (index < 0 || index >= rows.length) return false
    return true
  }

  function firstSelectable() {
    for (var i = 0; i < rows.length; i++) if (selectable(i)) return i
    return 0
  }

  function scrollTo(target) {
    var view = root.scroller
    var top = view.originY
    var bottom = view.originY + Math.max(0, view.contentHeight - view.height)
    scrollAnimation.stop()
    scrollAnimation.target = view
    scrollAnimation.to = Math.max(top, Math.min(bottom, target))
    scrollAnimation.start()
  }

  function scrollBy(amount) {
    scrollTo((scrollAnimation.running ? scrollAnimation.to : root.scroller.contentY) + amount)
  }

  function openReader(index) {
    if (index < 0 || index >= rows.length) return
    closePickers()
    // A click on a search result: the hidden search field would keep the keys.
    if (root.mode === "search") {
      root.mode = "list"
      focusCatcher()
    }
    var row = rows[index]
    root.cursor = index
    root.readingId = view === "notifications" ? "note:" + row.file : row.id
    root.feedVersionId = ""
    scrollAnimation.stop()
    reader.flick.contentY = 0
    if (view === "feed" && !row.read) hostWidget.markRead([row.id])
    repliesDelay.restart()
  }

  function openPostById(id) {
    showView("feed")
    clearFilters()
    for (var i = 0; i < items.length; i++) {
      if (items[i].id !== id) continue
      openReader(i)
      return true
    }
    return false
  }

  function closeReader() {
    closeSnooze()
    root.readingId = ""
    Qt.callLater(function() { root.list.positionViewAtIndex(root.cursor, ListView.Contain) })
  }

  // The open post left the list (read later off inside that filter, pruned): back to the list at the same place.
  function closeGoneReader() {
    if (!reading || readingIndex >= 0) return
    root.cursor = Math.max(0, Math.min(root.cursor, rows.length - 1))
    closeReader()
  }

  function stepReader(delta) {
    var next = root.cursor + delta
    if (next >= 0 && next < rows.length) openReader(next)
  }

  function moveCursor(delta) {
    closePickers()
    if (reading) {
      scrollBy(delta * Math.max(Style.space(60), Math.round(reader.flick.height * 0.2)))
      return
    }
    var next = root.cursor + delta
    while (next >= 0 && next < rows.length && !selectable(next)) next += delta
    if (!selectable(next)) return
    root.cursor = next
    root.list.positionViewAtIndex(next, ListView.Contain)
  }

  function feedItemAt(index) {
    return view === "feed" && index >= 0 && index < rows.length ? rows[index] : null
  }

  function activate(index) {
    if (view === "sources") {
      startRename()
      return
    }
    if (reading) return
    openReader(index)
  }

  // yazi-style: l goes into the thing under the cursor, h backs out one level.
  function enter() {
    if (view === "feed" || view === "notifications") {
      if (!reading) openReader(root.cursor)
    } else if (view === "sources") {
      startRename()
    }
  }

  function leave() {
    if (view === "sources") {
      showView("feed")
    } else if (reading) {
      closeReader()
    }
  }

  function jumpToEdge(bottom) {
    if (reading) {
      scrollTo(bottom ? reader.flick.contentHeight : 0)
      return
    }
    var target = -1
    if (bottom) { for (var i = rows.length - 1; i >= 0; i--) if (selectable(i)) { target = i; break } }
    else target = firstSelectable()
    if (target < 0) return
    root.cursor = target
    scrollAnimation.stop()
    if (bottom) root.list.positionViewAtEnd()
    else root.list.positionViewAtBeginning()
  }

  function openLink(index) {
    var item = feedItemAt(index)
    if (!item) return
    if (Model.webLink(item.link)) Qt.openUrlExternally(Model.webLink(item.link))
    if (!item.read) hostWidget.markRead([item.id])
  }

  function openCatchup() {
    if (view !== "feed" || reading || !hostWidget) return
    closeSnooze()
    root.catchupOpen = true
  }

  function closeCatchup() {
    root.catchupOpen = false
  }

  // Marks what the list shows: the source filter, read-later filter and search all narrow it.
  function catchUp(choice) {
    closeCatchup()
    var ids = Model.catchupIds(root.items, choice, new Date())
    if (ids.length > 0) hostWidget.markRead(ids)
    note("Marked " + ids.length + (ids.length === 1 ? " post" : " posts") + " read.")
  }

  function closePickers() {
    closeSnooze()
    closeCatchup()
  }

  function note(text) {
    root.messageError = false
    root.message = text
  }

  function currentItem() {
    return reading ? readingItem : feedItemAt(root.cursor)
  }

  function openSnooze(item) {
    if (item === undefined) item = currentItem()
    if (item) root.snoozePickerId = item.id
  }

  function closeSnooze() {
    root.snoozePickerId = ""
  }

  function snoozeItem(item, choice) {
    closeSnooze()
    if (!item) return
    if (reading) closeReader()
    hostWidget.snooze(item, Model.snoozeUntil(choice, new Date(), root.deliveryTime))
  }

  function itemById(id) {
    for (var i = 0; i < items.length; i++) if (items[i].id === id) return items[i]
    return null
  }

  function toggleLaterCurrent(item) {
    if (item === undefined) item = currentItem()
    if (!item) return
    hostWidget.toggleLater(item)
  }

  function copyLink(item) {
    if (item === undefined) item = currentItem()
    var link = item ? Model.webLink(item.link) : ""
    if (!link) return
    Quickshell.execDetached(["wl-copy", "--", link])
    note("Copied " + link)
  }

  // Pictures open in the image viewer, videos in the video player, from media ({ kind, index }, Model.mediaAt; default: the
  // one on screen). The panel steps aside meanwhile and comes back as it was (view, post, scroll), not via open(), which resets.
  function openMedia(media) {
    var item = currentItem()
    if (!item || imageViewer.running || videoPlayer.running) return
    var paths = Model.imagePaths(item.html, root.imageDir)
    var urls = Model.videoUrls(item.html)
    if (!media && reading) media = reader.nearestMedia()
    if (!media) media = { kind: paths.length > 0 ? "picture" : "video", index: 0 }
    if (media.kind === "video" && urls.length > 0) {
      root.viewingMedia = true
      root.openingVideo = item.id + ":" + media.index
      videoPlayer.command = [root.omaboxBin, "play", "--start", String(media.index)].concat(urls)
      videoPlayer.running = true
    } else if (media.kind === "picture" && paths.length > 0) {
      root.viewingMedia = true
      imageViewer.command = [root.omaboxBin, "view", "--start", String(media.index)].concat(paths)
      imageViewer.running = true
    } else {
      note("No pictures or videos in this post.")
    }
  }

  // Full article <-> feed version of the post in the reader; the first switch fetches it through the CLI.
  function toggleArticle() {
    var post = root.readingPost
    if (!reading || view !== "feed" || !Model.articleAvailable(post, feedState.profiles)) return "unavailable"
    if (post.full_html) {
      root.feedVersionId = root.feedVersionId === post.id ? "" : post.id
      scrollAnimation.stop()
      reader.flick.contentY = 0
      return root.feedVersionId === post.id ? "feed" : "full"
    }
    if (root.articleLoadingId !== "") return "fetching"
    root.articleLoadingId = post.id
    note("Fetching the full article…")
    runCli(["article", post.id, "--json"], function(code, text) {
      root.articleLoadingId = ""
      var result = null
      try { result = JSON.parse(text) } catch (e) {}
      if (code !== 0 || !result || result.error || !result.full_html) {
        root.messageError = true
        root.message = "No full article: " + (result && result.error ? result.error : text || "omabox article failed")
        return
      }
      root.message = ""
      hostWidget.override([result.id], { full_html: result.full_html, full_summary: result.full_summary, full_minutes: result.full_minutes })
      if (root.feedVersionId === result.id) root.feedVersionId = ""
      if (root.readingId === result.id) {
        scrollAnimation.stop()
        reader.flick.contentY = 0
      }
    })
    return "fetching"
  }

  // X post in the reader: "shown" (stored copy under it), "loading", "failed" (only C retries), "waiting" (the delay
  // or another post's fetch), or "unavailable".
  function repliesState() {
    var post = root.readingPost
    if (!reading || view !== "feed" || !Model.repliesAvailable(post)) return "unavailable"
    if (root.repliesLoadingId === post.id) return "loading"
    if (post.replies_html !== undefined) return "shown"
    return root.repliesFailed[post.id] ? "failed" : "waiting"
  }

  // repliesDelay's end: fetch the open post's replies when none are stored and no fetch runs or failed for it.
  function autoFetchReplies() {
    if (root.opened && repliesState() === "waiting" && !repliesProc.running) fetchReplies(root.readingPost, false)
  }

  function refreshReplies() {
    var state = repliesState()
    if (state === "unavailable") return state
    if (repliesProc.running) return "fetching"
    fetchReplies(root.readingPost, true)
    return "fetching"
  }

  function fetchReplies(post, refresh) {
    root.repliesLoadingId = post.id
    repliesProc.command = ["bash", "-c", "\"$@\" 2>&1; echo \"::exit $?\"", "--", root.omaboxBin, "replies", post.id, "--json"]
      .concat(refresh ? ["--refresh"] : [])
    repliesProc.running = true
  }

  // Comments grow the page under the reader, whose scroll position stays.
  function repliesFetched(code, text) {
    var id = root.repliesLoadingId
    root.repliesLoadingId = ""
    var result = null
    try { result = JSON.parse(text) } catch (e) {}
    if (code !== 0 || !result || result.error || result.replies_html === undefined) {
      var failed = {}
      for (var key in root.repliesFailed) failed[key] = true
      failed[id] = true
      root.repliesFailed = failed
      root.messageError = true
      root.message = "No comments: " + (result && result.error ? result.error : text || "omabox replies failed")
    } else {
      if (root.repliesFailed[id]) {
        var kept = {}
        for (var other in root.repliesFailed) if (other !== id) kept[other] = true
        root.repliesFailed = kept
      }
      hostWidget.override([result.id], { replies_html: result.replies_html, replies_count: result.replies_count,
        replies_fetched: result.replies_fetched })
    }
    // The post open now may have been skipped while this fetch ran.
    if (reading) repliesDelay.restart()
  }

  function runUpdate(item) {
    if (item === undefined) item = currentItem()
    if (!item || Model.versionTag(item, feedState.installed) !== "newer") return
    Quickshell.execDetached(["omarchy-launch-floating-terminal-with-presentation", "omarchy-update"])
    root.close()
  }

  function changeFontSize(step) {
    var delta = step === 0 ? 0 : Math.max(-4, Math.min(10, (Number(setting("readerFontDelta", 0)) || 0) + step))
    persistSettings({ readerFontDelta: delta })
  }

  function jumpSection(direction) {
    if (!reading) return
    var target = reader.sectionTarget(direction)
    if (target >= 0) scrollTo(target)
  }

  function cycleFilter() {
    if (view !== "feed" && view !== "notifications") return
    root.filter = view === "feed" ? Model.nextFilter(root.filter, allItems) : Model.nextNoteFilter(root.filter, notifications)
    root.cursor = 0
    root.message = ""
    Qt.callLater(function() { root.list.positionViewAtBeginning() })
  }

  function startSearch() {
    if (view !== "feed" && view !== "notifications") return
    root.mode = "search"
    Qt.callLater(function() {
      searchField.text = root.query
      searchField.forceActiveFocus()
    })
  }

  function clearFilters() {
    root.query = ""
    root.filter = ""
    root.cursor = 0
  }

  function endSearch(keep) {
    if (!keep) root.query = ""
    root.mode = "list"
    root.cursor = 0
    focusCatcher()
  }

  function refreshNotifications() {
    if (!historyProc.running) historyProc.running = true
  }

  function toggleDnd() {
    root.dnd = !root.dnd
    Quickshell.execDetached(["omarchy-shell", "notifications", "toggleDnd"])
  }

  // X or the clear button: the feed hides its read posts (Model.clearableIds), notifications drop all history.
  function askClear() {
    if (reading || mode !== "list") return
    if (view === "feed" && Model.clearableIds(items).length === 0) note("No read posts to clear.")
    else if (view === "notifications" && notifications.length === 0) note("No notifications to clear.")
    else if (view === "feed" || view === "notifications") {
      closePickers()
      root.mode = "confirm-clear"
    }
  }

  // clear-read gets the ids and marks them read too: an open post's `omabox read` may not have landed yet.
  function confirmClear(yes) {
    root.mode = "list"
    if (!yes) return
    if (view === "notifications") {
      clearNotifications()
      return
    }
    var ids = Model.clearableIds(items)
    if (ids.length === 0) return
    hostWidget.override(ids, { read: true, cleared: true })
    runCli(["clear-read"].concat(ids), function() {})
    root.cursor = 0
    note("Cleared " + ids.length + (ids.length === 1 ? " read post." : " read posts."))
  }

  function clearNotifications() {
    root.notifications = []
    Quickshell.execDetached(["omarchy-shell", "notifications", "clear"])
    runCli(["clear-notifications"], function() {})
  }

  function forgetNotification(index) {
    var row = index >= 0 && index < noteRows.length ? noteRows[index] : null
    if (!row || !row.file) return
    root.notifications = notifications.filter(function(other) { return other.file !== row.file })
    root.cursor = Math.min(root.cursor, Math.max(0, root.noteRows.length - 1))
    runCli(["forget-notification", row.file], function() {})
  }

  function runNotificationAction(index) {
    var argv = index >= 0 && index < noteRows.length ? Model.notificationArgv(noteRows[index]) : null
    if (!argv) {
      note("This notification has no action.")
      return
    }
    root.message = ""
    Quickshell.execDetached(argv)
    root.close()
  }

  function copyNotification(index) {
    var row = index >= 0 && index < noteRows.length ? noteRows[index] : null
    var text = row ? Model.plainBody(row.body) || String(row.summary || "") : ""
    if (!text) return
    Quickshell.execDetached(["wl-copy", "--", text])
    note("Copied: “" + (text.length > 60 ? text.slice(0, 60) + "…" : text) + "”")
  }

  function toggleHints() {
    persistSettings({ hints: !root.hintsVisible })
  }

  // ---- omabox CLI: the one writer of sources.toml and items.json.
  function runCli(args, done) {
    var queue = root.cliQueue.slice()
    queue.push({ args: args, done: done })
    root.cliQueue = queue
    runNextCli()
  }

  function runNextCli() {
    if (cliProc.running || root.cliQueue.length === 0) return
    var job = root.cliQueue[0]
    root.cliQueue = root.cliQueue.slice(1)
    root.cliDone = job.done
    cliProc.command = ["bash", "-c", "\"$@\" 2>&1; echo \"::exit $?\"", "--", root.omaboxBin].concat(job.args)
    cliProc.running = true
  }

  function loadDelivery() {
    runCli(["delivery", "--json"], function(code, text) {
      var result = null
      try { result = JSON.parse(text) } catch (e) {}
      if (code !== 0 || !result || !result.time) return
      if (!deliveryApply.running) root.deliveryTime = result.time
      root.weeklyDay = result.weekly_day || "mon"
    })
  }

  // Half-hour steps, wrapping past midnight; saved once the stepping stops.
  function stepDelivery(minutes) {
    if (root.deliveryTime === "") return
    var parts = root.deliveryTime.split(":")
    var total = ((Number(parts[0]) * 60 + Number(parts[1]) + minutes) % 1440 + 1440) % 1440
    total -= total % 30
    if (minutes < 0 && Number(parts[1]) % 30 !== 0) total += 30
    root.deliveryTime = ("0" + Math.floor(total / 60)).slice(-2) + ":" + ("0" + total % 60).slice(-2)
    deliveryApply.restart()
  }

  function setWeeklyDay(day) {
    if (day === root.weeklyDay) return
    root.weeklyDay = day
    runCli(["delivery", "--weekly-day", day, "--json"], function(code, text) {
      if (code === 0) note("Weekly sources come in on " + Model.weekdayName(day) + ".")
      else {
        root.messageError = true
        root.message = "Weekly day not saved: " + text
        loadDelivery()
      }
    })
  }

  function saveDelivery() {
    runCli(["delivery", root.deliveryTime, "--json"], function(code, text) {
      var result = null
      try { result = JSON.parse(text) } catch (e) {}
      if (code !== 0 || !result) {
        root.messageError = true
        root.message = "Delivery time not saved: " + text
        loadDelivery()
      } else {
        note("Next delivery " + (result.next || result.time) + ".")
      }
    })
  }

  function refreshSources() {
    runCli(["sources", "--json"], function(code, text) {
      if (code !== 0) {
        root.messageError = true
        root.message = text
        return
      }
      try { root.sources = JSON.parse(text) } catch (e) { root.message = text }
      if (root.view === "sources") root.cursor = Math.min(root.cursor, Math.max(0, root.sources.length - 1))
    })
  }

  function afterSourceChange(code, text) {
    root.busy = false
    root.messageError = code !== 0
    root.message = code === 0 ? "" : text
    refreshSources()
  }

  function focusCatcher() {
    Qt.callLater(function() { arrowBlocker.forceActiveFocus() })
  }

  function startAdd() {
    root.discovered = null
    root.message = ""
    root.mode = "add-url"
    Qt.callLater(function() {
      urlField.text = ""
      urlField.forceActiveFocus()
    })
  }

  function lookUp() {
    var url = urlField.text.trim()
    if (url === "" || root.busy) return
    root.busy = true
    root.message = ""
    runCli(["discover", "--json", url], function(code, text) {
      root.busy = false
      if (root.mode !== "add-url") return
      var found = null
      try { found = JSON.parse(text) } catch (e) {}
      if (found && found.needs === "x-token") {
        root.startXToken(url)
        return
      }
      if (!found || found.error) {
        root.messageError = true
        root.message = found && found.error ? found.error : text
        return
      }
      root.discovered = found
      root.mode = "add-name"
      Qt.callLater(function() {
        nameField.text = found.title
        nameField.selectAll()
        nameField.forceActiveFocus()
      })
    })
  }

  function dismissWelcome(next) {
    persistSettings({ welcomed: true })
    if (next === "add") {
      showView("sources")
      startAdd()
    }
  }

  // ---- X token: it goes to the CLI on stdin, so it never shows in a process list.
  function startXToken(url) {
    root.pendingXUrl = url || ""
    root.message = ""
    root.mode = "x-token"
    runCli(["x-token", "--json"], function(code, text) {
      var result = null
      try { result = JSON.parse(text) } catch (e) {}
      root.xTokenSaved = !!result && result.saved === true
    })
    Qt.callLater(function() {
      tokenField.text = ""
      tokenField.forceActiveFocus()
    })
  }

  function saveXToken() {
    var token = tokenField.text.trim()
    if (token === "" || tokenProc.running) return
    root.tokenToSend = token
    tokenField.text = ""
    tokenProc.running = true
  }

  function removeXToken() {
    runCli(["x-token", "--remove"], function(code, text) {
      root.xTokenSaved = false
      root.messageError = code !== 0
      root.message = code === 0 ? "X token removed from this computer." : text
    })
  }

  function tokenSaved(code, text) {
    if (code !== 0) {
      root.messageError = true
      root.message = text
      Qt.callLater(function() { tokenField.forceActiveFocus() })
      return
    }
    root.xTokenSaved = true
    var url = root.pendingXUrl
    root.pendingXUrl = ""
    if (url === "") {
      root.mode = "list"
      focusCatcher()
      note("X token saved.")
      return
    }
    root.mode = "add-url"
    Qt.callLater(function() {
      urlField.text = url
      root.lookUp()
    })
  }

  function saveNew() {
    var name = nameField.text.trim()
    if (!root.discovered || name === "" || root.busy) return
    root.busy = true
    root.mode = "list"
    focusCatcher()
    runCli(["add", root.discovered.url, "--name", name], afterSourceChange)
  }

  function startRename() {
    if (!currentSource) return
    root.mode = "rename"
    Qt.callLater(function() {
      var field = sourceList.itemAtIndex(root.cursor)
      if (field && field.renameField) {
        field.renameField.text = root.currentSource.name
        field.renameField.selectAll()
        field.renameField.forceActiveFocus()
      }
    })
  }

  function commitRename(text) {
    var source = currentSource
    root.mode = "list"
    focusCatcher()
    var name = String(text || "").trim()
    if (!source || name === "" || name === source.name) return
    runCli(["rename", source.name, name], afterSourceChange)
  }

  function startMute() {
    if (!currentSource) return
    root.mode = "mute"
    root.mutePick = -1
    root.message = ""
    Qt.callLater(function() {
      muteField.text = ""
      muteField.forceActiveFocus()
    })
  }

  function pickMute(index) {
    var rules = root.muteRules
    if (rules.length === 0) return
    root.mutePick = (index + rules.length) % rules.length
    muteField.text = rules[root.mutePick]
    muteField.selectAll()
    muteField.forceActiveFocus()
  }

  function stepMutePick(step) {
    pickMute(root.mutePick < 0 ? (step > 0 ? 0 : -1) : root.mutePick + step)
  }

  // Rules are added and removed one at a time, so commas and anything else inside a regex need no escaping.
  // A picked rule is replaced by the edited text, removed when the field was cleared, kept when unchanged.
  function commitMute(text) {
    var source = currentSource
    if (!source) return
    var rule = String(text || "").trim()
    var rules = root.muteRules
    var picked = root.mutePick >= 0 && root.mutePick < rules.length ? rules[root.mutePick] : ""
    root.mutePick = -1
    muteField.text = ""
    if (picked !== "") {
      if (rule === picked) return
      if (rule === "") {
        runCli(["unmute", source.name, "--", picked], afterMuteChange)
        return
      }
      // The old rule goes only once the new one was accepted, so a refused regex loses nothing.
      runCli(["mute", source.name, "--", rule], function(code, text) {
        if (code !== 0) afterMuteChange(code, text)
        else runCli(["unmute", source.name, "--", picked], function(code2, text2) { afterMuteChange(code2, text + "\n" + text2) })
      })
      return
    }
    if (rule === "") cancelTyping()
    else if (rules.indexOf(rule) >= 0) note("Already muted: " + rule)
    else runCli(["mute", source.name, "--", rule], afterMuteChange)
  }

  function removeMute(rule) {
    if (!currentSource) return
    root.mutePick = -1
    muteField.text = ""
    runCli(["unmute", currentSource.name, "--", rule], afterMuteChange)
  }

  function toggleReposts() {
    var source = currentSource
    if (!source || !source.x_hidden) return
    runCli([source.x_hidden.reposts ? "unmute" : "mute", source.name, "--reposts"], afterMuteChange)
  }

  // Shows the CLI's answer ("muted: …", "removed 3 stored posts" or why a regex was refused).
  function afterMuteChange(code, text) {
    root.messageError = code !== 0
    root.message = text
    refreshSources()
  }

  function cycleCadence() {
    if (currentSource) setCadence(Model.nextCadence(currentSource.cadence))
  }

  function setCadence(cadence) {
    if (currentSource && cadence !== currentSource.cadence) runCli(["cadence", currentSource.name, cadence], afterSourceChange)
  }

  function togglePause() {
    if (!currentSource) return
    runCli(["cadence", currentSource.name, currentSource.cadence === "paused" ? "daily" : "paused"], afterSourceChange)
  }

  function askRemove() {
    if (currentSource) root.mode = "confirm"
  }

  // Leaving rename/mute/confirm first: they act on currentSource, so moving the cursor under them
  // renames an empty field, mutes or removes a different source. An add form left open would keep `typing` set,
  // which blocks every key once the row click moves focus off the field.
  function selectSource(index) {
    if (root.mode !== "list") cancelTyping()
    root.cursor = index
  }

  function confirmRemove(yes) {
    var source = currentSource
    root.mode = "list"
    if (yes && source) runCli(["remove", source.name], afterSourceChange)
  }

  function cancelTyping() {
    root.mode = "list"
    root.message = ""
    focusCatcher()
  }

  function handleText(t) {
    // The welcome card is modal: only its own keys work until it is dismissed.
    if (root.welcoming) {
      if (t === "n") dismissWelcome("add")
      return
    }
    if (view === "sources" && mode === "confirm") {
      if (t === "y") confirmRemove(true)
      else if (t === "n") confirmRemove(false)
      return
    }
    if (mode === "confirm-clear") {
      if (t === "y") confirmClear(true)
      else if (t === "n") confirmClear(false)
      return
    }
    if (root.snoozePickerId !== "") {
      var choice = t === "1" ? "1h" : t === "2" ? "3h" : t === "3" ? "tomorrow" : ""
      if (choice) snoozeItem(itemById(root.snoozePickerId), choice)
      else closeSnooze()
      return
    }
    if (root.catchupOpen) {
      var age = t === "a" ? "all" : t === "d" ? "day" : t === "w" ? "week" : ""
      if (age) catchUp(age)
      else closeCatchup()
      return
    }
    var wasG = root.pendingG
    var wasY = root.pendingY
    root.pendingG = false
    root.pendingY = false
    // Ctrl+D / Ctrl+U arrive as control characters.
    if (t === "\u0004") scrollBy(Math.round(root.list.height / 2))
    else if (t === "\u0015") scrollBy(-Math.round(root.list.height / 2))
    else if (t === "g") {
      if (wasG) jumpToEdge(false)
      else { root.pendingG = true; gTimer.restart() }
    }
    else if (t === "G") jumpToEdge(true)
    else if (t === "?") toggleHints()
    else if (reading && (t === "+" || t === "=")) changeFontSize(1)
    else if (reading && t === "-") changeFontSize(-1)
    else if (reading && t === "0") changeFontSize(0)
    else if (t === "1") showView("feed")
    else if (t === "2") showView("notifications")
    else if (t === "3") showView("sources")
    else if (t === "H") showView("feed")
    else if (t === "L") showView("notifications")
    else if (t === "s" || t === ",") showView(view === "sources" ? "feed" : "sources")
    else if (view === "feed") {
      if (t === "o") openLink(root.cursor)
      else if (t === "J" && reading) stepReader(1)
      else if (t === "K" && reading) stepReader(-1)
      else if (t === "a") openCatchup()
      else if (t === "d") toggleDnd()
      else if (t === "/") startSearch()
      else if (t === "f") cycleFilter()
      else if (t === "z") openSnooze()
      else if (t === "m") toggleLaterCurrent()
      else if (t === "i") openMedia()
      else if (t === "r" && reading) toggleArticle()
      else if (t === "C" && reading) refreshReplies()
      else if (t === "U") runUpdate()
      else if (t === "]") jumpSection(1)
      else if (t === "[") jumpSection(-1)
      else if (t === "y") {
        if (wasY) copyLink()
        else { root.pendingY = true; gTimer.restart() }
      }
    } else if (view === "notifications") {
      if (t === "d") toggleDnd()
      else if (t === "/") startSearch()
      else if (t === "f") cycleFilter()
      else if (t === "o") runNotificationAction(root.cursor)
      else if (t === "y") {
        if (wasY) copyNotification(root.cursor)
        else { root.pendingY = true; gTimer.restart() }
      }
      else if (t === "J" && reading) stepReader(1)
      else if (t === "K" && reading) stepReader(-1)
    } else if (view === "sources") {
      if (t === "n") startAdd()
      else if (t === "r") startRename()
      else if (t === "c") cycleCadence()
      else if (t === "m") startMute()
      else if (t === "w") setWeeklyDay(Model.nextWeekday(root.weeklyDay))
      else if (t === "t") startXToken("")
      else if (t === "-") stepDelivery(-30)
      else if (t === "+" || t === "=") stepDelivery(30)
    }
  }

  function handleEscape() {
    if (root.welcoming) dismissWelcome("")
    else if (root.snoozePickerId !== "") closeSnooze()
    else if (root.catchupOpen) closeCatchup()
    else if (view === "sources" && mode === "confirm") confirmRemove(false)
    else if (mode === "confirm-clear") confirmClear(false)
    else if (reading) closeReader()
    else if (view === "sources") showView("feed")
    else if (view !== "sources" && (root.query !== "" || root.filter !== "")) clearFilters()
    else root.close()
  }

  // Must match Reader.qml's body font; the sample mixes cases and spaces like running text.
  TextMetrics {
    id: readingMetrics
    font.family: root.readingFont
    font.styleName: "Regular"
    font.pixelSize: root.readerFontSize
    text: "The quick brown fox jumps over the lazy dog while Omarchy ships a release."
  }

  Timer {
    interval: 4000
    running: root.message !== "" && !root.busy && root.articleLoadingId === "" && root.view !== "sources"
    onTriggered: root.message = ""
  }

  Timer {
    id: deliveryApply
    interval: 900
    onTriggered: root.saveDelivery()
  }

  // J/K through posts restarts it, so only a post that stays open fetches its replies.
  Timer {
    id: repliesDelay
    interval: 1500
    onTriggered: root.autoFetchReplies()
  }

  Timer {
    id: gTimer
    interval: 600
    onTriggered: {
      root.pendingG = false
      root.pendingY = false
    }
  }

  NumberAnimation {
    id: scrollAnimation
    property: "contentY"
    duration: 140
    easing.type: Easing.OutCubic
  }

  Process {
    id: imageViewer
    onStarted: root.close()
    onExited: function(exitCode) {
      root.controller.show()
      if (exitCode !== 0) root.note("No picture viewer opened.")
    }
  }

  // The panel stays until `omabox play` prints "opened" (the player's window is up), so the half second X takes to
  // start a file shows on the play badge instead of an empty screen.
  Process {
    id: videoPlayer
    property bool shown: false
    property bool noPlayer: false
    onStarted: {
      shown = false
      noPlayer = false
    }
    stdout: SplitParser {
      onRead: function(data) {
        if (data === "no player") videoPlayer.noPlayer = true
        if (data !== "opened") return
        videoPlayer.shown = true
        root.openingVideo = ""
        root.close()
      }
    }
    onExited: function(exitCode) {
      root.openingVideo = ""
      if (videoPlayer.shown) root.controller.show()
      else root.note(videoPlayer.noPlayer ? "No video player found. Install mpv to play videos." : "The video did not play.")
    }
  }

  Process {
    id: cliProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var result = Model.splitCliOutput(text)
        var done = root.cliDone
        root.cliDone = null
        if (done) done(result.code, result.text)
        root.runNextCli()
      }
    }
  }

  Process {
    id: tokenProc
    command: ["bash", "-c", "\"$@\" 2>&1; echo \"::exit $?\"", "--", root.omaboxBin, "x-token", "--set"]
    stdinEnabled: true
    onStarted: {
      write(root.tokenToSend + "\n")
      root.tokenToSend = ""
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var result = Model.splitCliOutput(text)
        root.tokenSaved(result.code, result.text)
      }
    }
  }

  Process {
    id: repliesProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var result = Model.splitCliOutput(text)
        root.repliesFetched(result.code, result.text)
      }
    }
  }

  Process {
    id: historyProc
    // Archive first so Omarchy's 10-entry history and Omabox's 7-day copy agree; both dirs are listed, parseHistory dedups.
    command: ["bash", "-c", "\"$1\" archive-notifications >/dev/null 2>&1; for d in \"$2\" \"$3\"; do for f in \"$d\"/*.json; do [[ -e $f ]] && printf '%s\\t' \"${f##*/}\" && tr -d '\\n' < \"$f\" && echo; done; done",
      "--", root.omaboxBin, root.historyDir, root.archiveDir]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        root.notifications = Model.parseHistory(text)
        if (root.pendingRead >= 0 && root.view === "notifications") root.openReader(root.pendingRead)
        root.pendingRead = -1
      }
    }
  }

  FileView {
    path: root.notificationSettingsPath
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try { root.dnd = JSON.parse(text()).dnd === true } catch (e) {}
    }
  }

  Timer {
    interval: 60000
    running: root.opened
    repeat: true
    onTriggered: root.now = new Date()
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    centerOnBar: true
    open: root.opened
    focusTarget: arrowBlocker
    contentWidth: panel.fittedContentWidth(root.reading ? root.readerWidth : Style.space(520))
    contentHeight: panel.fittedContentHeight(Math.max(body.implicitHeight, root.overlayShown ? overlayCard.height + Style.space(40) : 0))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: root.typing
      onMoveRequested: function(dx, dy) {
        if (root.confirming || root.welcoming) return
        if (dx > 0) root.enter()
        else if (dx < 0) root.leave()
        if (dy !== 0) root.moveCursor(dy)
      }
      onReturnRequested: root.viaReturn = true
      onActivateRequested: {
        var viaReturn = root.viaReturn
        root.viaReturn = false
        if (root.confirming) return
        if (root.welcoming) {
          root.dismissWelcome("")
          return
        }
        if (root.catchupOpen) {
          root.catchUp("all")
          return
        }
        if (!viaReturn && root.view === "sources") root.togglePause()
        else if (!viaReturn && root.reading) root.scrollBy(Math.round(reader.flick.height * 0.9))
        else root.activate(root.cursor)
      }
      onDeleteRequested: {
        if (root.reading || root.confirming || root.welcoming) return
        if (root.view === "notifications") root.forgetNotification(root.cursor)
        else if (root.view === "sources") root.askRemove()
      }
      onCloseRequested: root.handleEscape()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) { root.handleText(t) }

      // Holds focus instead of keyCatcher and swallows arrow keys so only vim keys move;
      // everything else propagates up to keyCatcher. Text fields take focus themselves and keep their arrows.
      Item {
        id: arrowBlocker
        focus: true
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Up || event.key === Qt.Key_Down || event.key === Qt.Key_Left || event.key === Qt.Key_Right)
            event.accepted = true
          // PanelKeyCatcher maps x and X both to deleteRequested; X (clear all) is split off here.
          else if (event.text === "X" && root.view !== "sources" && root.mode === "list" && !root.reading && !root.welcoming) {
            root.askClear()
            event.accepted = true
          }
        }
      }

      // While a card shows, a see-through theme background would let the desktop through, unblurred, behind it.
      Rectangle {
        readonly property real border: Math.max(1, Style.space(2))
        visible: root.overlayShown
        anchors.fill: parent
        anchors.margins: -(Style.spacing.popupPadding - border)
        radius: Math.max(0, Style.cornerRadius - border)
        color: Qt.rgba(root.cardColor.r, root.cardColor.g, root.cardColor.b, 1)
      }

      Column {
        id: body
        // Nothing behind a card reacts to the pointer: no hover highlight, no clicks.
        enabled: !root.overlayShown
        layer.enabled: root.overlayShown
        layer.effect: MultiEffect {
          autoPaddingEnabled: false
          blurEnabled: true
          blur: 1.0
          blurMax: 40
        }
        width: parent.width
        spacing: Style.space(8)

        Item {
          visible: !root.reading
          width: parent.width
          height: visible ? tabRow.height : 0

          Row {
            id: tabRow
            spacing: Style.space(6)

            Button {
              text: "Feed"
              bordered: true
              selected: root.view === "feed"
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.showView("feed")
            }

            Button {
              text: "Notifications"
              bordered: true
              selected: root.view === "notifications"
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.showView("notifications")
            }
          }

          Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            PanelActionButton {
              visible: root.view !== "sources"
              iconText: "󰍉"
              tooltipText: "Search (/)"
              foreground: root.query !== "" ? Color.accent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.startSearch()
            }

            PanelActionButton {
              visible: root.view !== "sources"
              iconText: "󰈲"
              tooltipText: root.filter !== ""
                ? "Next filter: " + (Model.filterLabel(root.view === "feed" ? Model.nextFilter(root.filter, root.allItems)
                  : Model.nextNoteFilter(root.filter, root.notifications)) || "all").toLowerCase() + " (f)"
                : root.view === "feed" ? "Filter by source (f)" : "Filter by app (f)"
              foreground: root.filter !== "" ? Color.accent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.cycleFilter()
            }

            PanelActionButton {
              visible: root.view !== "sources"
              iconText: root.dnd ? "󰂛" : "󰂚"
              tooltipText: root.dnd ? "Do not disturb is on (d)" : "Do not disturb is off (d)"
              foreground: root.dnd ? Color.accent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.toggleDnd()
            }

            PanelActionButton {
              visible: root.view !== "sources"
              enabled: root.view === "feed" ? Model.clearableIds(root.items).length > 0 : root.notifications.length > 0
              iconText: "󰎟"
              tooltipText: root.view === "feed" ? "Clear read posts (X)" : "Clear history (X)"
              foreground: root.mode === "confirm-clear" ? Color.urgent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.mode === "confirm-clear" ? root.confirmClear(false) : root.askClear()
            }

            PanelActionButton {
              visible: root.view === "sources"
              iconText: "󰐕"
              tooltipText: "New source (n)"
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.startAdd()
            }

            PanelActionButton {
              iconText: "󰌌"
              tooltipText: root.hintsVisible ? "Hide keybinds (?)" : "Show keybinds (?)"
              foreground: root.hintsVisible ? Color.accent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.toggleHints()
            }

            PanelActionButton {
              iconText: "󰒓"
              tooltipText: root.view === "sources" ? "Back to feed (esc)" : "Sources (s)"
              foreground: root.view === "sources" ? Color.accent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.showView(root.view === "sources" ? "feed" : "sources")
            }
          }
        }

        PanelSeparator {
          visible: !root.reading
          width: parent.width
          foreground: root.fg
        }

        Row {
          visible: root.view !== "sources" && !root.reading && (root.mode === "search" || root.query !== "" || root.filter !== "")
          width: parent.width
          spacing: Style.space(10)

          Text {
            visible: root.filter !== ""
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: "󰈲  " + Model.filterLabel(root.filter)
            color: Color.accent
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          Text {
            visible: root.mode !== "search" && root.query !== ""
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: "/ " + root.query
            color: Color.accent
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          TextField {
            id: searchField
            visible: root.mode === "search"
            width: parent.width - (root.filter !== "" ? Style.space(140) : 0)
            placeholderText: root.view === "feed" ? "search titles and text" : "search apps and messages"
            foreground: root.fg
            font.family: root.fontFamily
            onTextChanged: if (root.mode === "search") { root.query = text; root.cursor = 0 }
            Keys.onPressed: function(event) {
              if (event.key === Qt.Key_Escape) { root.endSearch(false); event.accepted = true }
              else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { root.endSearch(true); event.accepted = true }
            }
          }

          PanelActionButton {
            visible: root.mode !== "search"
            anchors.verticalCenter: parent.verticalCenter
            iconText: "󰅖"
            tooltipText: "Clear search and filter (esc)"
            foreground: root.fg
            fontFamily: root.fontFamily
            onClicked: root.clearFilters()
          }
        }

        Row {
          visible: !root.catchupOpen && root.view === "feed" && !root.reading && Model.unreadCount(root.items) > 0
          spacing: Style.space(10)

          Text {
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: Model.unreadCount(root.items) + " UNREAD"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          Button {
            anchors.verticalCenter: parent.verticalCenter
            text: "Mark read"
            tooltipText: "Mark read (a)"
            bordered: true
            foreground: root.fg
            fontFamily: root.fontFamily
            fontSize: Style.font.caption
            onClicked: root.openCatchup()
          }
        }

        Flow {
          visible: root.catchupOpen && root.view === "feed" && !root.reading
          width: parent.width
          spacing: Style.space(12)

          Text {
            textFormat: Text.PlainText
            text: "MARK READ" + (root.filter !== "" ? "  ·  " + Model.filterLabel(root.filter) : "")
              + (root.query !== "" ? "  ·  / " + root.query : "")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          ChoicePicker {
            choices: root.catchupOpen ? Model.catchupChoices(root.items, root.now) : []
            foreground: root.fg
            dim: root.faint
            fontFamily: root.fontFamily
            onPicked: function(choice) { root.catchUp(choice) }
            onCancelled: root.closeCatchup()
          }
        }

        Reader {
          id: reader
          visible: root.reading
          width: parent.width
          maxHeight: root.bodyMaxHeight - reader.y - root.tailHeight - (messageLine.visible ? messageLine.height + parent.spacing : 0)
          panel: root
          item: root.readingItem
        }

        Item {
          visible: root.view === "sources" && root.deliveryTime !== ""
          width: parent.width
          height: visible ? deliveryControls.height : 0

          Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              textFormat: Text.PlainText
              text: "DELIVERY"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1.2
              font.bold: true
            }

            Text {
              textFormat: Text.PlainText
              text: "Once a day, at this time."
              color: root.faint
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }

          Row {
            id: deliveryControls
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(6)

            PanelActionButton {
              anchors.verticalCenter: parent.verticalCenter
              iconText: "󰍴"
              tooltipText: "Half an hour earlier (-)"
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.stepDelivery(-30)
            }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: root.deliveryTime
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.subtitle
              font.bold: true
            }

            PanelActionButton {
              anchors.verticalCenter: parent.verticalCenter
              iconText: "󰐕"
              tooltipText: "Half an hour later (+)"
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.stepDelivery(30)
            }
          }
        }

        Item {
          visible: root.view === "sources" && root.deliveryTime !== ""
          width: parent.width
          height: visible ? weekdayChips.height : 0

          Text {
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: "Weekly sources on"
            color: root.faint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          ButtonGroup {
            id: weekdayChips
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(4)
            focusable: false
            options: Model.weekdayOptions()
            value: root.weeklyDay
            foreground: root.fg
            background: "transparent"
            fontFamily: root.fontFamily
            fontSize: Style.font.caption
            onChanged: function(value) { root.setWeeklyDay(value) }
          }
        }

        PanelSeparator {
          visible: root.view === "sources" && root.deliveryTime !== ""
          width: parent.width
          foreground: root.fg
        }

        Text {
          visible: root.view === "sources"
          textFormat: Text.PlainText
          text: "SOURCES"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.letterSpacing: 1.2
          font.bold: true
        }

        Column {
          id: addForm
          visible: root.view === "sources" && (root.mode === "add-url" || root.mode === "add-name")
          width: parent.width
          spacing: Style.space(6)

          Row {
            width: parent.width
            spacing: Style.space(10)

            Text {
              width: Style.space(48)
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: "URL"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1
              font.bold: true
            }

            TextField {
              id: urlField
              width: parent.width - Style.space(58)
              enabled: root.mode === "add-url" && !root.busy
              placeholderText: "page, feed, YouTube, Bluesky, Mastodon, X, Reddit, HN"
              foreground: root.fg
              font.family: root.fontFamily
              Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Escape) { root.cancelTyping(); event.accepted = true }
                else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { root.lookUp(); event.accepted = true }
              }
            }
          }

          Text {
            visible: root.discovered !== null && root.mode === "add-name"
            width: parent.width
            leftPadding: Style.space(58)
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            text: root.discovered
              ? "Found: " + root.discovered.title
                + (root.discovered.latest ? "  ·  latest \"" + root.discovered.latest.title + "\" "
                  + Model.relativeTime(root.discovered.latest.published, root.now) : "  ·  no posts yet")
              : ""
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }

          Row {
            visible: root.mode === "add-name"
            width: parent.width
            spacing: Style.space(10)

            Text {
              width: Style.space(48)
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: "NAME"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1
              font.bold: true
            }

            TextField {
              id: nameField
              width: parent.width - Style.space(58)
              foreground: root.fg
              font.family: root.fontFamily
              Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Escape) { root.cancelTyping(); event.accepted = true }
                else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { root.saveNew(); event.accepted = true }
              }
            }
          }
        }

        // Outside the source rows: refreshSources rebuilds every delegate, and the editor stays open between rules.
        Column {
          id: muteForm
          visible: root.view === "sources" && root.mode === "mute" && root.currentSource !== null
          width: parent.width
          spacing: Style.space(6)

          Text {
            width: parent.width
            textFormat: Text.PlainText
            elide: Text.ElideRight
            text: "MUTE  ·  " + (root.currentSource ? root.currentSource.name.toUpperCase() : "")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          TextField {
            id: muteField
            width: parent.width
            placeholderText: root.mutePick >= 0 ? "enter removes the rule"
              : root.muteRules.length > 0 ? "word or /regex/ to leave out  ·  tab picks a rule" : "word or /regex/ to leave out"
            foreground: root.fg
            font.family: root.fontFamily
            Keys.onPressed: function(event) {
              if (event.key === Qt.Key_Escape) { root.cancelTyping(); event.accepted = true }
              else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { root.commitMute(muteField.text); event.accepted = true }
              else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Down) { root.stepMutePick(1); event.accepted = true }
              else if (event.key === Qt.Key_Backtab || event.key === Qt.Key_Up) { root.stepMutePick(-1); event.accepted = true }
            }
          }

          Flow {
            visible: root.muteRules.length > 0
            width: parent.width
            spacing: Style.space(6)

            Repeater {
              model: root.muteRules

              Rectangle {
                id: ruleChip
                required property var modelData
                required property int index
                readonly property bool picked: index === root.mutePick
                width: ruleRow.implicitWidth + Style.space(16)
                height: ruleRow.implicitHeight + Style.space(6)
                radius: height / 2
                color: ruleMouse.containsMouse ? Style.hoverFillFor(root.fg, Color.accent) : "transparent"
                border.width: 1
                border.color: picked ? Color.accent : Util.alpha(root.fg, 0.25)

                MouseArea {
                  id: ruleMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.pickMute(ruleChip.index)
                }

                Row {
                  id: ruleRow
                  anchors.centerIn: parent
                  spacing: Style.space(6)

                  Text {
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(implicitWidth, muteForm.width - Style.space(60))
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    text: ruleChip.modelData
                    color: ruleChip.picked ? Color.accent : root.fg
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                  }

                  Text {
                    anchors.verticalCenter: parent.verticalCenter
                    textFormat: Text.PlainText
                    text: "󰅖"
                    color: removeRuleMouse.containsMouse ? Color.urgent : root.faint
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall

                    MouseArea {
                      id: removeRuleMouse
                      anchors.fill: parent
                      anchors.margins: -Style.space(4)
                      hoverEnabled: true
                      cursorShape: Qt.PointingHandCursor
                      onClicked: root.removeMute(ruleChip.modelData)
                    }

                    PanelToolTip {
                      visible: removeRuleMouse.containsMouse
                      text: "Remove rule"
                      fontFamily: root.fontFamily
                    }
                  }
                }
              }
            }
          }

          Row {
            visible: !!(root.currentSource && root.currentSource.x_hidden)
            spacing: Style.space(10)

            readonly property bool repostsHidden: !!(root.currentSource && root.currentSource.x_hidden && root.currentSource.x_hidden.reposts)

            Text {
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: parent.repostsHidden ? "X reposts are left out" : "X reposts come in"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
            }

            Button {
              text: parent.repostsHidden ? "Show reposts" : "Hide reposts"
              bordered: true
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.toggleReposts()
            }
          }
        }

        Text {
          id: messageLine
          visible: root.busy || root.message !== ""
          width: parent.width
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          text: root.busy ? "Looking…" : root.message
          color: root.busy || !root.messageError ? root.dim : Color.urgent
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
        }

        Text {
          visible: root.rows.length === 0 && !root.reading
          width: parent.width
          topPadding: Style.space(24)
          bottomPadding: Style.space(24)
          horizontalAlignment: Text.AlignHCenter
          textFormat: Text.PlainText
          text: root.view === "notifications" ? "No notifications. Quiet day."
            : root.view === "sources" ? "No sources. Press n to add one." : "Nothing here yet."
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        // One ListView per view: swapping model and delegate on a shared one feeds rows to the wrong delegate for a frame.
        ListView {
          id: feedList
          visible: root.view === "feed" && !root.reading && count > 0
          width: parent.width
          height: visible ? root.listHeight(feedList) : 0
          clip: true
          spacing: Style.space(2)
          boundsBehavior: Flickable.StopAtBounds
          Component.onCompleted: model = root.items
          delegate: feedRow
        }

        ListView {
          id: notificationList
          visible: root.view === "notifications" && !root.reading && count > 0
          width: parent.width
          height: visible ? root.listHeight(notificationList) : 0
          clip: true
          spacing: Style.space(2)
          boundsBehavior: Flickable.StopAtBounds
          Component.onCompleted: model = root.noteRows
          delegate: notificationRow
        }

        ListView {
          id: sourceList
          visible: root.view === "sources" && count > 0
          width: parent.width
          height: visible ? root.listHeight(sourceList) : 0
          clip: true
          spacing: Style.space(2)
          boundsBehavior: Flickable.StopAtBounds
          model: root.sources
          delegate: sourceRow
        }

        PanelSeparator {
          id: listSeparator
          width: parent.width
          foreground: root.fg
        }

        Text {
          id: statusLine
          visible: (root.view !== "sources" || root.mode === "confirm") && !root.reading
          width: parent.width
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          text: root.mode === "confirm" && root.currentSource ? "Remove " + root.currentSource.name + " and its posts?"
            : root.mode === "confirm-clear" ? root.clearQuestion
            : root.view === "feed"
              ? Model.deliveredLabel(root.feedState, root.now, root.deliveryTime, hostWidget ? hostWidget.tickProblem : "")
                + (root.errorSources.length > 0 ? "  ·  failed: " + root.errorSources.join(", ") : "")
              : root.notifications.length + " from the last 7 days"
          color: root.confirming ? root.fg
            : root.view === "feed" && root.hostWidget && root.hostWidget.tickProblem !== "" ? Color.urgent : root.faint
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.letterSpacing: 1
        }

        Row {
          id: confirmRow
          visible: (root.view === "sources" && root.mode === "confirm") || root.mode === "confirm-clear"
          spacing: Style.space(6)

          Button {
            text: root.mode === "confirm-clear" ? "Clear" : "Remove"
            bordered: true
            foreground: Color.urgent
            fontFamily: root.fontFamily
            onClicked: root.mode === "confirm-clear" ? root.confirmClear(true) : root.confirmRemove(true)
          }

          Button {
            text: "Keep"
            bordered: true
            foreground: root.fg
            fontFamily: root.fontFamily
            onClicked: root.mode === "confirm-clear" ? root.confirmClear(false) : root.confirmRemove(false)
          }
        }

        Flow {
          id: hintsFlow
          visible: root.hintsVisible || root.confirming
          width: parent.width
          spacing: Style.space(12)

          Repeater {
            model: Model.hintEntries(root.view, root.mode, root.reading)

            Row {
              required property var modelData
              spacing: Style.space(5)

              Text {
                textFormat: Text.PlainText
                text: modelData.key
                color: Color.accent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }

              Text {
                visible: text !== ""
                textFormat: Text.PlainText
                text: modelData.label
                color: root.faint
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }
        }
      }

      // Welcome and the X token guide sit in the middle of the panel over a blurred copy of it.
      MouseArea {
        anchors.fill: parent
        visible: root.overlayShown
        hoverEnabled: true
        acceptedButtons: Qt.AllButtons
        onWheel: function(wheel) { wheel.accepted = true }

        Rectangle {
          anchors.fill: parent
          color: Util.alpha(root.cardColor, 0.35)
        }

        Rectangle {
          id: overlayCard
          anchors.centerIn: parent
          width: Math.min(parent.width - Style.space(32), Style.space(470))
          height: overlayColumn.implicitHeight + Style.space(36)
          radius: Style.cornerRadius
          // Opaque even when the theme's popups are see-through, so the guide reads cleanly over the blur.
          color: Qt.rgba(root.cardColor.r, root.cardColor.g, root.cardColor.b, 1)
          border.width: 1
          border.color: Util.alpha(Color.accent, 0.45)

          Column {
            id: overlayColumn
            x: Style.space(18)
            y: Style.space(18)
            width: parent.width - Style.space(36)
            spacing: Style.space(10)

              Column {
                id: welcomeColumn
                visible: root.welcoming
                width: parent.width
                spacing: Style.space(10)

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: "Welcome to Omabox"
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  font.bold: true
                }

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  wrapMode: Text.WordWrap
                  lineHeight: 1.25
                  text: "A quiet inbox. Your feeds arrive once a day, at " + (root.deliveryTime || "08:00")
                    + ", all together, instead of all day long. In between there is nothing new to check, so you can get on with your day."
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                }

                Repeater {
                  model: [
                    "Add your own sources in Sources: blogs, YouTube channels, Reddit, Bluesky, Mastodon and X.",
                    "Notifications keeps every desktop notification for 7 days, so nothing is lost when one slips by.",
                    "Every action has a key. Press ? at any time to see them."
                  ]

                  Text {
                    required property var modelData
                    width: welcomeColumn.width
                    leftPadding: Style.space(14)
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    text: "•  " + modelData
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                  }
                }

                Row {
                  spacing: Style.space(6)

                  Button {
                    text: "Start reading"
                    bordered: true
                    foreground: Color.accent
                    fontFamily: root.fontFamily
                    onClicked: root.dismissWelcome("")
                  }

                  Button {
                    text: "Add a source"
                    bordered: true
                    foreground: root.fg
                    fontFamily: root.fontFamily
                    onClicked: root.dismissWelcome("add")
                  }
                }
              }
            Column {
              id: tokenForm
              visible: root.view === "sources" && root.mode === "x-token"
              width: parent.width
              spacing: Style.space(8)

              Text {
                width: parent.width
                textFormat: Text.PlainText
                text: root.xTokenSaved ? "Replace your X token" : "Connect an X account"
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }

              Text {
                width: parent.width
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                text: "Read this first. X has no public feeds, so Omabox reads X with your login. The token below is that login: "
                  + "whoever has it can use the account as you. X's rules do not allow reading this way and X can lock the account, "
                  + "so use a spare account, not your main one."
                color: Color.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                width: parent.width
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                text: "What Omabox does with it: the token stays in a file only you can read, and goes only to one fixed, "
                  + "checked version of RSSHub that runs on this computer during a delivery and stops right after. That version "
                  + "can only read X: it has no code that posts, likes, follows, sends messages or deletes anything."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Repeater {
                model: [
                  "1.  In your browser, sign in to x.com with the account Omabox should use.",
                  "2.  Open the developer tools (F12), then Application in Chromium or Storage in Firefox, then Cookies, then https://x.com.",
                  "3.  Copy the value of auth_token (about 40 letters and digits) and paste it below."
                ]

                Text {
                  required property var modelData
                  width: tokenForm.width
                  textFormat: Text.PlainText
                  wrapMode: Text.WordWrap
                  text: modelData
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                }
              }

              Row {
                width: parent.width
                spacing: Style.space(10)

                Text {
                  width: Style.space(48)
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: "TOKEN"
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.letterSpacing: 1
                  font.bold: true
                }

                TextField {
                  id: tokenField
                  width: parent.width - Style.space(58)
                  password: true
                  enabled: !tokenProc.running
                  placeholderText: "auth_token value"
                  foreground: root.fg
                  font.family: root.fontFamily
                  Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Escape) { root.pendingXUrl = ""; root.cancelTyping(); event.accepted = true }
                    else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { root.saveXToken(); event.accepted = true }
                  }
                }
              }

              Text {
                width: parent.width
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                text: "Signing out of x.com, or \"Log out of all other sessions\" in X's settings, makes the token useless at once."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Button {
                visible: root.xTokenSaved
                text: "Remove the saved token"
                bordered: true
                foreground: Color.urgent
                fontFamily: root.fontFamily
                onClicked: root.removeXToken()
              }
            }


            Text {
              visible: root.mode === "x-token" && root.messageError && root.message !== ""
              width: parent.width
              textFormat: Text.PlainText
              wrapMode: Text.WordWrap
              text: root.message
              color: Color.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
            }
          }
        }
      }
    }
  }

  Component {
    id: feedRow

    Rectangle {
      id: row
      required property var modelData
      required property int index
      readonly property var item: modelData
      readonly property string tag: Model.versionTag(item, root.feedState.installed)
      readonly property bool current: index === root.cursor
      // Read posts recede by colour only: a lighter weight would rewrap the title and change the row's height.
      readonly property color dimColor: current ? root.selectedDim : root.dim
      readonly property color metaColor: item.read ? (current ? root.selectedFaint : root.faint) : dimColor

      width: ListView.view.width
      height: rowColumn.implicitHeight + Style.space(16) + (rowSnooze.visible ? rowSnooze.height + Style.space(8) : 0)
      radius: Style.cornerRadius
      color: current
        ? Style.selectedFillFor(root.fg, Color.accent)
        : (rowHover.hovered ? Style.hoverFillFor(root.fg, Color.accent) : "transparent")

      HoverHandler {
        id: rowHover
        onHoveredChanged: if (!hovered && root.snoozePickerId === row.item.id) root.closeSnooze()
      }

      // Own line under the post: the row grows instead of the picker covering a long title.
      ChoicePicker {
        id: rowSnooze
        z: 1
        visible: root.snoozePickerId === row.item.id
        x: Style.space(10)
        y: rowColumn.y + rowColumn.implicitHeight + Style.space(8)
        choices: Model.snoozeChoices()
        foreground: root.fg
        dim: root.faint
        fontFamily: root.fontFamily
        onPicked: function(choice) { root.snoozeItem(row.item, choice) }
        onCancelled: root.closeSnooze()
      }

      MouseArea {
        id: rowMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        onClicked: function(mouse) {
          if (mouse.button === Qt.MiddleButton) root.openLink(row.index)
          else root.activate(row.index)
        }
      }

      Row {
        id: rowActions
        z: 1
        visible: rowHover.hovered && root.snoozePickerId !== row.item.id
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: Style.space(4)
        spacing: Style.space(2)

        PanelActionButton {
          iconText: row.item.later === true ? "󰃀" : "󰃃"
          tooltipText: row.item.later === true ? "Remove from read later (m)" : "Read later (m)"
          foreground: row.item.later === true ? Color.accent : root.fg
          fontFamily: root.fontFamily
          onClicked: root.toggleLaterCurrent(row.item)
        }

        PanelActionButton {
          iconText: "󰒲"
          tooltipText: "Snooze (z)"
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: root.openSnooze(row.item)
        }

        PanelActionButton {
          visible: row.tag === "newer"
          iconText: "󰚰"
          tooltipText: "Update Omarchy (U)"
          foreground: Color.accent
          fontFamily: root.fontFamily
          onClicked: root.runUpdate(row.item)
        }

        PanelActionButton {
          visible: !!row.item.link
          iconText: "󰏌"
          tooltipText: "Open in browser (o)"
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: root.openLink(row.index)
        }

        PanelActionButton {
          visible: !!row.item.link
          iconText: "󰆏"
          tooltipText: "Copy link (yy)"
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: root.copyLink(row.item)
        }
      }


      Column {
        id: rowColumn
        x: Style.space(10)
        y: Style.space(8)
        width: parent.width - Style.space(20)
        spacing: Style.space(3)

        Row {
          spacing: Style.space(8)

          Rectangle {
            visible: row.item !== null && !row.item.read
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(6)
            height: width
            radius: width / 2
            color: Color.accent
          }

          SourceIcon {
            anchors.verticalCenter: parent.verticalCenter
            icon: row.item && root.feedState.icons ? (root.feedState.icons[row.item.source] || {}) : ({})
            color: row.metaColor
            fontFamily: root.fontFamily
            size: Style.font.body
          }

          Text {
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: row.item ? (row.item.source + "  ·  " + Model.relativeTime(row.item.published, root.now)).toUpperCase() : ""
            color: row.metaColor
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          Text {
            visible: !!row.item.repost
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: row.item.repost ? ("·  󰑖 " + row.item.repost.name).toUpperCase() : ""
            color: row.metaColor
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          Text {
            visible: row.tag !== ""
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: "·  " + (row.tag === "newer" ? "NEWER THAN YOURS" : "INSTALLED")
            color: row.tag === "newer" ? Color.accent : row.metaColor
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          Text {
            visible: row.item.later === true
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: "·  󰃀 LATER"
            color: Color.accent
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }
        }

        Text {
          width: parent.width
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          text: row.item.title
          color: row.item.read ? row.dimColor : root.fg
          font.family: root.readingFont
          font.styleName: "Bold"
          font.pixelSize: Style.font.title
        }

        // Release notes list their sections ("Improvements 3  ·  Fixes 12"); other posts show their opening lines.
        Text {
          visible: text !== ""
          width: parent.width
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          maximumLineCount: 2
          elide: Text.ElideRight
          text: row.item.summary || row.item.excerpt || ""
          color: row.dimColor
          font.family: row.item.summary ? root.fontFamily : root.readingFont
          font.styleName: row.item.summary ? "" : "Regular"
          font.pixelSize: row.item.summary ? Style.font.caption : Style.font.body
          font.letterSpacing: row.item.summary ? 0.5 : 0
        }
      }
    }
  }

  Component {
    id: notificationRow

    Rectangle {
      id: note
      required property var modelData
      required property int index
      readonly property color dimColor: index === root.cursor ? root.selectedDim : root.dim

      width: ListView.view.width
      height: noteColumn.implicitHeight + Style.space(16)
      radius: Style.cornerRadius
      color: index === root.cursor
        ? Style.selectedFillFor(root.fg, Color.accent)
        : (noteHover.hovered ? Style.hoverFillFor(root.fg, Color.accent) : "transparent")

      // HoverHandler, not noteMouse.containsMouse: the copy button's own MouseArea takes hover from noteMouse.
      HoverHandler { id: noteHover }

      MouseArea {
        id: noteMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.activate(note.index)
      }

      Row {
        z: 1
        visible: noteHover.hovered
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: Style.space(4)
        spacing: Style.space(2)

        PanelActionButton {
          iconText: "󰆏"
          tooltipText: "Copy message (yy)"
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: root.copyNotification(note.index)
        }

        PanelActionButton {
          iconText: "󰅖"
          tooltipText: "Remove (x)"
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: root.forgetNotification(note.index)
        }
      }

      Text {
        id: noteGlyph
        x: Style.space(10)
        y: Style.space(8)
        width: Style.space(22)
        textFormat: Text.PlainText
        text: Model.appGlyph(note.modelData)
        color: note.dimColor
        font.family: root.fontFamily
        font.pixelSize: Style.font.icon
      }

      Column {
        id: noteColumn
        x: noteGlyph.x + noteGlyph.width + Style.space(8)
        y: Style.space(8)
        width: parent.width - x - Style.space(10)
        spacing: Style.space(3)

        Text {
          textFormat: Text.PlainText
          text: [Model.appLabel(note.modelData), Model.relativeTime(new Date(note.modelData.timestamp || 0).toISOString(), root.now)]
            .filter(function(part) { return part !== "" }).join("  ·  ").toUpperCase()
          color: note.dimColor
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.letterSpacing: 1
          font.bold: true
        }

        Text {
          visible: text !== ""
          width: parent.width
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          text: note.modelData.summary || ""
          color: root.fg
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
        }

        Text {
          visible: text !== ""
          width: parent.width
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          maximumLineCount: 4
          elide: Text.ElideRight
          text: Model.plainBody(note.modelData.body)
          color: note.dimColor
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
        }
      }
    }
  }

  Component {
    id: sourceRow

    Rectangle {
      id: source
      required property var modelData
      required property int index
      readonly property bool current: index === root.cursor
      readonly property color dimColor: current ? root.selectedDim : root.dim
      readonly property color faintColor: current ? root.selectedFaint : root.faint
      readonly property bool renaming: current && root.mode === "rename"
      property alias renameField: renameInput

      width: ListView.view.width
      height: sourceColumn.implicitHeight + Style.space(16)
      radius: Style.cornerRadius
      color: current
        ? Style.selectedFillFor(root.fg, Color.accent)
        : (sourceHover.hovered ? Style.hoverFillFor(root.fg, Color.accent) : "transparent")

      HoverHandler { id: sourceHover }

      MouseArea {
        id: sourceMouse
        anchors.fill: parent
        hoverEnabled: true
        onClicked: {
          root.selectSource(source.index)
          arrowBlocker.forceActiveFocus()
        }
        onDoubleClicked: root.startRename()
      }

      Row {
        id: sourceActions
        visible: sourceHover.hovered && !source.renaming && root.mode !== "confirm"
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: Style.space(4)
        spacing: Style.space(2)

        PanelActionButton {
          iconText: "󰏫"
          tooltipText: "Rename (r)"
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: { root.selectSource(source.index); root.startRename() }
        }

        PanelActionButton {
          iconText: "󰈉"
          tooltipText: "Mute rules (m)"
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: { root.selectSource(source.index); root.startMute() }
        }

        PanelActionButton {
          iconText: source.modelData.cadence === "paused" ? "󰐊" : "󰏤"
          tooltipText: source.modelData.cadence === "paused" ? "Resume (space)" : "Pause (space)"
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: { root.selectSource(source.index); root.togglePause() }
        }

        PanelActionButton {
          iconText: "󰆴"
          tooltipText: "Remove (x)"
          foreground: Color.urgent
          fontFamily: root.fontFamily
          onClicked: { root.selectSource(source.index); root.askRemove() }
        }
      }

      Column {
        id: sourceColumn
        x: Style.space(10)
        y: Style.space(8)
        width: parent.width - Style.space(20)
        spacing: Style.space(3)

        Item {
          width: parent.width
          height: Math.max(nameLabel.implicitHeight, renameInput.visible ? renameInput.implicitHeight : 0, cadenceLabel.height)

          SourceIcon {
            id: sourceIcon
            anchors.verticalCenter: parent.verticalCenter
            icon: source.modelData.icon || ({})
            color: String(source.modelData.cadence) === "paused" ? source.faintColor : root.fg
            fontFamily: root.fontFamily
            size: Style.font.subtitle
          }

          Text {
            id: nameLabel
            visible: !source.renaming
            anchors.verticalCenter: parent.verticalCenter
            x: sourceIcon.width + Style.space(8)
            width: parent.width - x - cadenceLabel.width - Style.space(10)
            textFormat: Text.PlainText
            elide: Text.ElideRight
            text: source.modelData.name
            color: source.modelData.cadence === "paused" ? source.dimColor : root.fg
            font.family: root.fontFamily
            font.pixelSize: Style.font.subtitle
            font.bold: true
          }

          TextField {
            id: renameInput
            visible: source.renaming
            anchors.verticalCenter: parent.verticalCenter
            x: sourceIcon.width + Style.space(8)
            width: parent.width - x - cadenceLabel.width - Style.space(10)
            foreground: root.fg
            font.family: root.fontFamily
            Keys.onPressed: function(event) {
              if (event.key === Qt.Key_Escape) { root.cancelTyping(); event.accepted = true }
              else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { root.commitRename(renameInput.text); event.accepted = true }
            }
          }

          ButtonGroup {
            id: cadenceLabel
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(4)
            focusable: false
            options: [{ value: "daily", label: "Daily" }, { value: "weekly", label: "Weekly" }, { value: "paused", label: "Paused" }]
            value: String(source.modelData.cadence || "")
            foreground: root.fg
            background: "transparent"
            fontFamily: root.fontFamily
            fontSize: Style.font.caption
            onChanged: function(value) {
              root.selectSource(source.index)
              root.setCadence(value)
            }
          }
        }

        Text {
          width: parent.width - (sourceActions.visible ? sourceActions.width + Style.space(4) : 0)
          textFormat: Text.PlainText
          elide: Text.ElideMiddle
          text: Model.shortUrl(source.modelData.url)
          color: source.faintColor
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
        }

        Text {
          readonly property bool full: Model.errorNeedsFullText(source.modelData.error)
          width: parent.width - (sourceActions.visible ? sourceActions.width + Style.space(4) : 0)
          textFormat: Text.PlainText
          wrapMode: full ? Text.WordWrap : Text.NoWrap
          elide: full ? Text.ElideNone : Text.ElideRight
          text: Model.sourceStatus(source.modelData, root.now) + "  ·  " + source.modelData.items + " posts"
            + Model.muteSummary(source.modelData)
          color: source.modelData.error ? Color.urgent : source.faintColor
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }

        Text {
          visible: text !== ""
          width: parent.width - (sourceActions.visible ? sourceActions.width + Style.space(4) : 0)
          textFormat: Text.PlainText
          elide: Text.ElideRight
          text: Model.staleLabel(source.modelData.stale).toUpperCase()
          color: source.modelData.stale && source.modelData.stale.kind === "failing" ? Color.urgent : source.dimColor
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.letterSpacing: 1
          font.bold: true
        }
      }
    }
  }
}
