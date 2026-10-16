import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "io.github.wienieclaurowy.omabox"

  readonly property string home: Quickshell.env("HOME")
  readonly property string stateHome: Quickshell.env("XDG_STATE_HOME") || (home + "/.local/state")
  readonly property string statePath: stateHome + "/omabox/items.json"
  readonly property string omaboxBin: Model.localPath(Qt.resolvedUrl("bin/omabox"))
  // Omarchy keeps it under $HOME whatever XDG_STATE_HOME says.
  readonly property string historyDir: home + "/.local/state/omarchy/notifications/history"
  // FileView never watches a file whose directory is missing, so the state directory is made before items.json is watched.
  property bool stateDirReady: false
  // Why the last `omabox tick` failed, "" after one that worked; the feed's status line shows it.
  property string tickProblem: ""

  // Every monitor has a copy of this widget. Only the first reads and parses items.json (about 40 ms for 2000 posts)
  // and keeps the overrides; the others show its result. A copy whose owner is gone (null) falls back to its own.
  readonly property var stateOwner: {
    var copies = peers()
    return copies.length > 0 && copies[0] ? copies[0] : root
  }
  readonly property bool ownsState: stateOwner === root || !stateOwner
  property var ownState: Model.parseState("")
  property var ownOverrides: ({})
  property bool ownLoaded: false
  readonly property var feedState: ownsState ? ownState : stateOwner.feedState
  // false until items.json was read (or found missing) once; the feed's empty state waits for it.
  readonly property bool stateLoaded: ownsState ? ownLoaded : stateOwner.stateLoaded
  readonly property var overrides: ownsState ? ownOverrides : stateOwner.overrides
  property date now: new Date()
  readonly property var items: ownsState ? Model.feedItems(ownState, ownOverrides, now) : stateOwner.items
  readonly property int unread: Model.unreadCount(items)

  // Set on every monitor's copy by the IPC handler; whichever copy the shell opens consumes it.
  property string requestedView: ""
  property double requestedAt: 0
  property int requestedRead: -1
  property string requestedPost: ""
  // `omabox pick`'s query for the opening copy's search; null: no search asked for.
  property var requestedSearch: null

  function takeRequestedView() {
    var view = Date.now() - requestedAt < 3000 ? requestedView : ""
    requestedView = ""
    return view
  }

  function takeRequestedRead() {
    var index = Date.now() - requestedAt < 3000 ? requestedRead : -1
    requestedRead = -1
    return index
  }

  function takeRequestedPost() {
    var id = Date.now() - requestedAt < 3000 ? requestedPost : ""
    requestedPost = ""
    return id
  }

  function takeRequestedSearch() {
    var query = Date.now() - requestedAt < 3000 ? requestedSearch : null
    requestedSearch = null
    return query
  }

  function peers() {
    return bar && typeof bar.moduleWidgets === "function" ? bar.moduleWidgets(moduleName) : [root]
  }

  // Sets all four fields: only the opening copy consumes them, so a field left on another monitor's copy
  // would turn fresh again with the next request's requestedAt.
  function requestOpen(copies, view, read, post, search) {
    for (var j = 0; j < copies.length; j++) {
      if (!copies[j]) continue
      copies[j].requestedView = view
      copies[j].requestedRead = read
      copies[j].requestedPost = post
      copies[j].requestedSearch = search === undefined ? null : search
      copies[j].requestedAt = Date.now()
    }
    Quickshell.execDetached(["omarchy-shell", "shell", "summon", moduleName, "{}"])
    return "opened"
  }

  function toggleView(view) {
    var copies = peers()
    for (var i = 0; i < copies.length; i++) {
      var panel = copies[i] && copies[i].panelItem ? copies[i].panelItem() : null
      if (panel && panel.opened) {
        if (panel.view === view) panel.close()
        else panel.showView(view)
        return panel.opened ? "switched" : "closed"
      }
    }
    return requestOpen(copies, view, -1, "")
  }

  function panelItem() { return panelLoader.item }

  function readPost(index, view) {
    var copies = peers()
    for (var i = 0; i < copies.length; i++) {
      var panel = copies[i] && copies[i].panelItem ? copies[i].panelItem() : null
      if (panel && panel.opened) {
        panel.showView(view)
        if (view === "notifications") panel.pendingRead = index
        else panel.openReader(index)
        return "reading"
      }
    }
    return requestOpen(copies, view, index, "")
  }

  // Snoozed posts are left out of items, so opening one by id wakes it first.
  function openPost(id) {
    var stored = false
    for (var s = 0; s < feedState.items.length; s++) if (feedState.items[s].id === id) stored = true
    if (!stored) return "no post " + id
    var copies = peers()
    var shown = false
    for (var k = 0; k < items.length; k++) if (items[k].id === id) shown = true
    if (!shown) {
      for (var c = 0; c < copies.length; c++) if (copies[c]) copies[c].override([id], { snoozed_until: "" })
      runWrite(["unsnooze", id])
    }
    for (var i = 0; i < copies.length; i++) {
      var panel = copies[i] && copies[i].panelItem ? copies[i].panelItem() : null
      if (panel && panel.opened) return panel.openPostById(id) ? "reading" : "no post " + id
    }
    return requestOpen(copies, "feed", -1, id)
  }

  function pickPost(query) {
    var copies = peers()
    for (var i = 0; i < copies.length; i++) {
      var panel = copies[i] && copies[i].panelItem ? copies[i].panelItem() : null
      if (panel && panel.opened) {
        panel.pickSearch(query)
        return "searching"
      }
    }
    return requestOpen(copies, "feed", -1, "", query)
  }

  function override(ids, fields) {
    if (!ownsState) {
      stateOwner.override(ids, fields)
      return
    }
    var next = {}
    for (var key in overrides) next[key] = overrides[key]
    for (var i = 0; i < ids.length; i++) {
      var merged = {}
      for (var old in next[ids[i]] || {}) merged[old] = next[ids[i]][old]
      for (var field in fields) merged[field] = fields[field]
      next[ids[i]] = merged
    }
    ownOverrides = next
  }

  function markRead(ids) {
    if (!ids || ids.length === 0) return
    override(ids, { read: true })
    runWrite(["read"].concat(ids))
  }

  function snooze(item, until) {
    override([item.id], { snoozed_until: until })
    runWrite(["snooze", item.id, "--until", until])
  }

  function toggleLater(item) {
    var later = !item.later
    override([item.id], { later: later })
    runWrite(["later", item.id, later ? "--on" : "--off"])
  }

  // CLI writes for the posts the user reads, snoozes and saves, one at a time and in order, on the state owner. Their
  // arguments go on stdin (--args-on-stdin): post ids in argv would tell every account what the user reads.
  property var writeQueue: []

  function runWrite(args) {
    if (!ownsState) {
      stateOwner.runWrite(args)
      return
    }
    writeQueue = writeQueue.concat([args])
    nextWrite()
  }

  function nextWrite() {
    if (writeProc.running || writeQueue.length === 0) return
    writeProc.stdinArgs = JSON.stringify(writeQueue[0]) + "\n"
    writeQueue = writeQueue.slice(1)
    writeProc.stdinEnabled = true
    writeProc.running = true
  }

  Process {
    id: writeProc
    property string stdinArgs: ""
    command: Model.bounded([root.omaboxBin, "--args-on-stdin"], Model.SMALL_OUTPUT_BYTES, 120)
    // Turning stdin off closes it after the one line.
    onStarted: {
      write(stdinArgs)
      stdinArgs = ""
      stdinEnabled = false
    }
    stdout: StdioCollector { waitForEnd: true }
    onExited: Qt.callLater(root.nextWrite)
  }

  function markAllRead() {
    var ids = []
    for (var i = 0; i < items.length; i++) if (!items[i].read) ids.push(items[i].id)
    markRead(ids)
  }

  // Bar.findPanelWidget routes `omarchy-shell shell toggle <id>` here; it needs open/close/opened on this root.
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function toggle() { if (panelLoader.item) panelLoader.item.toggle() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    target.bar = root.bar
    target.settings = root.settings
    target.anchorItem = button
    target.hostWidget = root
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  // One target, one handler: each extra registration logs a warning. The first copy owns it; when its monitor goes,
  // peers() changes and the next copy takes over a turn later, after the old owner let go (two at once warn too).
  property bool ipcOwner: false
  readonly property bool firstCopy: scheduler()
  onFirstCopyChanged: {
    if (!firstCopy) ipcOwner = false
    else Qt.callLater(function() { root.ipcOwner = root.scheduler() })
  }
  Component.onCompleted: Qt.callLater(function() { root.ipcOwner = root.scheduler() })

  IpcHandler {
    enabled: root.ipcOwner
    target: "omabox"

    function toggleView(view: string): string {
      if (["feed", "notifications", "sources"].indexOf(view) < 0) return "unknown view: " + view
      return root.toggleView(view)
    }

    // Opens post <index> (0 = newest) in the reader on the focused monitor.
    function read(index: string): string {
      return root.readPost(parseInt(index, 10) || 0, "feed")
    }

    // Opens notification <index> (0 = newest) in the reader.
    function readNotification(index: string): string {
      return root.readPost(parseInt(index, 10) || 0, "notifications")
    }

    // Opens the post with this id in the reader, clearing the filter and search; `omabox pick` calls it.
    function openPost(id: string): string {
      return root.openPost(id)
    }

    // The panel's search with query typed in, picking like a launcher; `omabox pick` calls it.
    function pick(query: string): string {
      return root.pickPost(query)
    }

    // Switches the post open in the reader between its full article (fetched on first use) and its feed version.
    function article(): string {
      var copies = root.peers()
      for (var i = 0; i < copies.length; i++) {
        var panel = copies[i] && copies[i].panelItem ? copies[i].panelItem() : null
        if (panel && panel.opened) return panel.toggleArticle()
      }
      return "closed"
    }

    // Replies under the X post open in the reader: "refresh" fetches them again, anything else reports their state
    // (shown, loading, waiting, failed, unavailable).
    function replies(mode: string): string {
      var copies = root.peers()
      for (var i = 0; i < copies.length; i++) {
        var panel = copies[i] && copies[i].panelItem ? copies[i].panelItem() : null
        if (panel && panel.opened) return mode === "refresh" ? panel.refreshReplies() : panel.repliesState()
      }
      return "closed"
    }
  }

  // Snoozed posts come back when their time passes, without waiting for the file to change.
  Timer {
    interval: 300000
    running: true
    repeat: true
    onTriggered: root.now = new Date()
  }

  // Every monitor has its own copy of this widget; the first one runs the scheduler, so deliveries run once.
  function scheduler() {
    var copies = peers()
    return copies.length === 0 || copies[0] === root
  }

  Process {
    running: true
    command: ["mkdir", "-p", "-m", "700", root.stateHome + "/omabox"]
    onExited: root.stateDirReady = true
  }

  // `omabox tick` delivers or retries when due and prints the seconds until it wants to run again.
  Timer {
    id: tickTimer
    interval: 5000
    running: true
    repeat: true
    onTriggered: {
      interval = 300000
      if (!tickProc.running && root.scheduler()) tickProc.running = true
    }
  }

  // Unbuffered, so the merged output keeps its order: the last line is the seconds, or why the run failed. A
  // delivery fetches every due source in turn, so its deadline is long.
  Process {
    id: tickProc
    command: Model.bounded(["env", "PYTHONUNBUFFERED=1", root.omaboxBin, "tick"], 1024 * 1024, 3600)
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var result = Model.splitCliOutput(text, Tr)
        var lines = result.text.trim().split("\n")
        var last = lines[lines.length - 1]
        if (result.code !== 0) {
          root.tickProblem = result.overflow ? result.text : Model.cliProblem(result.code, last, Tr)
            || Model.fill(Tr.t("bar.tickExited"), [result.code])
          return
        }
        root.tickProblem = ""
        var seconds = parseInt(last, 10)
        if (seconds > 0) {
          tickTimer.interval = Math.min(seconds, 300) * 1000
          tickTimer.restart()
        }
      }
    }
  }

  // Omarchy keeps only its last 10 notifications; each new one is copied to the 7-day archive as it arrives.
  FileView {
    path: root.historyDir
    preload: false
    watchChanges: true
    printErrors: false
    onFileChanged: if (!archiveProc.running && root.scheduler()) archiveProc.running = true
  }

  Process {
    id: archiveProc
    command: [root.omaboxBin, "archive-notifications"]
  }

  // A watcher only (preload: false never reads): items.json comes in through stateReader, capped and time-limited.
  FileView {
    path: root.stateDirReady && root.ownsState ? root.statePath : ""
    preload: false
    watchChanges: true
    printErrors: false
    onFileChanged: root.readState()
  }

  readonly property bool readsState: stateDirReady && ownsState
  onReadsStateChanged: if (readsState) readState()
  property bool stateStale: false

  function readState() {
    if (stateReader.running) stateStale = true
    else stateReader.running = true
  }

  Process {
    id: stateReader
    command: Model.bounded(["head", "-c", String(Model.MAX_STATE_BYTES + 1), "--", root.statePath], Model.MAX_STATE_BYTES, 10)
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var result = Model.splitCliOutput(text, Tr)
        // too large or too slow keeps the posts shown; a missing file is an empty feed
        if (result.code === 0) {
          root.ownState = Model.parseState(result.text)
          root.ownOverrides = ({})
        } else if (!result.overflow && result.code !== 124 && result.code !== 137) {
          root.ownState = Model.parseState("")
        }
        root.ownLoaded = true
      }
    }
    // a change seen while a read ran gets a read of its own
    onExited: if (root.stateStale) {
      root.stateStale = false
      if (root.readsState) Qt.callLater(root.readState)
    }
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰚇"
    tooltipText: root.unread > 0 ? Tr.tn("bar.unread", root.unread).arg(Tr.formatNumber(root.unread)) : "Omabox"
    onPressed: function(b) {
      if (b === Qt.MiddleButton) root.markAllRead()
      else root.toggle()
    }

    Rectangle {
      visible: root.unread > 0
      width: Style.space(6)
      height: width
      radius: width / 2
      color: Commons.Color.accent
      x: button.width / 2 + Style.space(5)
      y: button.height / 2 - Style.space(9)
    }
  }
}
