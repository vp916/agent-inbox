#!/usr/bin/python3
"""Install or remove Agent Monitor on this machine.

  install.py install     hooks in ~/.claude/settings.json, user systemd service, amctl link
  install.py uninstall   reverse all of that (event database is kept)
"""
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
SETTINGS = HOME / ".claude/settings.json"
BACKUP = HOME / ".claude/settings.json.before-agent-monitor"
UNIT = HOME / ".config/systemd/user/agent-monitor.service"
OVERLAY_UNIT = UNIT.with_name("agent-monitor-overlay.service")
LINK = HOME / ".local/bin/amctl"
MARK = "am_hook.py"
CMD = f"/usr/bin/python3 -I -S {shlex.quote(str(ROOT / 'hook' / MARK))} || true"
EVENTS = [
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest", "PermissionDenied",
    "PostToolUse", "PostToolUseFailure", "Notification", "SubagentStart", "SubagentStop",
    "Stop", "StopFailure", "PreCompact", "SessionEnd",
]  # fmt: skip


def systemctl(*args):
    subprocess.run(["systemctl", "--user", *args], check=False)


def edit_hooks(add):
    settings = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    if add and SETTINGS.exists() and not BACKUP.exists():
        shutil.copy2(SETTINGS, BACKUP)
    hooks = settings.get("hooks", {})
    for event in list(hooks):  # drop our old entries, keep everyone else's
        hooks[event] = [
            g for g in hooks[event] if not any(MARK in h.get("command", "") for h in g.get("hooks", []))
        ]
        if not hooks[event]:
            del hooks[event]
    if add:
        for event in EVENTS:
            hook = {"type": "command", "command": CMD, "timeout": 5}
            if event == "PermissionRequest":  # waits for an answer from the overlay
                hook["timeout"] = 330
            elif event != "SessionEnd":  # the process is exiting; let it finish sending
                hook["async"] = True
            hooks.setdefault(event, []).append({"hooks": [hook]})
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)
    SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")


def install():
    UNIT.parent.mkdir(parents=True, exist_ok=True)
    UNIT.write_text(
        "[Unit]\nDescription=Agent Monitor daemon\n\n"
        f"[Service]\nExecStart=/usr/bin/python3 {ROOT / 'daemon/amd.py'}\nRestart=on-failure\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    has_qt = subprocess.run(["/usr/bin/python3", "-c", "import PySide6"], capture_output=True).returncode == 0
    if has_qt:
        OVERLAY_UNIT.write_text(
            "[Unit]\nDescription=Agent Monitor overlay\n"
            "After=graphical-session.target agent-monitor.service\nPartOf=graphical-session.target\n\n"
            f"[Service]\nExecStart=/usr/bin/python3 {ROOT / 'ui/overlay.py'}\nRestart=on-failure\nRestartSec=3\n\n"
            "[Install]\nWantedBy=graphical-session.target\n"
        )
    else:
        print("PySide6 missing, overlay not installed. Run: sudo pacman -S --needed pyside6, then install again")
    systemctl("daemon-reload")
    for unit in ["agent-monitor.service"] + (["agent-monitor-overlay.service"] if has_qt else []):
        systemctl("enable", unit)
        systemctl("restart", unit)
    LINK.parent.mkdir(parents=True, exist_ok=True)
    LINK.unlink(missing_ok=True)
    LINK.symlink_to(ROOT / "bin/amctl")
    edit_hooks(add=True)
    print(f"installed. hooks in {SETTINGS} (backup: {BACKUP.name}), service running, amctl at {LINK}")


def uninstall():
    edit_hooks(add=False)
    systemctl("disable", "--now", "agent-monitor-overlay.service", "agent-monitor.service")
    UNIT.unlink(missing_ok=True)
    OVERLAY_UNIT.unlink(missing_ok=True)
    systemctl("daemon-reload")
    LINK.unlink(missing_ok=True)
    print("removed hooks, service and amctl link. Event database kept in ~/.local/share/agent-monitor")


if __name__ == "__main__":
    action = {"install": install, "uninstall": uninstall}.get(sys.argv[1] if len(sys.argv) > 1 else "")
    if not action:
        sys.exit(__doc__)
    action()
