import QtQuick
import QtTest
import "../Model.js" as Model

// Run by test_omabox.py (ModelJsTest) through qmltestrunner.
TestCase {
  name: "Model"

  function test_notification_action_runs_only_on_the_second_o() {
    var row = { file: "1760000000000-1.json", execArgv: JSON.stringify(["sh", "-c", "echo planted\n"]) }
    var first = Model.actionStep(row, "", "")
    compare(first.run, null)
    compare(first.pending, row.file)
    compare(first.message, 'o again to run: sh -c "echo planted\\n"')
    var second = Model.actionStep(row, first.pending, first.message)
    compare(second.run, ["sh", "-c", "echo planted\n"])
    compare(second.pending, "")
    // the line was cleared or shows something else, or the cursor is on another notification: shown again, not run
    compare(Model.actionStep(row, first.pending, "").run, null)
    compare(Model.actionStep(row, first.pending, "Copied").run, null)
    var other = { file: "1760000000001-1.json", execArgv: row.execArgv }
    compare(Model.actionStep(other, first.pending, first.message).run, null)
    compare(Model.actionStep({ file: "x" }, "", "").message, "This notification has no action.")
  }

  function test_command_line_is_whole_and_shows_hidden_characters() {
    compare(Model.commandLine(["omarchy-launch-webapp", "https://example.com/a", "x y"]),
            "omarchy-launch-webapp https://example.com/a \"x y\"")
    var long = Model.commandLine(["sh", "-c", "a".repeat(300) + " middle " + "b".repeat(200)])
    verify(long.indexOf(" middle ") > 0)
    compare(long.length, 6 + 300 + 8 + 200 + 2)
    compare(Model.commandLine(["echo", "safe\u202e\u200bgnp.exe"]), 'echo "safe\\u202e\\u200bgnp.exe"')
  }

  function test_an_action_too_long_to_show_is_not_run() {
    var row = { file: "1760000000000-1.json", execArgv: JSON.stringify(["sh", "-c", "x".repeat(700)]) }
    var first = Model.actionStep(row, "", "")
    compare(first.run, null)
    compare(first.pending, "")
    verify(first.message.indexOf("too long") > 0)
    compare(Model.actionStep(row, row.file, first.message).run, null)
  }
}
