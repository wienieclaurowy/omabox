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

  function test_command_line_quotes_and_shortens() {
    compare(Model.commandLine(["omarchy-launch-webapp", "https://example.com/a", "x y"]),
            "omarchy-launch-webapp https://example.com/a \"x y\"")
    var long = Model.commandLine(["sh", "-c", "a".repeat(300) + " tail"])
    verify(long.length <= 120)
    verify(long.indexOf("sh -c ") === 0)
    verify(long.indexOf(" tail\"") === long.length - 6)
  }
}
