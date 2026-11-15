// The overlay's content. Pure presentation: sessions in, commands out.
import QtQuick

Rectangle {
    id: panel

    property var sessions: []
    property string view: "inbox"   // inbox | all
    property var open: ({})         // session id -> expanded
    signal command(string cmd, string session, string label)
    signal viewPicked(string view)

    readonly property var needing: sessions.filter(s => s.attention)
    readonly property var shown: view === "all" ? sessions : needing
    property real now: Date.now() / 1000
    property int tick: 0

    // Tokyo Night
    readonly property color cBg: "#1a1b26"
    readonly property color cHover: "#1f2335"
    readonly property color cLine: "#292e42"
    readonly property color cFg: "#c0caf5"
    readonly property color cSoft: "#a9b1d6"
    readonly property color cDim: "#565f89"
    readonly property color cAccent: "#7aa2f7"
    readonly property color cAmber: "#e0af68"
    readonly property color cGreen: "#9ece6a"
    readonly property color cRed: "#f7768e"
    readonly property color cCyan: "#7dcfff"
    readonly property color cPurple: "#bb9af7"
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
    function clock(t) { return new Date(t * 1000).toTimeString().slice(0, 8) }
    function esc(t) { return String(t || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") }
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
        signal clicked()
        width: chipLabel.implicitWidth + 18; height: 24
        color: chipArea.containsMouse ? Qt.alpha(tint, 0.18) : "transparent"
        border.width: 1
        border.color: chipArea.containsMouse ? tint : panel.cLine
        Label { id: chipLabel; anchors.centerIn: parent; color: chip.tint }
        MouseArea {
            id: chipArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chip.clicked()
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
                    model: ["inbox", "all"]
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

        // ---- empty state
        Item {
            visible: panel.shown.length === 0
            width: parent.width; height: 64
            Label {
                anchors.centerIn: parent
                color: panel.cDim
                text: panel.sessions.length === 0 ? "no sessions open" : "nothing needs you"
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

                width: content.width
                height: body.implicitHeight + 18

                Rectangle { anchors.fill: parent; color: hover.hovered ? panel.cHover : "transparent" }
                Rectangle { width: 3; height: parent.height; color: panel.colorOf(row.kind); visible: !!row.a }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: panel.cLine
                            visible: row.index < panel.shown.length - 1 }
                HoverHandler { id: hover; onHoveredChanged: if (!hovered) row.confirmStop = false }
                MouseArea { anchors.fill: parent; onClicked: panel.toggle(row.s.id) }

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
                            text: (row.s.entry || "").replace("claude-", "") + (row.s.subagents ? "  +" + row.s.subagents + " agents" : "")
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
                        visible: !!(row.a && row.a.answerable) && (row.kind === "permission" || !!row.a.options)
                        x: 18; width: parent.width - 18
                        topPadding: 3; spacing: 8
                        Chip {
                            visible: row.kind === "permission"
                            text: "approve"; tint: panel.cGreen
                            onClicked: panel.command("approve", row.s.id, "")
                        }
                        Chip {
                            visible: row.kind === "permission"
                            text: "deny"; tint: panel.cRed
                            onClicked: panel.command("deny", row.s.id, "")
                        }
                        Repeater {
                            model: row.kind === "question" && row.a && row.a.options ? row.a.options : []
                            Chip {
                                required property string modelData
                                text: modelData
                                onClicked: panel.command("answer", row.s.id, modelData)
                            }
                        }
                    }

                    Column {
                        visible: row.expanded
                        x: 18; width: parent.width - 18
                        topPadding: 4; spacing: 2
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
    }
}
