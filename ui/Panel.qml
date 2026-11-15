// The overlay's content. Pure presentation: sessions in, commands out.
import QtQuick

Rectangle {
    id: panel

    property var sessions: []
    property string view: "inbox"   // inbox | all | today
    property var history: []        // today's turns, newest first (only filled in the today view)
    property var limits: ({})       // plan usage: five_hour / seven_day -> {pct, resets_at}, plus warn
    property int maxBody: 640       // the list scrolls beyond this height
    property var open: ({})         // session id -> expanded
    signal command(string cmd, string session, string label)
    signal viewPicked(string view)

    readonly property var needing: sessions.filter(s => s.attention)
    readonly property var shown: view === "all" ? sessions : view === "today" ? [] : needing
    property real now: Date.now() / 1000
    property int tick: 0

    property string theme: "tokyo-night"
    readonly property var themes: ({
        "tokyo-night": { bg: "#1a1b26", hover: "#1f2335", line: "#292e42", fg: "#c0caf5", soft: "#a9b1d6", dim: "#565f89",
                         accent: "#7aa2f7", amber: "#e0af68", green: "#9ece6a", red: "#f7768e", cyan: "#7dcfff", purple: "#bb9af7" },
        "catppuccin":  { bg: "#1e1e2e", hover: "#313244", line: "#45475a", fg: "#cdd6f4", soft: "#bac2de", dim: "#6c7086",
                         accent: "#89b4fa", amber: "#f9e2af", green: "#a6e3a1", red: "#f38ba8", cyan: "#89dceb", purple: "#cba6f7" },
        "gruvbox":     { bg: "#282828", hover: "#3c3836", line: "#504945", fg: "#ebdbb2", soft: "#d5c4a1", dim: "#928374",
                         accent: "#83a598", amber: "#fabd2f", green: "#b8bb26", red: "#fb4934", cyan: "#8ec07c", purple: "#d3869b" },
        "nord":        { bg: "#2e3440", hover: "#3b4252", line: "#434c5e", fg: "#eceff4", soft: "#d8dee9", dim: "#616e88",
                         accent: "#88c0d0", amber: "#ebcb8b", green: "#a3be8c", red: "#bf616a", cyan: "#8fbcbb", purple: "#b48ead" }
    })
    readonly property var pal: themes[theme] || themes["tokyo-night"]
    readonly property color cBg: pal.bg
    readonly property color cHover: pal.hover
    readonly property color cLine: pal.line
    readonly property color cFg: pal.fg
    readonly property color cSoft: pal.soft
    readonly property color cDim: pal.dim
    readonly property color cAccent: pal.accent
    readonly property color cAmber: pal.amber
    readonly property color cGreen: pal.green
    readonly property color cRed: pal.red
    readonly property color cCyan: pal.cyan
    readonly property color cPurple: pal.purple
    property string fontFamily: ""  // empty: first installed family from the list below
    readonly property string mono: {
        if (fontFamily) return fontFamily
        const have = Qt.fontFamilies()
        for (const f of ["JetBrainsMono Nerd Font", "JetBrains Mono", "Hack", "Fira Code", "Cascadia Code",
                         "Source Code Pro", "DejaVu Sans Mono", "Liberation Mono"])
            if (have.indexOf(f) >= 0) return f
        return "monospace"
    }
    readonly property var spinner: ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    function colorOf(kind) {
        return { permission: cAmber, question: cAmber, plan: cAmber, done: cGreen, error: cRed, working: cCyan }[kind] || cDim
    }
    function glyphOf(kind) {
        if (kind === "working") return spinner[tick % spinner.length]
        return { permission: "▲", question: "▲", plan: "▲", done: "●", error: "✗" }[kind] || "○"
    }
    function labelOf(kind) {
        return { permission: "allow?", question: "asks", plan: "plan", done: "done", error: "error" }[kind] || ""
    }
    function ago(t) {
        const d = Math.max(0, Math.floor(now - t))
        return d < 60 ? d + "s" : d < 3600 ? Math.floor(d / 60) + "m" : Math.floor(d / 3600) + "h"
    }
    function dur(s) {
        s = Math.max(0, Math.round(s))
        return s < 60 ? s + "s" : s < 3600 ? Math.floor(s / 60) + "m" : Math.floor(s / 3600) + "h " + Math.floor(s % 3600 / 60) + "m"
    }
    function usage(key, name) {
        const w = limits[key]
        if (!w) return ""
        const cells = Math.min(8, Math.round(w.pct / 12.5))
        const col = w.pct >= 95 ? cRed : w.pct >= (limits.warn || 80) ? cAmber : cSoft
        const day = key === "seven_day" ? ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date(w.resets_at * 1000).getDay()] + " " : ""
        return name + " <font color='" + col + "'>" + "█".repeat(cells) + "</font>" + "░".repeat(8 - cells)
             + " <font color='" + col + "'>" + w.pct + "%</font> → " + day + clock(w.resets_at).slice(0, 5)
    }
    function clock(t) { return new Date(t * 1000).toTimeString().slice(0, 8) }
    function esc(t) { return String(t || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") }
    function k(n) { return n >= 1000 ? Math.round(n / 1000) + "k" : String(n) }

    // answers being put together for multi-part questions:
    // session id -> one entry per question, a list of picked labels or a typed string
    property var picks: ({})
    function picked(sid, i) {
        const v = (picks[sid] || [])[i]
        return Array.isArray(v) ? v : []
    }
    function answerOf(sid, i) {
        const v = (picks[sid] || [])[i]
        return Array.isArray(v) ? v.join(", ") : (v || "")
    }
    function setPick(sid, i, v) {
        const all = Object.assign({}, picks)
        const mine = (all[sid] || []).slice()
        mine[i] = v
        all[sid] = mine
        picks = all
    }
    function pick(row, i, label, multi) {
        if (row.direct) { command("answer", row.s.id, JSON.stringify([label])); return }
        const cur = picked(row.s.id, i)
        setPick(row.s.id, i, !multi ? [label]
                              : cur.indexOf(label) >= 0 ? cur.filter(x => x !== label) : cur.concat([label]))
    }
    function complete(row) {
        return row.asking && row.a.questions.every((q, i) => answerOf(row.s.id, i) !== "")
    }
    function submit(row) {
        if (!complete(row)) return
        command("answer", row.s.id, JSON.stringify(row.a.questions.map((q, i) => answerOf(row.s.id, i))))
        const all = Object.assign({}, picks)
        delete all[row.s.id]
        picks = all
    }

    function toggle(id) {
        const o = Object.assign({}, open)
        o[id] = !o[id]
        open = o
    }

    width: 460
    height: content.implicitHeight + 2 * border.width
    color: cBg
    border.width: 2
    border.color: needing.length ? cAmber : cAccent
    Behavior on border.color { ColorAnimation { duration: 250 } }

    Timer {
        interval: 100; repeat: true; running: panel.visible
        onTriggered: { panel.tick++; panel.now = Date.now() / 1000 }
    }

    component Label: Text {
        font.family: panel.mono
        font.pixelSize: 13
        color: panel.cFg
    }

    component Button: Label {
        id: btn
        property color hot: panel.cFg
        property bool active: false
        signal clicked()
        color: active || area.containsMouse ? hot : panel.cDim
        MouseArea {
            id: area
            anchors.fill: parent; anchors.margins: -4
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: btn.clicked()
        }
    }

    component Chip: Rectangle {
        id: chip
        property alias text: chipLabel.text
        property color tint: panel.cAccent
        property bool on: false
        signal clicked()
        width: chipLabel.implicitWidth + 18; height: 24
        color: on ? Qt.alpha(tint, 0.3) : chipArea.containsMouse ? Qt.alpha(tint, 0.18) : "transparent"
        border.width: 1
        border.color: on || chipArea.containsMouse ? tint : panel.cLine
        Label { id: chipLabel; anchors.centerIn: parent; color: chip.tint }
        MouseArea {
            id: chipArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chip.clicked()
        }
    }

    component Field: Rectangle {
        id: field
        property string placeholder: ""
        signal edited(string text)
        signal accepted(string text)
        width: 150; height: 24
        color: "transparent"
        border.width: 1
        border.color: input.activeFocus ? panel.cAccent : panel.cLine
        TextInput {
            id: input
            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8
            verticalAlignment: TextInput.AlignVCenter
            font.family: panel.mono; font.pixelSize: 13
            color: panel.cFg; selectionColor: panel.cAccent
            clip: true; selectByMouse: true
            onTextEdited: field.edited(text)
            onAccepted: field.accepted(text)
        }
        Label {
            anchors.fill: input
            verticalAlignment: Text.AlignVCenter
            visible: !input.text && !input.activeFocus
            text: field.placeholder; color: panel.cDim
        }
    }

    Column {
        id: content
        x: panel.border.width; y: panel.border.width
        width: panel.width - 2 * panel.border.width

        // ---- header
        Item {
            width: parent.width; height: 36
            Row {
                x: 14; spacing: 16
                anchors.verticalCenter: parent.verticalCenter
                Label { text: "agents"; color: panel.cAccent; font.bold: true }
                Repeater {
                    model: ["inbox", "all", "today"]
                    Button {
                        required property string modelData
                        text: modelData
                        active: panel.view === modelData
                        font.underline: panel.view === modelData
                        onClicked: panel.viewPicked(modelData)
                    }
                }
            }
            Label {
                anchors.right: parent.right; anchors.rightMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                text: panel.needing.length ? panel.needing.length + (panel.needing.length === 1 ? " needs you" : " need you")
                                           : panel.sessions.length + " open"
                color: panel.needing.length ? panel.cAmber : panel.cDim
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: panel.cLine }
        }

        Flickable {
            width: parent.width
            height: Math.min(body.implicitHeight, panel.maxBody)
            contentHeight: body.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: body
                width: parent.width

                // ---- empty state
                Item {
                    visible: panel.view === "today" ? panel.history.length === 0 : panel.shown.length === 0
                    width: parent.width; height: 64
                    Label {
                        anchors.centerIn: parent
                        color: panel.cDim
                        text: panel.view === "today" ? "nothing yet today"
                            : panel.sessions.length === 0 ? "no sessions open" : "nothing needs you"
                    }
                }

                // ---- sessions
                Repeater {
                    model: panel.shown.length
                    Item {
                        id: row
                        required property int index
                        readonly property var s: panel.shown[index] || ({})
                        readonly property var a: s.attention || null
                        readonly property string kind: a ? a.kind : (s.state || "idle")
                        readonly property bool expanded: !!panel.open[s.id]
                        property bool confirmStop: false
                        readonly property bool asking: !!(a && a.answerable && a.questions && a.questions.length)
                        // one single-choice question: a click or Enter answers straight away
                        readonly property bool direct: asking && a.questions.length === 1 && !a.questions[0].multi

                        width: content.width
                        height: body.implicitHeight + 18

                        Rectangle { anchors.fill: parent; color: hover.hovered ? panel.cHover : "transparent" }
                        Rectangle { width: 3; height: parent.height; color: panel.colorOf(row.kind); visible: !!row.a }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: panel.cLine
                                    visible: row.index < panel.shown.length - 1 }
                        HoverHandler { id: hover; onHoveredChanged: if (!hovered) row.confirmStop = false }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: panel.command("focus", row.s.id, "")   // jump to that terminal
                        }

                        Column {
                            id: body
                            x: 14; y: 9
                            width: parent.width - 28
                            spacing: 4

                            Item {
                                width: parent.width; height: name.implicitHeight
                                Label { id: glyph; width: 18; text: panel.glyphOf(row.kind); color: panel.colorOf(row.kind) }
                                Label { id: name; x: 18; text: row.s.project || "?"; font.bold: true }
                                Label {
                                    anchors.left: name.right; anchors.leftMargin: 10; anchors.baseline: name.baseline
                                    text: (row.s.agent && row.s.agent !== "claude" ? row.s.agent + " " : "") + (row.s.entry || "").replace("claude-", "") + (row.s.subagents ? "  +" + row.s.subagents + " agents" : "")
                                          + (row.s.ctx_tokens ? "  ctx " + panel.k(row.s.ctx_tokens) + (row.s.ctx_pct ? " " + row.s.ctx_pct + "%" : "") + " · out " + panel.k(row.s.out_tokens) : "")
                                    color: panel.cDim; font.pixelSize: 11
                                }
                                Label {
                                    anchors.right: parent.right
                                    text: panel.ago(row.a ? row.a.ts : row.s.since)
                                    color: panel.cDim
                                }
                            }

                            Item {
                                x: 18; width: parent.width - 18
                                height: Math.max(msg.implicitHeight, actions.height)
                                Label {
                                    id: msg
                                    width: parent.width - (actions.visible ? actions.width + 12 : 0)
                                    textFormat: Text.StyledText
                                    wrapMode: Text.Wrap
                                    maximumLineCount: row.expanded ? 12 : (row.a ? 2 : 1)
                                    elide: Text.ElideRight
                                    color: panel.cSoft
                                    text: row.a ? "<font color='" + panel.colorOf(row.kind) + "'>" + panel.labelOf(row.kind) + "</font>&nbsp;&nbsp;" + panel.esc(row.a.text)
                                                : panel.esc(row.s.action)
                                }
                                Row {
                                    id: actions
                                    anchors.right: parent.right
                                    spacing: 12
                                    visible: hover.hovered || !!row.a
                                    Button {
                                        visible: hover.hovered
                                        text: row.expanded ? "less" : "more"
                                        onClicked: panel.toggle(row.s.id)
                                    }
                                    Button {
                                        visible: !!row.a
                                        text: "dismiss"
                                        onClicked: panel.command("dismiss", row.s.id, "")
                                    }
                                    Button {
                                        visible: hover.hovered && !!row.s.pid
                                        text: row.confirmStop ? "sure?" : "stop"
                                        hot: panel.cRed
                                        active: row.confirmStop
                                        onClicked: {
                                            if (row.confirmStop) panel.command("stop", row.s.id, "")
                                            row.confirmStop = !row.confirmStop
                                        }
                                    }
                                }
                            }

                            Flow {
                                visible: !!(row.a && row.a.answerable) && row.kind === "permission"
                                x: 18; width: parent.width - 18
                                topPadding: 3; spacing: 8
                                Chip {
                                    text: "approve"; tint: panel.cGreen
                                    onClicked: panel.command("approve", row.s.id, "")
                                }
                                Chip {
                                    text: "deny"; tint: panel.cRed
                                    onClicked: panel.command("deny", row.s.id, "")
                                }
                            }

                            Column {
                                visible: row.asking
                                x: 18; width: parent.width - 18
                                topPadding: 3; spacing: 8
                                Repeater {
                                    model: row.asking ? row.a.questions : []
                                    Column {
                                        id: part
                                        required property var modelData
                                        required property int index
                                        width: parent.width; spacing: 5
                                        Label {
                                            visible: !row.direct
                                            width: parent.width; wrapMode: Text.Wrap
                                            color: panel.cSoft
                                            text: part.modelData.q + (part.modelData.multi ? "  (pick any)" : "")
                                        }
                                        Flow {
                                            width: parent.width; spacing: 8
                                            Repeater {
                                                model: part.modelData.options
                                                Chip {
                                                    required property string modelData
                                                    text: modelData
                                                    on: panel.picked(row.s.id, part.index).indexOf(modelData) >= 0
                                                    onClicked: panel.pick(row, part.index, modelData, part.modelData.multi)
                                                }
                                            }
                                            Field {
                                                placeholder: "or type…"
                                                onEdited: text => { if (!row.direct) panel.setPick(row.s.id, part.index, text.trim()) }
                                                onAccepted: text => {
                                                    if (!text.trim()) return
                                                    if (row.direct) panel.command("answer", row.s.id, JSON.stringify([text.trim()]))
                                                    else panel.submit(row)
                                                }
                                            }
                                        }
                                    }
                                }
                                Chip {
                                    visible: !row.direct
                                    text: "send"; tint: panel.cGreen
                                    opacity: panel.complete(row) ? 1 : 0.35
                                    onClicked: panel.submit(row)
                                }
                            }

                            Column {
                                visible: row.expanded
                                x: 18; width: parent.width - 18
                                topPadding: 4; spacing: 2
                                Label {
                                    visible: !!(row.a && row.a.detail)
                                    width: parent.width; wrapMode: Text.Wrap
                                    maximumLineCount: 16; elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                    color: panel.cSoft; font.pixelSize: 12
                                    text: row.a && row.a.detail ? row.a.detail : ""
                                }
                                Label {
                                    visible: !!row.s.task
                                    width: parent.width; elide: Text.ElideRight
                                    text: "› " + (row.s.task || ""); color: panel.cPurple
                                }
                                Repeater {
                                    model: row.expanded ? (row.s.recent || []) : []
                                    Label {
                                        required property var modelData
                                        width: parent.width; elide: Text.ElideRight
                                        textFormat: Text.StyledText
                                        color: panel.cSoft; font.pixelSize: 12
                                        text: "<font color='" + panel.cDim + "'>" + panel.clock(modelData[0]) + "</font>&nbsp;&nbsp;" + panel.esc(modelData[1])
                                    }
                                }
                            }
                        }
                    }
                }

                // ---- today's turns
                Repeater {
                    model: panel.view === "today" ? panel.history.length : 0
                    Item {
                        id: turn
                        required property int index
                        readonly property var h: panel.history[index] || ({})
                        width: content.width
                        height: turnBody.implicitHeight + 16
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: panel.cLine
                                    visible: turn.index < panel.history.length - 1 }
                        Column {
                            id: turnBody
                            x: 14; y: 8
                            width: parent.width - 28
                            spacing: 3
                            Item {
                                width: parent.width; height: turnName.implicitHeight
                                Label { text: panel.clock(turn.h.start || 0).slice(0, 5); color: panel.cDim }
                                Label { id: turnName; x: 52; text: turn.h.project || "?"; font.bold: true }
                                Label {
                                    anchors.right: parent.right
                                    color: turn.h.end ? panel.cDim : turn.h.live ? panel.cCyan : panel.cDim
                                    text: (turn.h.end ? panel.dur(turn.h.end - turn.h.start) : turn.h.live ? "running" : "unfinished")
                                          + " · " + (turn.h.tools || 0) + " tools"
                                }
                            }
                            Label {
                                x: 52; width: parent.width - 52
                                elide: Text.ElideRight
                                color: panel.cPurple
                                text: "› " + (turn.h.prompt || "")
                            }
                            Label {
                                visible: !!turn.h.result
                                x: 52; width: parent.width - 52
                                wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                                color: panel.cSoft; font.pixelSize: 12
                                text: turn.h.result || ""
                            }
                        }
                    }
                }
            }
        }

        // ---- plan usage
        Item {
            visible: !!(panel.limits.five_hour || panel.limits.seven_day)
            width: parent.width; height: 30
            Rectangle { width: parent.width; height: 1; color: panel.cLine }
            Label {
                x: 14; width: parent.width - 28
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.StyledText
                font.pixelSize: 11; color: panel.cDim
                elide: Text.ElideRight
                text: [panel.usage("five_hour", "5h"), panel.usage("seven_day", "7d")].filter(x => x).join("&nbsp;&nbsp;&nbsp;")
            }
        }
    }
}
