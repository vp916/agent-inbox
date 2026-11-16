// The overlay window: a layer-shell surface above all windows, top-right, never takes keyboard focus.
// `backend` is provided by overlay.py.
import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: win
    width: panel.width
    height: panel.height
    visible: backend.visible && !remapping
    color: "transparent"
    flags: Qt.FramelessWindowHint

    readonly property string pos: backend.config.position || "top-right"
    readonly property int gap: backend.config.margin === undefined ? 14 : backend.config.margin

    // Which screen: "active" lets KWin pick the one you are working on, each time the overlay
    // opens; "primary" or a screen name pins it. A layer surface cannot move to another screen
    // while shown, so a change hides and reopens it.
    readonly property string place: backend.screen || "active"
    property bool remapping: false
    // screenConfiguration is deprecated since layer-shell-qt 6.8 but works everywhere from 6.0 on
    LayerShell.Window.screenConfiguration: place === "active" ? LayerShell.Window.ScreenFromCompositor
                                                              : LayerShell.Window.ScreenFromQWindow
    function pick() {
        const want = place === "active" || place === "primary" ? backend.primary : place
        const all = Qt.application.screens
        for (let i = 0; i < all.length; i++)
            if (all[i].name === want) return all[i]
        return null
    }
    function applyPlace() {
        const s = pick()
        if (place !== "active" && s) win.screen = s
        if (backend.visible) { remapping = true; reopen.start() }
    }
    Timer { id: reopen; interval: 60; onTriggered: win.remapping = false }
    onPlaceChanged: applyPlace()
    readonly property string primaryName: backend.primary
    onPrimaryNameChanged: if (place === "primary") applyPlace()
    onScreenChanged: backend.onScreen(win.screen ? win.screen.name : "")
    Component.onCompleted: { applyPlace(); backend.onScreen(win.screen ? win.screen.name : "") }

    LayerShell.Window.scope: "agent-inbox"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: (pos.startsWith("bottom") ? LayerShell.Window.AnchorBottom : LayerShell.Window.AnchorTop)
                               | (pos.endsWith("left") ? LayerShell.Window.AnchorLeft : LayerShell.Window.AnchorRight)
    LayerShell.Window.margins.top: gap
    LayerShell.Window.margins.bottom: gap
    LayerShell.Window.margins.left: gap
    LayerShell.Window.margins.right: gap
    // focus only when the user clicks into a reply box
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityOnDemand
    LayerShell.Window.activateOnShow: false

    Panel {
        id: panel
        sessions: backend.sessions
        history: backend.history
        limits: backend.limits
        theme: backend.config.theme || "tokyo-night"
        width: backend.config.width || 460
        fontFamily: backend.config.font || ""
        view: backend.view
        opacity: win.visible ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        onCommand: (cmd, session, label) => backend.send(cmd, session, label)
        onViewPicked: view => backend.setView(view)
    }
}
