// The overlay window: a layer-shell surface above all windows, top-right, never takes keyboard focus.
// `backend` is provided by overlay.py.
import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: win
    width: panel.width
    height: panel.height
    visible: backend.visible
    color: "transparent"
    flags: Qt.FramelessWindowHint

    readonly property string pos: backend.config.position || "top-right"
    readonly property int gap: backend.config.margin === undefined ? 14 : backend.config.margin

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
        width: backend.config.width || 460
        fontFamily: backend.config.font || ""
        view: backend.view
        opacity: win.visible ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        onCommand: (cmd, session, label) => backend.send(cmd, session, label)
        onViewPicked: view => backend.setView(view)
    }
}
