import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
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

  property var feedState: Model.parseState("")
  property var overrides: ({})
  property date now: new Date()
  readonly property var items: Model.feedItems(feedState, overrides, now)
  readonly property int unread: Model.unreadCount(items)

  // Set on every monitor's copy by the IPC handler; whichever copy the shell opens consumes it.
  property string requestedView: ""
  property double requestedAt: 0
  property int requestedRead: -1
  property string requestedPost: ""

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

  function peers() {
    return bar && typeof bar.moduleWidgets === "function" ? bar.moduleWidgets(moduleName) : [root]
  }

  // Sets all three fields: only the opening copy consumes them, so a field left on another monitor's copy
  // would turn fresh again with the next request's requestedAt.
  function requestOpen(copies, view, read, post) {
    for (var j = 0; j < copies.length; j++) {
      if (!copies[j]) continue
      copies[j].requestedView = view
      copies[j].requestedRead = read
      copies[j].requestedPost = post
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
      Quickshell.execDetached([omaboxBin, "unsnooze", id])
    }
    for (var i = 0; i < copies.length; i++) {
      var panel = copies[i] && copies[i].panelItem ? copies[i].panelItem() : null
      if (panel && panel.opened) return panel.openPostById(id) ? "reading" : "no post " + id
    }
    return requestOpen(copies, "feed", -1, id)
  }

  function override(ids, fields) {
    var next = {}
    for (var key in overrides) next[key] = overrides[key]
    for (var i = 0; i < ids.length; i++) {
      var merged = {}
      for (var old in next[ids[i]] || {}) merged[old] = next[ids[i]][old]
      for (var field in fields) merged[field] = fields[field]
      next[ids[i]] = merged
    }
    overrides = next
  }

  function markRead(ids) {
    if (!ids || ids.length === 0) return
    override(ids, { read: true })
    Quickshell.execDetached([omaboxBin, "read"].concat(ids))
  }

  function snooze(item, until) {
    override([item.id], { snoozed_until: until })
    Quickshell.execDetached([omaboxBin, "snooze", item.id, "--until", until])
  }

  function toggleLater(item) {
    var later = !item.later
    override([item.id], { later: later })
    Quickshell.execDetached([omaboxBin, "later", item.id, later ? "--on" : "--off"])
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

  IpcHandler {
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
    command: ["mkdir", "-p", root.stateHome + "/omabox"]
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

  Process {
    id: tickProc
    command: [root.omaboxBin, "tick"]
    // Exit and the end of stderr arrive in either order; -1 until this run exits.
    property int exitCode: -1
    function report() {
      if (exitCode < 0) return
      var lines = tickErrors.text.trim().split("\n")
      root.tickProblem = exitCode === 0 ? "" : Model.cliProblem(exitCode, lines[lines.length - 1]) || "omabox tick exited with " + exitCode
    }
    onStarted: exitCode = -1
    onExited: function(code) {
      exitCode = code
      report()
    }
    stderr: StdioCollector {
      id: tickErrors
      waitForEnd: true
      onStreamFinished: tickProc.report()
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var lines = text.trim().split("\n")
        var seconds = parseInt(lines[lines.length - 1], 10)
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

  FileView {
    path: root.stateDirReady ? root.statePath : ""
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      root.feedState = Model.parseState(text())
      root.overrides = ({})
    }
    onLoadFailed: root.feedState = Model.parseState("")
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
    tooltipText: root.unread > 0 ? "Omabox: " + root.unread + " unread" : "Omabox"
    onPressed: function(b) {
      if (b === Qt.MiddleButton) root.markAllRead()
      else root.toggle()
    }

    Rectangle {
      visible: root.unread > 0
      width: Style.space(6)
      height: width
      radius: width / 2
      color: Color.accent
      x: button.width / 2 + Style.space(5)
      y: button.height / 2 - Style.space(9)
    }
  }
}
