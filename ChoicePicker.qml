import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// A Flow, so a language with long labels wraps onto a second line when given a width; without one it is a single row.
// Children are not anchored (Flow forbids it); the cancel button sits in a box as tall as a choice.
Flow {
  id: root

  // [{ key, label, choice, detail? }]; the key is only shown, the panel's key handler does the picking.
  property var choices: []
  property color foreground: Commons.Color.foreground
  property color dim: Commons.Color.foreground
  property string fontFamily: Style.font.family

  signal picked(string choice)
  signal cancelled()

  spacing: Style.space(10)

  Repeater {
    id: choiceRows
    model: root.choices

    Row {
      required property var modelData
      spacing: Style.space(4)

      Text {
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: modelData.key
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }

      Button {
        anchors.verticalCenter: parent.verticalCenter
        text: modelData.label.charAt(0).toUpperCase() + modelData.label.slice(1) + (modelData.detail ? "  " + modelData.detail : "")
        bordered: true
        foreground: root.foreground
        fontFamily: root.fontFamily
        fontSize: Style.font.caption
        onClicked: root.picked(modelData.choice)
      }
    }
  }

  Item {
    width: cancelButton.width
    height: Math.max(cancelButton.height, choiceRows.count > 0 && choiceRows.itemAt(0) ? choiceRows.itemAt(0).height : 0)

    PanelActionButton {
      id: cancelButton
      anchors.verticalCenter: parent.verticalCenter
      iconText: "󰅖"
      tooltipText: Tr.t("actions.cancel")
      foreground: root.dim
      fontFamily: root.fontFamily
      onClicked: root.cancelled()
    }
  }
}
