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
          attention: { kind: "permission", text: "$ rm -rf dist/ && npm run build", ts: t - 12, answerable: true } },
        { id: "f6", project: "docs-site", entry: "cli", agent: "codex", state: "working", action: "Asking: Which framework?", since: t - 30, pid: 6, subagents: 0,
          task: "", recent: [],
          attention: { kind: "question", text: "Which framework should the docs use?", ts: t - 30, answerable: true,
                       questions: [{ q: "Which framework should the docs use?", options: ["Astro", "Docusaurus", "Plain markdown"], multi: false }] } },
        { id: "t9", project: "llm-lab", entry: "ollama", agent: "terminal", state: "idle", action: "Waiting for input", since: t - 14, pid: 9, subagents: 0,
          task: "$ ollama run deepseek-r1", recent: [],
          attention: { kind: "question", text: "Apply these changes? [y/n]", ts: t - 14, answerable: true,
                       detail: "Plan:\n  1. rename utils.py -> helpers.py\n  2. update 14 imports\nApply these changes? [y/n]" } },
        { id: "g7", project: "shop-backend", entry: "cli", state: "working", action: "Asking: Which checks?", since: t - 20, pid: 7, subagents: 0,
          ctx_tokens: 84210, out_tokens: 12950, task: "", recent: [],
          attention: { kind: "question", text: "Which checks should run before deploy?", ts: t - 20, answerable: true,
                       questions: [{ q: "Which checks should run before deploy?", options: ["Tests", "Lint", "Type check"], multi: true },
                                   { q: "Deploy target?", options: ["Staging", "Production"], multi: false }] } },
        { id: "h8", project: "blog", entry: "vscode", agent: "copilot", state: "working", action: "Plan ready for review", since: t - 45, pid: 8, subagents: 0,
          task: "add an RSS feed", recent: [],
          attention: { kind: "plan", text: "Plan ready for review", ts: t - 45,
                       detail: "## Plan\n1. Add a feed.xml route that renders the 20 newest posts.\n2. Link it from the page head.\n3. Add a test that the feed validates." } },
        { id: "b2", project: "vision-train", entry: "claude-vscode", state: "idle", action: "Finished", since: t - 250, pid: 2, subagents: 0,
          task: "fix the mAP drop after the augmentation change", recent: [],
          attention: { kind: "done", text: "Training script fixed. The mAP drop came from a <resize> applied twice in the val loader; removed the second one and re-ran eval.", ts: t - 250 } },
        { id: "c3", project: "agent-inbox", entry: "cli", state: "working", action: "Editing state.py", since: t - 3, pid: 3, subagents: 2, ctx_tokens: 238000, out_tokens: 41300,
          task: "build the overlay",
          recent: [[t - 40, "Reading PLAN.md"], [t - 31, "$ python3 tests/test_state.py"], [t - 9, "↳ Searching layershell"], [t - 3, "Editing state.py"]],
          attention: null },
        { id: "d4", project: "notes-app", entry: "ide", agent: "antigravity", state: "idle", action: "Finished", since: t - 4000, pid: 4, subagents: 0,
          task: "", recent: [], attention: null },
        { id: "e5", project: "music-player", entry: "claude-vscode", state: "idle", action: "Stopped on error", since: t - 70, pid: 5, subagents: 0,
          task: "", recent: [], attention: { kind: "error", text: "API error: rate limit reached", ts: t - 70 } }
    ]

    readonly property var few: mock.filter(s => ["a1", "f6", "b2", "e5"].indexOf(s.id) >= 0)
    readonly property var turns: [
        { start: t - 300, end: null, live: true, project: "agent-inbox", tools: 14, prompt: "add a history view to the overlay", result: "" },
        { start: t - 2400, end: t - 2150, project: "vision-train", tools: 9, prompt: "fix the mAP drop after the augmentation change",
          result: "Training script fixed. The mAP drop came from a resize applied twice in the val loader." },
        { start: t - 5200, end: t - 5170, project: "notes-app", tools: 2, prompt: "rename the export button", result: "Renamed in the toolbar and the menu." },
        { start: t - 9000, end: t - 5400, project: "web-api", tools: 131, prompt: "migrate the auth module to the new session store",
          result: "Migration done; all 212 tests pass. Two call sites still use the old cookie name behind a flag." }
    ]

    Column {
        id: stage
        padding: 24; spacing: 24
        Row {
            spacing: 24
            Panel { sessions: win.mock; view: "inbox"; limits: ({ five_hour: { pct: 62, resets_at: win.t + 5400 }, seven_day: { pct: 84, resets_at: win.t + 260000 }, warn: 80 }) }
            Panel { sessions: win.mock; view: "all"; open: ({ c3: true, h8: true }); picks: ({ g7: [["Tests", "Lint"], ["Staging"]] }) }
            Column {
                spacing: 24
                Panel { sessions: win.mock; view: "today"; history: win.turns }
                Panel { sessions: win.mock.filter(s => !s.attention); view: "inbox" }
            }
        }
        Row {
            spacing: 24
            Panel { sessions: win.few; theme: "catppuccin" }
            Panel { sessions: win.few; theme: "gruvbox" }
            Panel { sessions: win.few; theme: "nord" }
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
