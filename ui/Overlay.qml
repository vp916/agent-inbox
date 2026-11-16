// The overlay window: a layer-shell surface above all windows, top-right, never takes keyboard focus.
// `backend` is provided by overlay.py.
import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: win
    width: panel.width
    height: panel.height
    visible: ready && backend.visible && !remapping
    color: "transparent"

    // Layer-shell settings that not every layer-shell-qt has (Debian 13 ships 6.3, without
    // activateOnShow) are set from code where they exist. The window stays hidden until then,
    // because a layer surface reads them when it is first shown.
    property bool ready: false
    function setLayer(name, value) {
        if (LayerShell.Window[name] != null) LayerShell.Window[name] = value   // null or undefined: not there
    }
    flags: Qt.FramelessWindowHint

    readonly property string pos: backend.config.position || "top-right"
    readonly property int gap: backend.config.margin === undefined ? 14 : backend.config.margin

    // Which screen: "active" lets KWin pick the one you are working on, each time the overlay
    // opens; "primary" or a screen name pins it. A layer surface cannot move to another screen
    // while shown, so a change hides and reopens it.
    readonly property string place: backend.screen || "active"
    property bool remapping: false
    function pick() {
        const want = place === "active" || place === "primary" ? backend.primary : place
        const all = Qt.application.screens
        for (let i = 0; i < all.length; i++)
            if (all[i].name === want) return all[i]
        return null
    }
    function applyPlace() {
        // screenConfiguration is deprecated since layer-shell-qt 6.8 but still works there
        setLayer("screenConfiguration", place === "active" ? LayerShell.Window.ScreenFromCompositor
                                                           : LayerShell.Window.ScreenFromQWindow)
        const s = pick()
        if (place !== "active" && s) win.screen = s
        if (backend.visible) { remapping = true; reopen.start() }
    }
    Timer { id: reopen; interval: 60; onTriggered: win.remapping = false }
    onPlaceChanged: applyPlace()
    readonly property string primaryName: backend.primary
    onPrimaryNameChanged: if (place === "primary") applyPlace()
    onScreenChanged: backend.onScreen(win.screen ? win.screen.name : "")
    Component.onCompleted: {
        setLayer("activateOnShow", false)
        applyPlace()
        ready = true
        backend.onScreen(win.screen ? win.screen.name : "")
    }

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
