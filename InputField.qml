import QtQuick
import qs.Ui

// Qt 6.12 TextInput reads the whole foreign clipboard text on every clipboard change unless readOnly
// (q_canPasteChanged); the panel stays loaded all session, so fields stay read-only until focused.
TextField {
  readOnly: !activeFocus
}
