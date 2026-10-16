import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
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

  readonly property color fg: bar ? bar.foreground : Commons.Color.foreground
  // Secondary text, solid: dim is for text read as text (excerpts, read titles), faint for small meta and hints.
  // Targets sit above WCAG's 4.5 and 3 because antialiased thin text renders lighter than its colour.
  readonly property color dim: Model.readableShade(fg, opaqueCard, 0.6, 4.9)
  readonly property color faint: Model.readableShade(fg, opaqueCard, 0.4, 3.4)
  // The same two on the cursor row's fill.
  readonly property color selectedDim: Model.readableShade(fg, selectedCard, 0.6, 4.9)
  readonly property color selectedFaint: Model.readableShade(fg, selectedCard, 0.4, 3.4)
  readonly property color readText: Model.readShade(fg, opaqueCard)
  readonly property color selectedReadText: Model.readShade(fg, selectedCard)
  readonly property color opaqueCard: Qt.rgba(cardColor.r, cardColor.g, cardColor.b, 1)
  readonly property color selectedCard: Qt.tint(opaqueCard, Style.selectedFillFor(fg, Commons.Color.accent))
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  // ttf-ia-writer tags every Quattro file as weight 80, so Qt picks Bold unless the style is named explicitly.
  readonly property string readingFont: setting("readingFont", "iA Writer Quattro S")
  readonly property color cardColor: Commons.Color.popups.background
  // Reader width follows the measure (characters per line), not pixels, so theme font sizes keep ~70ch lines.
  readonly property int readingMeasure: Math.max(45, Math.min(100, Number(setting("readingMeasure", 70)) || 70))
  readonly property real readingCharWidth: readingMetrics.advanceWidth / readingMetrics.text.length
  readonly property int readerWidth: Math.max(Style.space(520), Math.round(readingCharWidth * readingMeasure))

  readonly property string home: Quickshell.env("HOME")
  readonly property string omaboxBin: Model.localPath(Qt.resolvedUrl("bin/omabox"))
  readonly property string imageDir: (Quickshell.env("XDG_CACHE_HOME") || (home + "/.cache")) + "/omabox/images"
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
  // Set by the first answer, so the empty states do not flash while the CLI is still reading.
  property bool sourcesLoaded: false
  property bool notificationsLoaded: false
  property var discovered: null
  property bool busy: false
  property string message: ""
  property bool messageError: false
  // file of the notification whose action the first o showed (Model.actionStep); the second o runs it
  property string pendingAction: ""
  property bool viaReturn: false
  property var cliQueue: []
  // HH:MM of the daily delivery (`omabox delivery`), "" until loaded; -/+ in sources move it, deliveryApply saves.
  property string deliveryTime: ""
  // From `omabox delivery --json`, refreshed while the panel is open: a fetch is running, and the name of an unreadable
  // items.json the CLI moved aside (shown until that file is gone).
  property bool fetching: false
  property string cliRecoveredFile: ""
  property bool deliveryKnown: false
  // items.json names the moved-aside file too, so the notice is there from the first frame; the CLI's answer wins
  // once it came, as it also knows whether that file still exists.
  readonly property string recoveredFile: deliveryKnown ? cliRecoveredFile
    : String(feedState.recovered && feedState.recovered.file || "")
  readonly property string stateDir: (Quickshell.env("XDG_STATE_HOME") || (home + "/.local/state")) + "/omabox"
  readonly property string stateDirLabel: stateDir.indexOf(home + "/") === 0 ? "~" + stateDir.slice(home.length) : stateDir
  property string weeklyDay: "mon"
  // Rows the feed and notification lists show before they scroll (`omabox rows`); 0 fits them to the screen.
  property int feedRows: 0
  property int notificationRows: 0
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
    : view === "notifications" ? Model.noteAsItem(noteRows[readingIndex], Tr) : items[readingIndex]
  // A stored full article is what the reader shows; feedVersionId is the post switched back to its feed html.
  property string feedVersionId: ""
  // Stays set after the viewer or player closes, until the next open(): the reader keeps its body (and scroll) meanwhile.
  property bool viewingMedia: false
  // "<post id>:<video index>" while the player loads that video; the reader shows it on the video's play badge.
  property string openingVideo: ""
  property string articleLoadingId: ""
  // Link-only posts whose article fetch failed this session (often a paywall's 403); only r retries them.
  property var articleFailed: ({})
  // Replies fetch in their own Process, off the CLI queue (real X request, starts RSSHub: 4-60 s).
  // repliesFailed: ids whose fetch errored this session; only C retries them.
  property string repliesLoadingId: ""
  property var repliesFailed: ({})
  readonly property var readingItem: Model.withReplies(Model.articleView(readingPost, feedVersionId !== "" && feedVersionId === readingId),
    repliesLoadingId !== "" && repliesLoadingId === readingId, Tr)
  readonly property var scroller: reading ? reader.flick : list
  readonly property string readerCss: Model.readerCss({
    gap: Style.space(10),
    accent: "" + Commons.Color.accent,
    fg: "" + fg,
    faint: "" + faint,
    codeBg: "" + Qt.tint(cardColor, Util.alpha(fg, 0.09)),
    quoteBg: "" + Qt.tint(cardColor, Util.alpha(fg, 0.06)),
    small: Style.font.bodySmall,
    caption: Style.font.caption,
    heading: Style.font.heading + Style.space(4),
    mono: fontFamily,
    line: "" + Qt.tint(cardColor, Util.alpha(fg, 0.2)),
    opBg: "" + Qt.tint(cardColor, Util.alpha(Commons.Color.accent, 0.12)),
    pad: commentFaces.pad
  })
  readonly property var commentFaces: ({ avatar: Style.space(30), gap: Style.space(10), pad: Style.space(8), mini: Style.space(22) })
  readonly property string clearQuestion: {
    if (view === "notifications")
      return Tr.tn("notifications.clearQuestion", notifications.length).arg(Tr.formatNumber(notifications.length))
    var count = Model.clearableIds(items).length
    return Tr.tn("feed.clearQuestion", count).arg(Tr.formatNumber(count))
  }
  readonly property var currentSource: view === "sources" && cursor < sources.length ? sources[cursor] : null
  readonly property var muteRules: currentSource && currentSource.mute ? currentSource.mute : []
  // Lists and the reader take what the screen leaves after the panel's own chrome; the Style caps keep their usual
  // size on taller screens. `panel` is the KeyboardPanel below, whose availableCardHeight is the screen minus bar and gaps.
  readonly property real bodyMaxHeight: panel.availableCardHeight > 0 ? panel.availableCardHeight - panel.verticalContentInset : 1e6
  // What the body shows under the lists.
  readonly property real tailHeight: [statusLine, confirmRow, hintsFlow]
    .reduce(function(sum, item) { return sum + (item.visible ? item.height + body.spacing : 0) }, 0)

  function listHeight(list) {
    var fit = Math.max(Style.space(120), bodyMaxHeight - list.y - tailHeight)
    var cap = list.rowCap <= 0 ? Style.space(560)
      : list.count > list.rowCap ? (list.capHeight || Math.min(fit, Style.space(560))) : list.contentHeight
    return Math.min(cap, list.contentHeight, fit)
  }

  onViewChanged: if (view === "sources") { feedList.measureCap(); notificationList.measureCap() }

  // Whole rows that fit: fitRows in Fit's height, maxRows (at most 10) on the screen. A hidden list uses the room it
  // had when last shown; notifications not shown yet get the feed's room plus its unread slot, the only feed-only row
  // above the lists. A row not built (scrolled away) leaves what it would decide as it was.
  function measureRows(list) {
    if (list.visible) {
      list.shownRoom = Math.max(Style.space(120), bodyMaxHeight - list.y - tailHeight)
      if (list === feedList) feedList.unreadAbove = unreadSlot.visible
    }
    var room = list.shownRoom
    if (room <= 0 && list === notificationList && feedList.shownRoom > 0)
      room = feedList.shownRoom + (feedList.unreadAbove ? unreadSlot.height + body.spacing : 0)
    var first = list.itemAtIndex(0)
    if (room <= 0 || !first) return
    var fitRoom = Math.min(Style.space(560), room), fits = -1, i = 0
    for (; i < list.count; i++) {
      var item = list.itemAtIndex(i)
      if (!item) return
      var bottom = item.y + item.height - first.y
      if (fits < 0 && bottom > fitRoom) fits = i
      if (fits >= 0) list.fitRows = fits
      if (bottom > room) break
    }
    if (fits < 0) list.fitRows = list.count
    list.maxRows = Math.min(10, i)
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
    var requestedSearch = hostWidget && typeof hostWidget.takeRequestedSearch === "function" ? hostWidget.takeRequestedSearch() : null
    root.picking = false
    showView(requested || "feed")
    loadDelivery()
    // Every open, whatever the view: switching to Notifications must not show the previous list first.
    refreshNotifications()
    // The notification list loads asynchronously; its reader opens once the list arrives.
    if (requestedPost) openPostById(requestedPost)
    else if (requestedSearch !== null) pickSearch(requestedSearch)
    else if (requestedRead >= 0 && root.view === "notifications") root.pendingRead = requestedRead
    else if (requestedRead >= 0) openReader(requestedRead)
    root.controller.show()
  }

  function close() {
    if (typing) focusCatcher()
    root.picking = false
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
    note(Tr.tn("feed.markedRead", ids.length).arg(Tr.formatNumber(ids.length)))
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
    copyText(link, Model.fill(Tr.t("feed.copiedLink"), [link]), true)
  }

  // The note shows once wl-copy answered, so a missing or failing wl-copy is reported instead of "Copied". wl-copy forks
  // a child that serves the clipboard; its output goes to /dev/null so that child holds none of this Process's pipes.
  // The text goes through stdin, never argv: argv is readable by every local user and notifications hold sign-in codes.
  // Anything but a plain copy is marked sensitive, so clipboard history skips it.
  function copyText(text, done, plain) {
    if (copyProc.running) return
    copyProc.done = done
    copyProc.text = text
    copyProc.plain = plain === true
    copyProc.stdinEnabled = true
    copyProc.running = true
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
      // on stdin like runCli: which videos the user watches stays out of argv
      // no deadline: it runs while the video plays
      videoPlayer.command = Model.capped([root.omaboxBin, "--args-on-stdin"], Model.SMALL_OUTPUT_BYTES)
      videoPlayer.stdinArgs = JSON.stringify(["play", "--start", String(media.index), "--"].concat(urls)) + "\n"
      videoPlayer.stdinEnabled = true
      videoPlayer.running = true
    } else if (media.kind === "picture" && paths.length > 0) {
      root.viewingMedia = true
      // on stdin too: cache names hash the pictures' addresses
      imageViewer.command = Model.capped([root.omaboxBin, "--args-on-stdin"], Model.SMALL_OUTPUT_BYTES)
      imageViewer.stdinArgs = JSON.stringify(["view", "--start", String(media.index), "--"].concat(paths)) + "\n"
      imageViewer.stdinEnabled = true
      imageViewer.running = true
    } else {
      note(Tr.t("reader.noMedia"))
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
    fetchArticle(post)
    return "fetching"
  }

  // repliesDelay's end: a link-only post that stays open gets its article without r.
  function autoFetchArticle() {
    var post = root.readingPost
    if (!root.opened || !reading || view !== "feed" || !Model.articleAvailable(post, feedState.profiles)) return
    if (post.full_html || !Model.linkOnly(post) || root.articleLoadingId !== "" || root.articleFailed[post.id]) return
    fetchArticle(post)
  }

  function fetchArticle(post) {
    root.articleLoadingId = post.id
    note(Tr.t("reader.fetchingArticle"))
    runCli(["article", "--json", "--", post.id], function(code, text) {
      root.articleLoadingId = ""
      var result = null
      try { result = JSON.parse(text) } catch (e) {}
      if (code !== 0 || !result || result.error || !result.full_html) {
        var failed = {}
        for (var key in root.articleFailed) failed[key] = true
        failed[post.id] = true
        root.articleFailed = failed
        root.messageError = true
        root.message = Model.fill(Tr.t("reader.noArticle"), [result && result.error ? result.error : text || Tr.t("reader.articleCommandFailed")])
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
    repliesProc.command = Model.bounded([root.omaboxBin, "--args-on-stdin"], Model.CLI_OUTPUT_BYTES, 300)
    repliesProc.stdinArgs = JSON.stringify(["replies", "--json"].concat(refresh ? ["--refresh"] : [], ["--", post.id])) + "\n"
    repliesProc.stdinEnabled = true
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
      root.message = Model.fill(Tr.t("reader.noComments"), [result && result.error ? result.error : text || Tr.t("reader.repliesCommandFailed")])
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
    // Version tags are only refreshed at delivery; `fetch --offline` redoes them right after the update so "newer"
    // clears. The launcher runs this in the terminal and checks the last status, so the update's status goes last.
    var bin = "'" + root.omaboxBin.replace(/'/g, "'\\''") + "'"
    Quickshell.execDetached(["omarchy-launch-floating-terminal-with-presentation",
      "omarchy-update; status=$?; " + bin + " fetch --offline >/dev/null 2>&1; (exit $status)"])
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

  // `omabox pick`: the search works as a launcher does. The arrows move while typing, Enter opens the post under the
  // cursor in the reader and Escape closes the panel.
  property bool picking: false

  function pickSearch(query) {
    showView("feed")
    clearFilters()
    root.picking = true
    root.query = Model.spliceField("", 0, 0, query, searchField.maxChars).text
    startSearch()
  }

  function pickCurrent() {
    var item = feedItemAt(root.cursor)
    if (!item || !item.id) return
    root.picking = false
    root.mode = "list"
    focusCatcher()
    openPostById(item.id)
  }

  function endSearch(keep) {
    root.picking = false
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
    if (view === "feed" && Model.clearableIds(items).length === 0) note(Tr.t("feed.nothingToClear"))
    else if (view === "notifications" && notifications.length === 0) note(Tr.t("notifications.nothingToClear"))
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
    runCli(["clear-read", "--"].concat(ids), function() {})
    root.cursor = 0
    note(Tr.tn("feed.cleared", ids.length).arg(Tr.formatNumber(ids.length)))
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
    runCli(["forget-notification", "--", row.file], function() {})
  }

  function runNotificationAction(index) {
    var row = index >= 0 && index < noteRows.length ? noteRows[index] : null
    var step = Model.actionStep(row, root.pendingAction, root.message, Tr)
    root.pendingAction = step.pending
    if (!step.run) {
      note(step.message)
      return
    }
    root.message = ""
    Quickshell.execDetached(step.run)
    root.close()
  }

  function copyNotification(index) {
    var row = index >= 0 && index < noteRows.length ? noteRows[index] : null
    var text = row ? Model.plainBody(row.body) || String(row.summary || "") : ""
    if (!text) return
    copyText(text, Model.fill(Tr.t("notifications.copied"), [text.length > 60 ? text.slice(0, 60) + "…" : text]))
  }

  function toggleHints() {
    persistSettings({ hints: !root.hintsVisible })
  }

  // ---- omabox CLI: the one writer of sources.toml and items.json. Arguments go on stdin (--args-on-stdin), never argv,
  // which every local user can read: they carry feed URLs (private feeds hold tokens), source names and mute words.
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
    cliProc.command = Model.bounded([root.omaboxBin, "--args-on-stdin"], Model.CLI_OUTPUT_BYTES, Model.CLI_SECONDS)
    cliProc.stdinArgs = JSON.stringify(job.args) + "\n"
    cliProc.stdinEnabled = true
    cliProc.running = true
  }

  function loadDelivery() {
    runCli(["delivery", "--json"], function(code, text) {
      var result = null
      // The JSON is the last line; a state recovery prints its notice to stderr first, merged in here.
      try { result = JSON.parse(String(text).trim().split("\n").pop()) } catch (e) {}
      if (code !== 0 || !result || !result.time) return
      if (!deliveryApply.running) root.deliveryTime = result.time
      root.weeklyDay = result.weekly_day || "mon"
      if (result.rows && !rowsApply.running) {
        root.feedRows = result.rows.feed || 0
        root.notificationRows = result.rows.notifications || 0
      }
      root.deliveryStatus(result)
    })
  }

  function deliveryStatus(result) {
    root.fetching = result.fetching === true
    root.cliRecoveredFile = String(result.recovered || "")
    root.deliveryKnown = true
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
      if (code === 0) note(Model.fill(Tr.t("sources.weeklyDaySaved"), [Model.weekdayName(day, Tr)]))
      else {
        root.messageError = true
        root.message = Model.fill(Tr.t("sources.weeklyDayNotSaved"), [text])
        loadDelivery()
      }
    })
  }

  // Rows shown now, counting Fit as the rows that fit (0 while not measured yet).
  function shownRows(kind) {
    var list = kind === "feed" ? feedList : notificationList
    var current = kind === "feed" ? root.feedRows : root.notificationRows
    return current <= 0 ? list.fitRows : list.maxRows > 0 ? Math.min(current, list.maxRows) : current
  }

  // 1 to 10 rows, or fewer when the screen holds fewer; the rows Fit shows turn back into Fit. Saved once the stepping
  // stops.
  function stepRows(kind, delta) {
    var list = kind === "feed" ? feedList : notificationList
    var current = kind === "feed" ? root.feedRows : root.notificationRows
    var top = list.maxRows > 0 ? list.maxRows : 10
    var shown = shownRows(kind)
    var next = shown > 0 ? shown + delta : delta < 0 ? Math.min(10, list.count - 1) : 0
    if (delta < 0) next = Math.min(next, top)
    if (next < 1 || next > top) return
    if (next === list.fitRows) next = 0
    if (next === current) return
    if (kind === "feed") root.feedRows = next
    else root.notificationRows = next
    rowsApply.restart()
  }

  function saveRows() {
    runCli(["rows", "--feed", String(root.feedRows), "--notifications", String(root.notificationRows), "--json"],
      function(code, text) {
        if (code === 0) return
        root.messageError = true
        root.message = Model.fill(Tr.t("sources.rowsNotSaved"), [text])
        loadDelivery()
      })
  }

  function saveDelivery() {
    runCli(["delivery", root.deliveryTime, "--json"], function(code, text) {
      var result = null
      try { result = JSON.parse(text) } catch (e) {}
      if (code !== 0 || !result) {
        root.messageError = true
        root.message = Model.fill(Tr.t("sources.deliveryNotSaved"), [text])
        loadDelivery()
      } else {
        var next = new Date(result.next_at || "")
        note(Model.fill(Tr.t("sources.nextDelivery"),
          [isNaN(next.getTime()) ? result.next || result.time : next.toLocaleString(Tr.locale, Tr.t("time.weekdayTime"))]))
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
      root.sourcesLoaded = true
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
    runCli(["discover", "--json", "--", url], function(code, text) {
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
        nameField.text = Model.spliceField("", 0, 0, found.title, nameField.maxChars).text
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
      root.message = code === 0 ? Tr.t("xToken.removed") : text
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
      note(Tr.t("xToken.saved"))
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
    runCli(["add", "--name=" + name, "--", root.discovered.url], afterSourceChange)
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
    runCli(["rename", "--", source.name, name], afterSourceChange)
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
        runCli(["unmute", "--", source.name, picked], afterMuteChange)
        return
      }
      // The old rule goes only once the new one was accepted, so a refused regex loses nothing.
      runCli(["mute", "--", source.name, rule], function(code, text) {
        if (code !== 0) afterMuteChange(code, text)
        else runCli(["unmute", "--", source.name, picked], function(code2, text2) { afterMuteChange(code2, text + "\n" + text2) })
      })
      return
    }
    if (rule === "") cancelTyping()
    else if (rules.indexOf(rule) >= 0) note(Model.fill(Tr.t("mute.already"), [rule]))
    else runCli(["mute", "--", source.name, rule], afterMuteChange)
  }

  function removeMute(rule) {
    if (!currentSource) return
    root.mutePick = -1
    muteField.text = ""
    runCli(["unmute", "--", currentSource.name, rule], afterMuteChange)
  }

  function toggleReposts() {
    var source = currentSource
    if (!source || !source.x_hidden) return
    runCli([source.x_hidden.reposts ? "unmute" : "mute", "--reposts", "--", source.name], afterMuteChange)
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
    if (currentSource && cadence !== currentSource.cadence) runCli(["cadence", "--", currentSource.name, cadence], afterSourceChange)
  }

  function togglePause() {
    if (!currentSource) return
    runCli(["cadence", "--", currentSource.name, currentSource.cadence === "paused" ? "daily" : "paused"], afterSourceChange)
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
    if (yes && source) runCli(["remove", "--", source.name], afterSourceChange)
  }

  function cancelTyping() {
    root.mode = "list"
    root.message = ""
    focusCatcher()
  }

  function handleText(t) {
    // The welcome card is modal: only its own keys work until it is dismissed. It tells about ?, which closes it,
    // since the key hints would sit under its blur.
    if (root.welcoming) {
      if (t === "n") dismissWelcome("add")
      else if (t === "?") {
        dismissWelcome("")
        if (!root.hintsVisible) toggleHints()
      }
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
    if (t !== "o") root.pendingAction = ""
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

  // Off the CLI queue: a read-only check that must not wait behind, or hold up, the user's own changes.
  Process {
    id: deliveryProbe
    command: Model.bounded([root.omaboxBin, "delivery", "--json"], Model.SMALL_OUTPUT_BYTES, 30)
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var output = Model.splitCliOutput(text, Tr)
        var result = null
        // the JSON is the last line; a state recovery prints its notice first
        if (output.code === 0) try { result = JSON.parse(output.text.split("\n").pop()) } catch (e) {}
        if (result) root.deliveryStatus(result)
      }
    }
  }

  Timer {
    interval: root.fetching ? 3000 : 15000
    running: root.opened
    repeat: true
    onTriggered: if (!deliveryProbe.running) deliveryProbe.running = true
  }

  Timer {
    id: deliveryApply
    interval: 900
    onTriggered: root.saveDelivery()
  }

  Timer {
    id: rowsApply
    interval: 900
    onTriggered: root.saveRows()
  }

  // J/K through posts restarts it, so only a post that stays open fetches its replies or article.
  Timer {
    id: repliesDelay
    interval: 1500
    onTriggered: {
      root.autoFetchReplies()
      root.autoFetchArticle()
    }
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
    property string stdinArgs: ""
    onStarted: {
      write(stdinArgs)
      stdinArgs = ""
      stdinEnabled = false
      root.close()
    }
    onExited: function(exitCode) {
      root.controller.show()
      if (exitCode !== 0) root.note(Tr.t("reader.noViewer"))
    }
  }

  // The panel stays until `omabox play` prints "opened" (the player's window is up), so the half second X takes to
  // start a file shows on the play badge instead of an empty screen.
  Process {
    id: videoPlayer
    property bool shown: false
    property bool noPlayer: false
    property string stdinArgs: ""
    onStarted: {
      shown = false
      noPlayer = false
      write(stdinArgs)
      stdinArgs = ""
      stdinEnabled = false
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
      else root.note(videoPlayer.noPlayer ? Tr.t("reader.noPlayer") : Tr.t("reader.videoFailed"))
    }
  }

  Process {
    id: copyProc
    property string done: ""
    property string text: ""
    property bool plain: false
    environment: ({ OMABOX_COPY: plain ? "plain" : "sensitive" })
    // wl-copy before 2.3 rejects --sensitive: only then is the copy retried without it.
    command: ["bash", "-c", "command -v wl-copy >/dev/null || exit 127; text=$(cat; printf x); text=${text%x}; t='text/plain;charset=utf-8'; if [ \"$OMABOX_COPY\" != plain ]; then printf %s \"$text\" | wl-copy --sensitive --type \"$t\" >/dev/null 2>&1 && exit 0; s=$?; wl-copy --help </dev/null 2>&1 | grep -q -- --sensitive && exit $s; fi; printf %s \"$text\" | wl-copy --type \"$t\" >/dev/null 2>&1"]
    // Turning stdin off closes it, the EOF the copy waits for.
    onStarted: {
      write(text)
      text = ""
      stdinEnabled = false
    }
    onExited: function(code) {
      if (code === 0) {
        root.note(done)
        return
      }
      root.messageError = true
      root.message = code === 127 ? Tr.t("common.noWlCopy") : Tr.t("common.wlCopyFailed")
    }
  }

  Process {
    id: cliProc
    property string stdinArgs: ""
    // Turning stdin off closes it after the one line.
    onStarted: {
      write(stdinArgs)
      stdinArgs = ""
      stdinEnabled = false
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var result = Model.splitCliOutput(text, Tr)
        var done = root.cliDone
        root.cliDone = null
        if (done) done(result.code, result.text)
        root.runNextCli()
      }
    }
  }

  Process {
    id: tokenProc
    command: Model.bounded([root.omaboxBin, "x-token", "--set"], Model.SMALL_OUTPUT_BYTES, 60)
    stdinEnabled: true
    onStarted: {
      write(root.tokenToSend + "\n")
      root.tokenToSend = ""
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var result = Model.splitCliOutput(text, Tr)
        root.tokenSaved(result.code, result.text)
      }
    }
  }

  Process {
    id: repliesProc
    property string stdinArgs: ""
    onStarted: {
      write(stdinArgs)
      stdinArgs = ""
      stdinEnabled = false
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var result = Model.splitCliOutput(text, Tr)
        root.repliesFetched(result.code, result.text)
      }
    }
  }

  Process {
    id: historyProc
    // Other apps write these files: the CLI reads each one capped (NOTE_MAX_BYTES), and its whole answer is capped here.
    command: Model.bounded([root.omaboxBin, "notifications"], 8 * 1024 * 1024, 60)
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var result = Model.splitCliOutput(text, Tr)
        if (result.code === 0) root.notifications = Model.parseHistory(result.text)
        root.notificationsLoaded = true
        if (root.pendingRead >= 0 && root.view === "notifications") root.openReader(root.pendingRead)
        root.pendingRead = -1
      }
    }
  }

  // Omarchy's file, so a watcher only (preload: false never reads): dndReader reads it capped and time-limited.
  FileView {
    path: root.notificationSettingsPath
    preload: false
    watchChanges: true
    printErrors: false
    onFileChanged: root.readDnd()
    Component.onCompleted: root.readDnd()
  }

  property bool dndStale: false

  function readDnd() {
    if (dndReader.running) dndStale = true
    else dndReader.running = true
  }

  Process {
    id: dndReader
    command: Model.bounded(["head", "-c", String(Model.SMALL_OUTPUT_BYTES + 1), "--", root.notificationSettingsPath],
                           Model.SMALL_OUTPUT_BYTES, 5)
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var result = Model.splitCliOutput(text, Tr)
        if (result.code === 0) try { root.dnd = JSON.parse(result.text).dnd === true } catch (e) {}
      }
    }
    onExited: if (root.dndStale) {
      root.dndStale = false
      Qt.callLater(root.readDnd)
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
              text: Tr.t("tabs.feed")
              bordered: true
              selected: root.view === "feed"
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.showView("feed")
            }

            Button {
              text: Tr.t("tabs.notifications")
              bordered: true
              selected: root.view === "notifications"
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.showView("notifications")
            }
          }

          Text {
            id: headerStatus
            readonly property bool failed: root.view === "feed" && root.hostWidget !== null && root.hostWidget.tickProblem !== ""
            anchors.left: tabRow.right
            anchors.leftMargin: Style.space(8)
            anchors.right: toolRow.left
            anchors.rightMargin: Style.space(6)
            anchors.verticalCenter: parent.verticalCenter
            horizontalAlignment: Text.AlignRight
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            text: root.view === "feed"
              ? [Model.deliveryNotice(root.feedState, root.now, hostWidget ? hostWidget.tickProblem : "", Tr).split("  ·  ").join("\n"),
                 root.errorSources.length > 0 ? Model.fill(Tr.t("feed.failedSources"), [root.errorSources.join(Tr.t("common.listSeparator"))]) : ""]
                .filter(function(part) { return part !== "" }).join("\n")
              : root.view === "sources" && root.sourcesLoaded
                ? Tr.tn("sources.count", root.sources.length).arg(Tr.formatNumber(root.sources.length))
              : ""
            color: failed ? Commons.Color.urgent : root.faint
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
          }

          Row {
            id: toolRow
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            PanelActionButton {
              visible: root.view !== "sources"
              iconText: "󰍉"
              tooltipText: Tr.t("actions.search")
              foreground: root.query !== "" ? Commons.Color.accent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.startSearch()
            }

            PanelActionButton {
              visible: root.view !== "sources"
              iconText: "󰈲"
              tooltipText: root.filter !== ""
                ? Model.fill(Tr.t("actions.nextFilter"), [(Model.filterLabel(root.view === "feed" ? Model.nextFilter(root.filter, root.allItems)
                  : Model.nextNoteFilter(root.filter, root.notifications), Tr) || Tr.t("actions.filterAll")).toLowerCase()])
                : (root.view === "feed" ? Tr.t("actions.filterBySource") : Tr.t("actions.filterByApp"))
              foreground: root.filter !== "" ? Commons.Color.accent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.cycleFilter()
            }

            PanelActionButton {
              visible: root.view !== "sources"
              iconText: root.dnd ? "󰂛" : "󰂚"
              tooltipText: root.dnd ? Tr.t("actions.dndOn") : Tr.t("actions.dndOff")
              foreground: root.dnd ? Commons.Color.accent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.toggleDnd()
            }

            PanelActionButton {
              visible: root.view !== "sources"
              enabled: root.view === "feed" ? Model.clearableIds(root.items).length > 0 : root.notifications.length > 0
              iconText: "󰎟"
              tooltipText: root.view === "feed" ? Tr.t("actions.clearRead") : Tr.t("actions.clearHistory")
              foreground: root.mode === "confirm-clear" ? Commons.Color.urgent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.mode === "confirm-clear" ? root.confirmClear(false) : root.askClear()
            }

            PanelActionButton {
              visible: root.view === "sources"
              iconText: "󰐕"
              tooltipText: Tr.t("actions.newSource")
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.startAdd()
            }

            PanelActionButton {
              iconText: "󰌌"
              tooltipText: root.hintsVisible ? Tr.t("actions.hideKeys") : Tr.t("actions.showKeys")
              foreground: root.hintsVisible ? Commons.Color.accent : root.fg
              fontFamily: root.fontFamily
              onClicked: root.toggleHints()
            }

            PanelActionButton {
              iconText: "󰒓"
              tooltipText: root.view === "sources" ? Tr.t("actions.backToFeed") : Tr.t("actions.sources")
              foreground: root.view === "sources" ? Commons.Color.accent : root.fg
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
            text: "󰈲  " + Model.filterLabel(root.filter, Tr)
            color: Commons.Color.accent
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
            color: Commons.Color.accent
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          InputField {
            id: searchField
            visible: root.mode === "search"
            width: parent.width - (root.filter !== "" ? Style.space(140) : 0)
            placeholderText: root.view === "feed" ? Tr.t("feed.searchPlaceholder") : Tr.t("notifications.searchPlaceholder")
            foreground: root.fg
            font.family: root.fontFamily
            onTextChanged: if (root.mode === "search") { root.query = text; root.cursor = 0 }
            Keys.onPressed: function(event) {
              if (root.picking && (event.key === Qt.Key_Up || event.key === Qt.Key_Down)) {
                root.moveCursor(event.key === Qt.Key_Up ? -1 : 1)
                event.accepted = true
              } else if (event.key === Qt.Key_Escape) {
                var picked = root.picking
                root.endSearch(false)
                if (picked) root.close()
                event.accepted = true
              } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                if (root.picking) root.pickCurrent()
                else root.endSearch(true)
                event.accepted = true
              }
            }
          }

          PanelActionButton {
            visible: root.mode !== "search"
            anchors.verticalCenter: parent.verticalCenter
            iconText: "󰅖"
            tooltipText: Tr.t("actions.clearSearch")
            foreground: root.fg
            fontFamily: root.fontFamily
            onClicked: root.clearFilters()
          }
        }

        // One fixed-height slot for the unread count and the mark-read choices, gone once nothing is unread.
        // What the choices cover is in the status line.
        Item {
          id: unreadSlot
          visible: root.view === "feed" && !root.reading && root.allItems.length > 0
                   && (Model.unreadCount(root.items) > 0 || root.catchupOpen)
          width: parent.width
          height: Math.max(markReadButton.implicitHeight, catchupPicker.implicitHeight)

          Row {
            id: unreadRow
            visible: !root.catchupOpen
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(10)

            readonly property int unread: Model.unreadCount(root.items)

            Text {
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: Tr.tn("feed.unread", unreadRow.unread).arg(Tr.formatNumber(unreadRow.unread))
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1
              font.bold: true
            }

            Button {
              id: markReadButton
              visible: unreadRow.unread > 0
              anchors.verticalCenter: parent.verticalCenter
              text: Tr.t("feed.markRead")
              tooltipText: Tr.t("actions.markRead")
              bordered: true
              foreground: root.fg
              fontFamily: root.fontFamily
              fontSize: Style.font.caption
              onClicked: root.openCatchup()
            }
          }

          ChoicePicker {
            id: catchupPicker
            visible: root.catchupOpen
            width: parent.width
            anchors.verticalCenter: parent.verticalCenter
            choices: root.catchupOpen ? Model.catchupChoices(root.items, root.now, Tr) : []
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
          maxHeight: root.bodyMaxHeight - reader.y - root.tailHeight
          panel: root
          item: root.readingItem
        }

        Item {
          visible: root.view === "sources"
          width: parent.width
          height: visible ? deliveryControls.height : 0

          Column {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - deliveryControls.width - Style.space(10)
            spacing: Style.space(2)

            Text {
              width: parent.width
              textFormat: Text.PlainText
              elide: Text.ElideRight
              text: Tr.t("sources.deliveryHeading")
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1.2
              font.bold: true
            }

            Text {
              width: parent.width
              textFormat: Text.PlainText
              elide: Text.ElideRight
              text: Tr.t("sources.deliveryNote")
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
              tooltipText: Tr.t("sources.earlier")
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.stepDelivery(-30)
            }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: root.deliveryTime || "--:--"
              color: root.deliveryTime ? root.fg : root.faint
              font.family: root.fontFamily
              font.pixelSize: Style.font.subtitle
              font.bold: true
            }

            PanelActionButton {
              anchors.verticalCenter: parent.verticalCenter
              iconText: "󰐕"
              tooltipText: Tr.t("sources.later")
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.stepDelivery(30)
            }
          }
        }

        Item {
          visible: root.view === "sources"
          width: parent.width
          height: visible ? weekdayChips.height : 0

          Text {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - weekdayChips.width - Style.space(10)
            textFormat: Text.PlainText
            elide: Text.ElideRight
            text: Tr.t("sources.weeklyOn")
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
            options: Model.weekdayOptions(Tr)
            value: root.weeklyDay
            foreground: root.fg
            background: "transparent"
            fontFamily: root.fontFamily
            fontSize: Style.font.caption
            onChanged: function(value) { root.setWeeklyDay(value) }
          }
        }

        Repeater {
          model: root.view === "sources" ? ["feed", "notifications"] : []

          Item {
            id: rowsSetting
            required property string modelData
            readonly property int rows: root.shownRows(modelData)
            width: parent.width
            height: rowsControls.height

            Text {
              anchors.verticalCenter: parent.verticalCenter
              width: parent.width - rowsControls.width - Style.space(10)
              textFormat: Text.PlainText
              elide: Text.ElideRight
              text: Tr.t(rowsSetting.modelData === "feed" ? "sources.feedRows" : "sources.notificationRows")
              color: root.faint
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }

            Row {
              id: rowsControls
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(6)

              PanelActionButton {
                anchors.verticalCenter: parent.verticalCenter
                iconText: "󰍴"
                tooltipText: Tr.t("sources.fewerRows")
                foreground: root.fg
                fontFamily: root.fontFamily
                onClicked: root.stepRows(rowsSetting.modelData, -1)
              }

              Text {
                anchors.verticalCenter: parent.verticalCenter
                width: Math.max(implicitWidth, Math.ceil(fitWidth.advanceWidth))
                horizontalAlignment: Text.AlignHCenter
                textFormat: Text.PlainText
                text: rowsSetting.rows > 0 ? Tr.formatNumber(rowsSetting.rows) : Tr.t("sources.rowsFit")
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true

                TextMetrics {
                  id: fitWidth
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                  text: Tr.t("sources.rowsFit")
                }
              }

              PanelActionButton {
                anchors.verticalCenter: parent.verticalCenter
                iconText: "󰐕"
                tooltipText: Tr.t("sources.moreRows")
                foreground: root.fg
                fontFamily: root.fontFamily
                onClicked: root.stepRows(rowsSetting.modelData, 1)
              }
            }
          }
        }

        PanelSeparator {
          visible: root.view === "sources"
          width: parent.width
          foreground: root.fg
        }

        Text {
          visible: root.view === "sources"
          textFormat: Text.PlainText
          text: Tr.t("sources.heading")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.letterSpacing: 1.2
          font.bold: true
        }

        Column {
          id: addForm
          // The URL and NAME labels share one column, as wide as the longer one in this language.
          readonly property real labelWidth: Math.max(Style.space(48), urlLabel.implicitWidth, nameFieldLabel.implicitWidth)
          visible: root.view === "sources" && (root.mode === "add-url" || root.mode === "add-name")
          width: parent.width
          spacing: Style.space(6)

          Row {
            width: parent.width
            spacing: Style.space(10)

            Text {
              id: urlLabel
              width: addForm.labelWidth
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: Tr.t("sources.urlLabel")
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1
              font.bold: true
            }

            InputField {
              id: urlField
              objectName: "urlField"
              width: parent.width - addForm.labelWidth - Style.space(10)
              enabled: root.mode === "add-url" && !root.busy
              placeholderText: Tr.t("sources.urlPlaceholder")
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
            leftPadding: addForm.labelWidth + Style.space(10)
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
            text: !root.discovered ? ""
              : root.discovered.latest ? Model.fill(Tr.t("sources.foundLatest"), [Model.clip(root.discovered.title, Model.NAME_CHARS),
                  Model.clip(root.discovered.latest.title, Model.NAME_CHARS),
                  Model.relativeTime(root.discovered.latest.published, root.now, Tr)])
              : Model.fill(Tr.t("sources.foundEmpty"), [Model.clip(root.discovered.title, Model.NAME_CHARS)])
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }

          Row {
            visible: root.mode === "add-name"
            width: parent.width
            spacing: Style.space(10)

            Text {
              id: nameFieldLabel
              width: addForm.labelWidth
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: Tr.t("sources.nameLabel")
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1
              font.bold: true
            }

            InputField {
              id: nameField
              width: parent.width - addForm.labelWidth - Style.space(10)
              maxChars: Model.NAME_CHARS
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
            text: Model.fill(Tr.t("mute.heading"), [root.currentSource ? root.currentSource.name.toUpperCase() : ""])
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          InputField {
            id: muteField
            width: parent.width
            placeholderText: root.mutePick >= 0 ? Tr.t("mute.removePlaceholder")
              : root.muteRules.length > 0 ? Tr.t("mute.pickPlaceholder") : Tr.t("mute.placeholder")
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
                color: ruleMouse.containsMouse ? Style.hoverFillFor(root.fg, Commons.Color.accent) : "transparent"
                border.width: 1
                border.color: picked ? Commons.Color.accent : Util.alpha(root.fg, 0.25)

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
                    color: ruleChip.picked ? Commons.Color.accent : root.fg
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                  }

                  Text {
                    anchors.verticalCenter: parent.verticalCenter
                    textFormat: Text.PlainText
                    text: "󰅖"
                    color: removeRuleMouse.containsMouse ? Commons.Color.urgent : root.faint
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
                      text: Tr.t("mute.removeRule")
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
              text: parent.repostsHidden ? Tr.t("mute.repostsHidden") : Tr.t("mute.repostsShown")
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
            }

            Button {
              text: parent.repostsHidden ? Tr.t("mute.showReposts") : Tr.t("mute.hideReposts")
              bordered: true
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.toggleReposts()
            }
          }
        }

        Text {
          visible: root.rows.length === 0 && !root.reading && (root.view === "feed" ? !root.hostWidget || root.hostWidget.stateLoaded
            : root.view === "notifications" ? root.notificationsLoaded : root.sourcesLoaded)
          width: parent.width
          topPadding: Style.space(24)
          bottomPadding: Style.space(24)
          horizontalAlignment: Text.AlignHCenter
          textFormat: Text.PlainText
          text: root.view === "notifications" ? Tr.t("notifications.empty")
            : root.view === "sources" ? Tr.t("sources.empty") : Tr.t("feed.empty")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        // One ListView per view: swapping model and delegate on a shared one feeds rows to the wrong delegate for a frame.
        ListView {
          id: feedList
          visible: root.view === "feed" && !root.reading && count > 0
          // Fit, and caps past the screen, stop at the last whole row that fits.
          readonly property int rowCap: root.feedRows <= 0 ? fitRows : maxRows > 0 ? Math.min(root.feedRows, maxRows) : root.feedRows
          property real capHeight: 0
          property int measuredFor: 0
          property int fitRows: 0
          property int maxRows: 0
          property real shownRoom: 0
          property bool unreadAbove: false
          // Height of the first rowCap rows. Rows scrolled out of the cache cannot be measured; the last height stays
          // then, so the list does not resize while scrolling.
          function measureCap() {
            root.measureRows(feedList)
            var first = itemAtIndex(0), last = itemAtIndex(rowCap - 1)
            if (rowCap <= 0 || count <= rowCap) capHeight = 0
            else if (first && last) capHeight = last.y + last.height - first.y
            else if (measuredFor !== rowCap) capHeight = 0
            else return
            measuredFor = rowCap
          }
          onRowCapChanged: Qt.callLater(measureCap)
          onCountChanged: Qt.callLater(measureCap)
          onContentHeightChanged: Qt.callLater(measureCap)
          onHeightChanged: Qt.callLater(measureCap)
          onVisibleChanged: Qt.callLater(measureCap)
          // Keeps the capped rows built while the list is hidden, so it comes back at its cap height, not Fit's,
          // and measureRows can count them from the Sources view.
          cacheBuffer: Math.ceil(Math.min(root.bodyMaxHeight, Style.space(1400)))
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
          // Fit, and caps past the screen, stop at the last whole row that fits.
          readonly property int rowCap: root.notificationRows <= 0 ? fitRows : maxRows > 0 ? Math.min(root.notificationRows, maxRows) : root.notificationRows
          property real capHeight: 0
          property int measuredFor: 0
          property int fitRows: 0
          property int maxRows: 0
          property real shownRoom: 0
          function measureCap() {
            root.measureRows(notificationList)
            var first = itemAtIndex(0), last = itemAtIndex(rowCap - 1)
            if (rowCap <= 0 || count <= rowCap) capHeight = 0
            else if (first && last) capHeight = last.y + last.height - first.y
            else if (measuredFor !== rowCap) capHeight = 0
            else return
            measuredFor = rowCap
          }
          onRowCapChanged: Qt.callLater(measureCap)
          onCountChanged: Qt.callLater(measureCap)
          onContentHeightChanged: Qt.callLater(measureCap)
          onHeightChanged: Qt.callLater(measureCap)
          onVisibleChanged: Qt.callLater(measureCap)
          // Keeps the capped rows built while the list is hidden, so it comes back at its cap height, not Fit's,
          // and measureRows can count them from the Sources view.
          cacheBuffer: Math.ceil(Math.min(root.bodyMaxHeight, Style.space(1400)))
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
          readonly property int rowCap: 0
          readonly property real capHeight: 0
          width: parent.width
          height: visible ? root.listHeight(sourceList) : 0
          clip: true
          spacing: Style.space(2)
          boundsBehavior: Flickable.StopAtBounds
          model: root.sources
          delegate: sourceRow
        }

        Text {
          id: statusLine
          visible: root.confirming || root.catchupOpen
          width: parent.width
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          text: root.mode === "confirm" && root.currentSource ? Model.fill(Tr.t("sources.removeQuestion"), [root.currentSource.name])
            : root.mode === "confirm-clear" ? root.clearQuestion
            : root.catchupOpen ? [Tr.t("feed.markReadHeading"), Model.filterLabel(root.filter, Tr), root.query !== "" ? "/ " + root.query : ""]
              .filter(function(part) { return part !== "" }).join("  ·  ")
            : ""
          color: root.fg
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.letterSpacing: 1
        }

        Row {
          id: confirmRow
          visible: (root.view === "sources" && root.mode === "confirm") || root.mode === "confirm-clear"
          spacing: Style.space(6)

          Button {
            text: root.mode === "confirm-clear" ? Tr.t("common.clear") : Tr.t("common.remove")
            bordered: true
            foreground: Commons.Color.urgent
            fontFamily: root.fontFamily
            onClicked: root.mode === "confirm-clear" ? root.confirmClear(true) : root.confirmRemove(true)
          }

          Button {
            text: Tr.t("common.keep")
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
            model: Model.hintEntries(root.view, root.mode, root.reading, Tr)

            Row {
              required property var modelData
              spacing: Style.space(5)

              Text {
                textFormat: Text.PlainText
                text: modelData.key
                color: Commons.Color.accent
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

      // Messages ("Copied …", CLI answers, fetching) cover the bottom edge for a while instead of taking a line, so
      // the list never moves and the panel has no empty band below it.
      Rectangle {
        id: messageStrip
        readonly property string text: statusLine.visible ? ""
          : root.busy ? Tr.t("sources.looking")
          : root.message !== "" ? Model.clip(root.message, Model.MESSAGE_CHARS)
          : root.fetching ? Tr.t("feed.fetching")
          : root.view === "feed" && !headerStatus.failed && root.recoveredFile !== ""
            ? Model.fill(Tr.t("feed.recovered"), [root.stateDirLabel + "/" + root.recoveredFile])
          : ""
        visible: text !== "" && !root.overlayShown
        x: body.x
        width: body.width
        height: messageText.implicitHeight + Style.space(8)
        y: body.y + (hintsFlow.visible ? hintsFlow.y - body.spacing : body.height) - height
        color: Qt.rgba(root.cardColor.r, root.cardColor.g, root.cardColor.b, 1)

        Text {
          id: messageText
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          textFormat: Text.PlainText
          // Wrap, not WordWrap: a notification's command to confirm can be one long word and must show in full
          wrapMode: Text.Wrap
          text: messageStrip.text
          color: root.busy || (root.message === "" && root.fetching) ? root.faint
            : root.message !== "" ? (root.messageError ? Commons.Color.urgent : root.dim)
            : root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.letterSpacing: 1
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
          border.color: Util.alpha(Commons.Color.accent, 0.45)

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
                  text: Tr.t("welcome.title")
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
                  text: Model.fill(Tr.t("welcome.intro"), [root.deliveryTime || "08:00"])
                  color: root.fg
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                }

                Repeater {
                  model: [Tr.t("welcome.sources"), Tr.t("welcome.notifications"), Tr.t("welcome.keys")]

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
                    text: Tr.t("welcome.start")
                    bordered: true
                    foreground: Commons.Color.accent
                    fontFamily: root.fontFamily
                    onClicked: root.dismissWelcome("")
                  }

                  Button {
                    text: Tr.t("welcome.addSource")
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
                text: root.xTokenSaved ? Tr.t("xToken.replaceTitle") : Tr.t("xToken.connectTitle")
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }

              Text {
                width: parent.width
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                text: Tr.t("xToken.warning")
                color: Commons.Color.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                width: parent.width
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                text: Tr.t("xToken.handling")
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Repeater {
                model: [Tr.t("xToken.step1"), Tr.t("xToken.step2"), Tr.t("xToken.step3")]

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
                  id: tokenLabel
                  width: Math.max(Style.space(48), implicitWidth)
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: Tr.t("xToken.label")
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.letterSpacing: 1
                  font.bold: true
                }

                InputField {
                  id: tokenField
                  width: parent.width - tokenLabel.width - Style.space(10)
                  password: true
                  enabled: !tokenProc.running
                  placeholderText: Tr.t("xToken.placeholder")
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
                text: Tr.t("xToken.signOut")
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Button {
                visible: root.xTokenSaved
                text: Tr.t("xToken.remove")
                bordered: true
                foreground: Commons.Color.urgent
                fontFamily: root.fontFamily
                onClicked: root.removeXToken()
              }
            }


            Text {
              visible: root.mode === "x-token" && root.messageError && root.message !== ""
              width: parent.width
              textFormat: Text.PlainText
              wrapMode: Text.WordWrap
              maximumLineCount: 6
              elide: Text.ElideRight
              text: Model.clip(root.message, Model.MESSAGE_CHARS)
              color: Commons.Color.urgent
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
      readonly property color readColor: current ? root.selectedReadText : root.readText
      readonly property color metaColor: item.read ? readColor : dimColor

      width: ListView.view.width
      height: rowColumn.implicitHeight + Style.space(16) + (rowSnooze.visible ? rowSnooze.height + Style.space(8) : 0)
      radius: Style.cornerRadius
      color: current
        ? Style.selectedFillFor(root.fg, Commons.Color.accent)
        : (rowHover.hovered ? Style.hoverFillFor(root.fg, Commons.Color.accent) : "transparent")

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
        width: parent.width - Style.space(20)
        y: rowColumn.y + rowColumn.implicitHeight + Style.space(8)
        choices: Model.snoozeChoices(Tr)
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
          tooltipText: row.item.later === true ? Tr.t("actions.unmarkLater") : Tr.t("actions.readLater")
          foreground: row.item.later === true ? Commons.Color.accent : root.fg
          fontFamily: root.fontFamily
          onClicked: root.toggleLaterCurrent(row.item)
        }

        PanelActionButton {
          iconText: "󰒲"
          tooltipText: Tr.t("actions.snooze")
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: root.openSnooze(row.item)
        }

        PanelActionButton {
          visible: row.tag === "newer"
          iconText: "󰚰"
          tooltipText: Tr.t("actions.updateOmarchy")
          foreground: Commons.Color.accent
          fontFamily: root.fontFamily
          onClicked: root.runUpdate(row.item)
        }

        PanelActionButton {
          visible: !!row.item.link
          iconText: "󰏌"
          tooltipText: Tr.t("actions.openInBrowser")
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: root.openLink(row.index)
        }

        PanelActionButton {
          visible: !!row.item.link
          iconText: "󰆏"
          tooltipText: Tr.t("actions.copyLink")
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

        // The source name and the repost's author give way (elide) so the time and tags stay clear of the hover buttons.
        Row {
          id: metaRow
          spacing: Style.space(8)
          readonly property real room: rowColumn.width - rowActions.width - Style.space(6)
          readonly property real fixedWidth: {
            var width = 0, shown = 0
            for (var i = 0; i < children.length; i++) {
              if (!children[i].visible) continue
              shown++
              if (children[i] !== sourceLabel && children[i] !== repostLabel) width += children[i].width
            }
            return width + spacing * Math.max(0, shown - 1)
          }

          Rectangle {
            visible: row.item !== null && !row.item.read
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(6)
            height: width
            radius: width / 2
            color: Commons.Color.accent
          }

          SourceIcon {
            anchors.verticalCenter: parent.verticalCenter
            icon: row.item && root.feedState.icons ? (root.feedState.icons[row.item.source] || {}) : ({})
            color: row.metaColor
            fontFamily: root.fontFamily
            size: Style.font.body
          }

          Text {
            id: sourceLabel
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, Math.max(Style.space(40),
              metaRow.room - metaRow.fixedWidth - (repostLabel.visible ? repostLabel.width : 0)))
            textFormat: Text.PlainText
            elide: Text.ElideRight
            text: row.item ? row.item.source.toUpperCase() : ""
            color: row.metaColor
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          Text {
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: row.item ? ("·  " + Model.relativeTime(row.item.published, root.now, Tr)).toUpperCase() : ""
            color: row.metaColor
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          Text {
            id: repostLabel
            visible: !!row.item.repost
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, Math.max(Style.space(60), (metaRow.room - metaRow.fixedWidth) / 2))
            elide: Text.ElideRight
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
            text: "·  " + (row.tag === "newer" ? Tr.t("feed.newerTag") : Tr.t("feed.installedTag"))
            color: row.tag === "newer" ? Commons.Color.accent : row.metaColor
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          Text {
            visible: row.item.later === true
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: "·  󰃀 " + Tr.t("feed.laterTag")
            color: Commons.Color.accent
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
          color: row.item.read ? row.readColor : root.fg
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
          color: row.item.read ? row.readColor : row.dimColor
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
        ? Style.selectedFillFor(root.fg, Commons.Color.accent)
        : (noteHover.hovered ? Style.hoverFillFor(root.fg, Commons.Color.accent) : "transparent")

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
        id: noteActions
        z: 1
        visible: noteHover.hovered
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: Style.space(4)
        spacing: Style.space(2)

        PanelActionButton {
          iconText: "󰆏"
          tooltipText: Tr.t("actions.copyMessage")
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: root.copyNotification(note.index)
        }

        PanelActionButton {
          iconText: "󰅖"
          tooltipText: Tr.t("actions.remove")
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
          width: Math.min(implicitWidth, parent.width - noteActions.width - Style.space(6))
          textFormat: Text.PlainText
          elide: Text.ElideRight
          text: [Model.appLabel(note.modelData), Model.relativeTime(new Date(note.modelData.timestamp || 0).toISOString(), root.now, Tr)]
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
        ? Style.selectedFillFor(root.fg, Commons.Color.accent)
        : (sourceHover.hovered ? Style.hoverFillFor(root.fg, Commons.Color.accent) : "transparent")

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
          tooltipText: Tr.t("actions.rename")
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: { root.selectSource(source.index); root.startRename() }
        }

        PanelActionButton {
          iconText: "󰈉"
          tooltipText: Tr.t("actions.muteRules")
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: { root.selectSource(source.index); root.startMute() }
        }

        PanelActionButton {
          iconText: source.modelData.cadence === "paused" ? "󰐊" : "󰏤"
          tooltipText: source.modelData.cadence === "paused" ? Tr.t("actions.resume") : Tr.t("actions.pause")
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: { root.selectSource(source.index); root.togglePause() }
        }

        PanelActionButton {
          iconText: "󰆴"
          tooltipText: Tr.t("actions.remove")
          foreground: Commons.Color.urgent
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

          InputField {
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
            options: [{ value: "daily", label: Tr.t("sources.daily") }, { value: "weekly", label: Tr.t("sources.weekly") },
              { value: "paused", label: Tr.t("sources.paused") }]
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
          text: Model.sourceStatus(source.modelData, root.now, Tr) + "  ·  "
            + Tr.tn("sources.postCount", source.modelData.items).arg(Tr.formatNumber(source.modelData.items))
            + Model.muteSummary(source.modelData, Tr)
          color: source.modelData.error ? Commons.Color.urgent : source.faintColor
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }

        Text {
          visible: text !== ""
          width: parent.width - (sourceActions.visible ? sourceActions.width + Style.space(4) : 0)
          textFormat: Text.PlainText
          elide: Text.ElideRight
          text: Model.staleLabel(source.modelData.stale, Tr).toUpperCase()
          color: source.modelData.stale && source.modelData.stale.kind === "failing" ? Commons.Color.urgent : source.dimColor
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.letterSpacing: 1
          font.bold: true
        }
      }
    }
  }
}
