import QtQuick
import QtQuick.Effects
import qs.Commons

// A source's glyph, or its favicon recoloured to the theme like symbolic tray icons.
Item {
  id: root

  property var icon: ({})
  property color color: Color.foreground
  property string fontFamily: Style.font.family
  property real size: Style.font.body

  readonly property string favicon: icon && icon.favicon ? String(icon.favicon) : ""
  readonly property string glyph: icon && icon.glyph ? String(icon.glyph) : String.fromCodePoint(0xF046B)

  implicitWidth: size
  implicitHeight: size

  Text {
    visible: root.favicon === "" || favicon.status !== Image.Ready
    anchors.centerIn: parent
    textFormat: Text.PlainText
    text: root.glyph
    color: root.color
    font.family: root.fontFamily
    font.pixelSize: root.size
  }

  Image {
    id: favicon
    anchors.fill: parent
    visible: false
    source: root.favicon !== "" ? "file://" + root.favicon : ""
    sourceSize.width: Math.ceil(root.size * 2)
    sourceSize.height: Math.ceil(root.size * 2)
    fillMode: Image.PreserveAspectFit
    smooth: true
    asynchronous: true
  }

  MultiEffect {
    anchors.fill: favicon
    source: favicon
    visible: root.favicon !== "" && favicon.status === Image.Ready
    saturation: -1.0
    colorization: 1.0
    colorizationColor: root.color
  }
}
