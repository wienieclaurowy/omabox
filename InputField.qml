import QtQuick
import QtQuick.Controls
import Quickshell.Io
import qs.Ui
import "Model.js" as Model

// Qt 6.12 reads the whole foreign clipboard into an editable TextInput on every clipboard change and on paste, with
// no size or time cap; every such path skips read-only fields, so typing is done here and paste goes through paster.
// Costs: no undo, no input method (CJK). Callers' Keys.onPressed still runs, after this one.
TextField {
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

  Process {
    id: paster
    command: ["timeout", "-k", "1", "2", "sh", "-c", "wl-paste --no-newline --type text 2>/dev/null | head -c 16384"]
    stdout: StdioCollector { id: pasted }
    onExited: {
      var clip = pasted.text.replace(/�+$/, "")
      if (clip !== "" && field.activeFocus && field.enabled) field.edit(field.selectionStart, field.selectionEnd, clip)
    }
  }

  Keys.onPressed: function(event) {
    var from = selectionStart
    var to = selectionEnd
    var ctrl = (event.modifiers & Qt.ControlModifier) !== 0
    var alt = (event.modifiers & Qt.AltModifier) !== 0
    if (event.matches(StandardKey.Paste)) {
      if (!paster.running) paster.running = true
    } else if (event.matches(StandardKey.Cut)) {
      copy()
      edit(from, to, "")
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
