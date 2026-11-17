import QtQuick
import QtQuick.Controls
import Quickshell.Io
import qs.Ui
import qs.Ui as Ui
import "Model.js" as Model

// Qt 6.12 reads the whole foreign clipboard into an editable TextInput on every clipboard change and on paste, with
// no size or time cap; every such path skips read-only fields, so typing is done here and paste goes through paster.
// Costs: no undo, no input method (CJK). Callers' Keys.onPressed still runs, after this one.
Ui.TextField {
  id: field

  property int maxChars: 4096

  readOnly: true
  cursorVisible: activeFocus
  ContextMenu.menu: null
  // Qt paints no built-in cursor in a read-only field; a delegate is still placed at cursorRectangle.
  cursorDelegate: Rectangle {
    width: 1
    color: field.color
    visible: field.cursorVisible
  }

  function edit(start, end, insert) {
    var next = Model.spliceField(text, start, end, insert, maxChars)
    if (next.text !== text) text = next.text
    cursorPosition = next.cursor
  }

  // Qt's own copy sets no sensitive hint, and a field can hold a private feed URL with a token in it.
  // cut: the selection is deleted only once the copy succeeded (the field has no undo), and only if it is unchanged.
  function copySelection(cut) {
    if (echoMode !== TextInput.Normal || selectionStart === selectionEnd || copier.running) return
    copier.text = text.slice(selectionStart, selectionEnd)
    copier.cut = cut === true
    copier.cutFrom = selectionStart
    copier.cutTo = selectionEnd
    copier.stdinEnabled = true
    copier.running = true
  }

  // Qt copies a mouse selection to the primary selection on release, with no sensitive hint and even read-only, so
  // the field never sees mouse events: a click only places the cursor.
  MouseArea {
    anchors.fill: parent
    cursorShape: Qt.IBeamCursor
    onPressed: function(mouse) {
      field.forceActiveFocus()
      field.deselect()
      field.cursorPosition = field.positionAt(mouse.x, mouse.y)
    }
  }

  Process {
    id: copier
    property string text: ""
    property bool cut: false
    property int cutFrom: 0
    property int cutTo: 0
    environment: ({ OMABOX_COPY: "sensitive" })
    command: Model.bounded(["bash", "-c", Model.COPY_SCRIPT], Model.SMALL_OUTPUT_BYTES, 10)
    // Turning stdin off closes it, the EOF the copy waits for.
    onStarted: {
      write(text)
      text = ""
      stdinEnabled = false
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (copier.cut && /::exit 0$/.test(text) && field.selectionStart === copier.cutFrom
            && field.selectionEnd === copier.cutTo)
          field.edit(copier.cutFrom, copier.cutTo, "")
        copier.cut = false
      }
    }
  }

  Process {
    id: paster
    command: Model.bounded(["wl-paste", "--no-newline", "--type", "text"], 16384, 2)
    stdout: StdioCollector {
      waitForEnd: true
      // stderr is merged, so only a clean exit is clipboard text; past the cap nothing is pasted
      onStreamFinished: {
        var end = text.match(/::exit 0$/)
        var clip = end ? text.slice(0, end.index) : ""
        if (clip !== "" && field.activeFocus && field.enabled) field.edit(field.selectionStart, field.selectionEnd, clip)
      }
    }
  }

  Keys.onPressed: function(event) {
    var from = selectionStart
    var to = selectionEnd
    var ctrl = (event.modifiers & Qt.ControlModifier) !== 0
    var alt = (event.modifiers & Qt.AltModifier) !== 0
    if (event.matches(StandardKey.Paste)) {
      if (!paster.running) paster.running = true
    } else if (event.matches(StandardKey.Copy)) {
      copySelection()
    } else if (event.matches(StandardKey.Cut)) {
      copySelection(true)
    } else if (event.key === Qt.Key_Backspace) {
      edit(from !== to ? from : ctrl ? Model.wordStart(text, from) : Model.charStep(text, from, false), to, "")
    } else if (event.key === Qt.Key_Delete) {
      edit(from, from !== to ? to : Model.charStep(text, to, true), "")
    } else if (event.text !== "" && !/[\u0000-\u001f\u007f]/.test(event.text)
               && !(event.modifiers & Qt.MetaModifier) && ctrl === alt) {
      // ctrl === alt: plain keys, and Ctrl+Alt as some layouts report AltGr
      edit(from, to, event.text)
    } else {
      return
    }
    event.accepted = true
  }
}
