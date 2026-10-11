// Screenshot rig: the real Omabox bar widget on a stand-in bar strip over the theme's wallpaper, with the panel
// opened on one scenario. shots.py runs it in a copy of the Omarchy shell's Commons and Ui; no surface here takes
// keyboard focus or pointer input, and the panel is opened by calls, not over the live shell's IPC.
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui

ShellRoot {
  id: rig

  readonly property string scenario: Quickshell.env("SHOTS_SCENARIO") || "feed"
  readonly property string pluginDir: Quickshell.env("SHOTS_PLUGIN")
  readonly property string wallpaper: Quickshell.env("SHOTS_BACKDROP")
  readonly property var target: screenNamed(Quickshell.env("SHOTS_SCREEN"))

  function screenNamed(name) {
    for (var i = 0; i < Quickshell.screens.length; i++)
      if (Quickshell.screens[i].name === name) return Quickshell.screens[i]
    return Quickshell.screens[0]
  }

  function findItem(item, test) {
    if (!item) return null
    if (test(item)) return item
    // A panel's content sits in its window's contentItem, and windows sit in data, not children.
    var kids = [].concat(item.children ? Array.from(item.children) : [], item.data ? Array.from(item.data) : [],
                         item.contentItem ? [item.contentItem] : [])
    for (var i = 0; i < kids.length; i++) {
      if (kids[i] === item) continue
      var found = findItem(kids[i], test)
      if (found) return found
    }
    return null
  }

  function stagePanel() {
    var host = widget.item
    host.open()
    var panel = host.panelItem()
    if (!panel) return
    if (scenario === "notifications") panel.showView("notifications")
    else if (scenario === "sources") panel.showView("sources")
    else if (scenario === "reader") panel.openReader(1)
    else if (scenario === "xtoken") {
      panel.showView("sources")
      panel.startXToken("https://x.com/someone")
    } else if (scenario === "add") {
      panel.showView("sources")
      panel.startAdd()
      typeUrl.start()
    }
  }

  PanelWindow {
    screen: rig.target
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    color: Color.background
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.namespace: "omabox-shots-backdrop"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    mask: Region {}

    Image {
      anchors.fill: parent
      source: rig.wallpaper ? "file://" + rig.wallpaper : ""
      fillMode: Image.PreserveAspectCrop
      asynchronous: false
    }
  }

  PanelWindow {
    id: barWindow
    screen: rig.target
    anchors { top: true; left: true; right: true }
    implicitHeight: Style.bar.sizeHorizontal
    exclusionMode: ExclusionMode.Ignore
    color: Color.bar.background
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "omabox-shots-bar"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    mask: Region {}

    PluginBarApi {
      id: api
      pluginId: "io.github.wienieclaurowy.omabox"
      moduleName: "io.github.wienieclaurowy.omabox"
      foreground: Color.bar.text
      barForeground: Color.bar.text
      background: Color.bar.background
      urgent: Color.bar.active
      fontFamily: Style.font.family
      barSize: Style.bar.sizeHorizontal
    }

    Loader {
      id: widget
      anchors.centerIn: parent
      source: "file://" + rig.pluginDir + "/BarWidget.qml"
      onLoaded: {
        item.bar = api
        item.moduleName = api.moduleName
        item.settings = { id: api.moduleName, welcomed: rig.scenario !== "welcome" }
        opener.start()
      }
    }
  }

  // Late enough for the widget to read the demo state and for shots.py to grab the backdrop alone first.
  Timer {
    id: opener
    interval: 2800
    onTriggered: rig.stagePanel()
  }

  Timer {
    id: typeUrl
    interval: 300
    onTriggered: {
      var field = rig.findItem(widget.item.panelItem(), function(item) {
        return item.placeholderText !== undefined && String(item.placeholderText).indexOf("YouTube") >= 0
      })
      if (field) field.text = "https://x.com/someone"
    }
  }
}
