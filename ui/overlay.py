#!/usr/bin/python3
"""agent-inbox overlay: subscribes to the daemon and shows Overlay.qml."""
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine

SOCK = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}") + "/agent-inbox.sock"


class Backend(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._sessions, self._visible, self._view, self._config, self._history = [], False, "inbox", {}, []
        self._limits = {}
        self._screen, self._on = "active", ""
        app = QGuiApplication.instance()
        for sig in (app.screenAdded, app.screenRemoved, app.primaryScreenChanged):
            sig.connect(self._screens_changed)
        self.sock = QLocalSocket(self)
        self.sock.connected.connect(self._subscribe)
        self.sock.readyRead.connect(self._read)
        self.sock.disconnected.connect(self._lost)
        self.sock.errorOccurred.connect(self._lost)
        self.retry = QTimer(self, interval=2000, singleShot=True)
        self.retry.timeout.connect(self._connect)
        self._connect()

    def _connect(self):
        if self.sock.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            self.sock.connectToServer(SOCK)

    def _subscribe(self):
        self._write({"kind": "subscribe", "role": "overlay"})
        self._report()

    def _screens_changed(self, *_):
        self.changed.emit()
        self._report()

    def _report(self):
        """Tell the daemon which screens exist and which one the overlay is on, for `agent-inbox screen`."""
        if self.sock.state() == QLocalSocket.LocalSocketState.ConnectedState:
            names = [s.name() for s in QGuiApplication.screens()]
            self._write({"cmd": "screens", "names": names, "on": self._on})

    def _lost(self, *_):
        self._sessions, self._visible = [], False
        self.changed.emit()
        self.retry.start()

    def _read(self):
        while self.sock.canReadLine():
            snap = json.loads(self.sock.readLine().data())
            if snap.get("type") == "state":
                self._sessions = snap["sessions"]
                self._visible = snap["ui"]["visible"]
                self._view = snap["ui"]["view"]
                self._screen = snap["ui"].get("screen") or "active"
                self._config = snap.get("config") or {}
                self._history = snap.get("history") or []
                self._limits = snap.get("limits") or {}
        self.changed.emit()

    def _write(self, msg):
        self.sock.write((json.dumps(msg) + "\n").encode())
        self.sock.flush()

    @Property("QVariantList", notify=changed)
    def sessions(self):
        return self._sessions

    @Property("QVariantMap", notify=changed)
    def limits(self):
        return self._limits

    @Property("QVariantList", notify=changed)
    def history(self):
        return self._history

    @Property("QVariantMap", notify=changed)
    def config(self):
        return self._config

    @Property(bool, notify=changed)
    def visible(self):
        return self._visible

    @Property(str, notify=changed)
    def view(self):
        return self._view

    @Property(str, notify=changed)
    def screen(self):
        """Where to open: active | primary | a screen name."""
        return self._screen

    @Property(str, notify=changed)
    def primary(self):
        s = QGuiApplication.primaryScreen()
        return s.name() if s else ""

    @Slot(str)
    def onScreen(self, name):
        if name != self._on:
            self._on = name
            self._report()

    @Slot(str, str, str)
    def send(self, cmd, session, label):
        msg = {"cmd": cmd, "session": session}
        if cmd == "answer":
            msg["answers"] = json.loads(label)  # a JSON list, one answer per question
        elif cmd == "type":
            msg["text"] = label  # raw characters for a program started with `agent-inbox run`
        self._write(msg)

    @Slot(str)
    def setView(self, view):
        self._write({"cmd": "view", "view": view})


def main():
    app = QGuiApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    backend = Backend()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("Overlay.qml"))))
    if not engine.rootObjects():
        sys.exit("could not load Overlay.qml")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
