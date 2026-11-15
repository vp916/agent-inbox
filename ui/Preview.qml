// Design preview with mock data. Renders to a PNG without touching the screen:
//   QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software qml6 ui/Preview.qml -- out.png
import QtQuick
import QtQuick.Window

Window {
    id: win
    width: stage.width; height: stage.height
    visible: true
    color: "#3b4261"

    readonly property real t: Date.now() / 1000
    readonly property var mock: [
        { id: "a1", project: "web-api", entry: "cli", state: "working", action: "$ npm run build", since: t - 12, pid: 1, subagents: 0,
          task: "ship the release build", recent: [],
          attention: { kind: "permission", text: "$ rm -rf dist/ && npm run build", ts: t - 12 } },
        { id: "b2", project: "vision-train", entry: "claude-vscode", state: "idle", action: "Finished", since: t - 250, pid: 2, subagents: 0,
          task: "fix the mAP drop after the augmentation change", recent: [],
          attention: { kind: "done", text: "Training script fixed. The mAP drop came from a <resize> applied twice in the val loader; removed the second one and re-ran eval.", ts: t - 250 } },
        { id: "c3", project: "agent-inbox", entry: "cli", state: "working", action: "Editing state.py", since: t - 3, pid: 3, subagents: 2,
          task: "build the agent monitor overlay",
          recent: [[t - 40, "Reading PLAN.md"], [t - 31, "$ python3 tests/test_state.py"], [t - 9, "↳ Searching layershell"], [t - 3, "Editing state.py"]],
          attention: null },
        { id: "d4", project: "notes-app", entry: "cli", state: "idle", action: "Finished", since: t - 4000, pid: 4, subagents: 0,
          task: "", recent: [], attention: null },
        { id: "e5", project: "music-player", entry: "claude-vscode", state: "idle", action: "Stopped on error", since: t - 70, pid: 5, subagents: 0,
          task: "", recent: [], attention: { kind: "error", text: "API error: rate limit reached", ts: t - 70 } }
    ]

    Row {
        id: stage
        padding: 24; spacing: 24
        Panel { sessions: win.mock; view: "inbox" }
        Panel { sessions: win.mock; view: "all"; open: ({ c3: true }) }
        Column {
            spacing: 24
            Panel { sessions: win.mock.filter(s => !s.attention); view: "inbox" }
            Panel { sessions: []; view: "all" }
        }
    }

    Timer {
        interval: 400; running: Qt.application.arguments.length > 0
        onTriggered: {
            const out = Qt.application.arguments[Qt.application.arguments.length - 1]
            if (!out.endsWith(".png")) return
            stage.grabToImage(r => { r.saveToFile(out); Qt.quit() })
        }
    }
}
