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

    LayerShell.Window.scope: "agent-monitor"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorRight
    LayerShell.Window.margins.top: 14
    LayerShell.Window.margins.right: 14
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.activateOnShow: false

    Panel {
        id: panel
        sessions: backend.sessions
        view: backend.view
        opacity: win.visible ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        onCommand: (cmd, session, label) => backend.send(cmd, session, label)
        onViewPicked: view => backend.setView(view)
    }
}
