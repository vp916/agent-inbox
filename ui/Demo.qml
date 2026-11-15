// Scripted demo with sample data, rendered frame by frame without touching the screen:
//   QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software qml6 ui/Demo.qml -- <frames dir>
// then:  ffmpeg -framerate 8 -i <frames dir>/f%03d.png -vf "split[a][b];[a]palettegen[p];[b][p]paletteuse" docs/demo.gif
import QtQuick
import QtQuick.Window

Window {
    id: win
    width: stage.width; height: stage.height
    visible: true

    readonly property real t0: Date.now() / 1000
    property int frame: 0
    property int step: 0

    // [frames to hold, view, sessions needing attention, picks]
    readonly property var script: [
        { hold: 10, view: "all", ask: "", picks: [] },
        { hold: 14, view: "inbox", ask: "permission", picks: [] },
        { hold: 8, view: "inbox", ask: "", picks: [] },
        { hold: 10, view: "inbox", ask: "question", picks: [] },
        { hold: 5, view: "inbox", ask: "question", picks: [["Tests"]] },
        { hold: 5, view: "inbox", ask: "question", picks: [["Tests", "Lint"]] },
        { hold: 8, view: "inbox", ask: "question", picks: [["Tests", "Lint"], ["Staging"]] },
        { hold: 14, view: "inbox", ask: "done", picks: [] },
        { hold: 12, view: "today", ask: "", picks: [] }
    ]
    readonly property var now_: script[step]

    function session(id, project, entry, action, ctx, attention, agent) {
        return { id: id, project: project, entry: entry, agent: agent || "claude", state: "working", action: action, since: t0 - 3, pid: 1, subagents: 0,
                 ctx_tokens: ctx, ctx_pct: Math.round(ctx / 2000), out_tokens: Math.round(ctx / 7), task: "", recent: [], attention: attention }
    }
    readonly property var sessions: [
        session("a", "web-api", "vscode", "$ npm run build", 84000,
                now_.ask === "permission" ? { kind: "permission", text: "$ rm -rf dist/ && npm run build", ts: t0, answerable: true } : null, "copilot"),
        session("b", "shop-backend", "claude-vscode", "Editing deploy.yml", 126000,
                now_.ask === "question" ? { kind: "question", text: "Which checks should run before deploy?", ts: t0, answerable: true,
                    questions: [{ q: "Which checks should run before deploy?", options: ["Tests", "Lint", "Type check"], multi: true },
                                { q: "Deploy target?", options: ["Staging", "Production"], multi: false }] } : null),
        session("c", "vision-train", "cli", now_.ask === "done" ? "Finished" : "$ python train.py --epochs 40", 41000,
                now_.ask === "done" ? { kind: "done", text: "Training finished: mAP 0.71 on the validation split, weights saved to runs/exp12.", ts: t0 } : null, "codex")
    ]
    readonly property var turns: [
        { start: t0 - 240, end: t0 - 5, project: "vision-train", tools: 23, prompt: "train for 40 epochs and report mAP",
          result: "Training finished: mAP 0.71 on the validation split, weights saved to runs/exp12." },
        { start: t0 - 900, end: null, live: true, project: "shop-backend", tools: 37, prompt: "set up the deploy pipeline", result: "" },
        { start: t0 - 2400, end: t0 - 2150, project: "web-api", tools: 9, prompt: "clean and rebuild the release bundle",
          result: "Rebuilt; bundle is 18% smaller after dropping the unused locale files." }
    ]

    Rectangle {
        id: stage
        width: 508; height: 430
        color: "#11121a"
        Panel {
            x: 24; y: 24
            sessions: win.sessions
            view: win.now_.view
            history: win.turns
            picks: ({ b: win.now_.picks })
            limits: ({ five_hour: { pct: 62, resets_at: win.t0 + 5400 }, seven_day: { pct: 41, resets_at: win.t0 + 260000 }, warn: 80 })
        }
    }

    property int held: 0
    Timer {
        interval: 110; repeat: true; running: true
        onTriggered: {
            const dir = Qt.application.arguments[Qt.application.arguments.length - 1]
            const name = dir + "/f" + String(win.frame).padStart(3, "0") + ".png"
            stage.grabToImage(r => r.saveToFile(name))
            win.frame++
            if (++win.held >= win.now_.hold) {
                win.held = 0
                if (win.step === win.script.length - 1) { running = false; quit.start() }
                else win.step++
            }
        }
    }
    Timer { id: quit; interval: 600; onTriggered: Qt.quit() }
}
