#!/usr/bin/env python3
"""Install or remove agent-inbox for the current user.

  install.py install     hooks in ~/.claude/settings.json, user systemd services, `agent-inbox` command
  install.py uninstall   reverse all of that (event database and config are kept)

The hooks and services point at this folder. If you move it, run install again.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
SETTINGS = HOME / ".claude/settings.json"
BACKUP = HOME / ".claude/settings.json.before-agent-inbox"
UNITS = HOME / ".config/systemd/user"
DAEMON_UNIT = UNITS / "agent-inbox.service"
OVERLAY_UNIT = UNITS / "agent-inbox-overlay.service"
LINK = HOME / ".local/bin/agent-inbox"
MARK = "agent_inbox_hook.py"
STATUS_MARK = "agent_inbox_statusline.py"
# The system interpreter is the one distro PySide6 packages install into.
PY = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
CMD = f"{PY} -I -S {shlex.quote(str(ROOT / 'hook' / MARK))} || true"
STATUS_CMD = f"{PY} -I -S {shlex.quote(str(ROOT / 'hook' / STATUS_MARK))}"
EVENTS = [
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest", "PermissionDenied",
    "PostToolUse", "PostToolUseFailure", "Notification", "SubagentStart", "SubagentStop",
    "Stop", "StopFailure", "PreCompact", "SessionEnd",
]  # fmt: skip


def systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True).returncode == 0


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
    # Plan usage only reaches us through the status line. Never replace someone's own.
    line = settings.get("statusLine")
    ours = isinstance(line, dict) and STATUS_MARK in line.get("command", "")
    kept_other = False
    if add and (line is None or ours):
        settings["statusLine"] = {"type": "command", "command": STATUS_CMD}
    elif add:
        kept_other = True
    elif ours:
        del settings["statusLine"]
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")
    return kept_other


def check():
    """Returns (can run the overlay, list of problems to tell the user about)."""
    problems = []
    if sys.version_info < (3, 10):
        sys.exit("agent-inbox needs Python 3.10 or newer")
    has_qt = subprocess.run([PY, "-c", "import PySide6.QtQml"], capture_output=True).returncode == 0
    if not has_qt:
        problems.append(
            f"PySide6 is not available to {PY}, so the overlay was not installed (the daemon and the "
            "`agent-inbox` command still work). Install PySide6 and layer-shell-qt from your distribution "
            "(Arch: sudo pacman -S --needed pyside6 layer-shell-qt), then run install again."
        )
    if os.environ.get("XDG_SESSION_TYPE") != "wayland":
        problems.append("This is not a Wayland session. The overlay needs Wayland with layer-shell support.")
    elif "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        problems.append("GNOME does not support layer-shell, so the overlay cannot stay above other windows.")
    if str(LINK.parent) not in os.environ.get("PATH", "").split(":"):
        problems.append(f"{LINK.parent} is not on your PATH; use the full path {LINK} or add it.")
    return has_qt, problems


def install():
    has_qt, problems = check()
    if not shutil.which("systemctl") or not systemctl("show-environment"):
        sys.exit(
            "No systemd user session found, nothing was installed. agent-inbox needs one to start "
            "its daemon and overlay."
        )
    UNITS.mkdir(parents=True, exist_ok=True)
    DAEMON_UNIT.write_text(
        "[Unit]\nDescription=agent-inbox daemon\n\n"
        f"[Service]\nExecStart={PY} {ROOT / 'daemon/daemon.py'}\nRestart=on-failure\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    units = [DAEMON_UNIT.name]
    if has_qt:
        OVERLAY_UNIT.write_text(
            "[Unit]\nDescription=agent-inbox overlay\n"
            "After=graphical-session.target agent-inbox.service\nPartOf=graphical-session.target\n\n"
            f"[Service]\nExecStart={PY} {ROOT / 'ui/overlay.py'}\nRestart=on-failure\nRestartSec=3\n\n"
            "[Install]\nWantedBy=graphical-session.target\n"
        )
        units.append(OVERLAY_UNIT.name)
    systemctl("daemon-reload")
    for unit in units:
        systemctl("enable", unit)
        if not systemctl("restart", unit):
            problems.append(f"{unit} did not start: journalctl --user -u {unit}")
    LINK.parent.mkdir(parents=True, exist_ok=True)
    LINK.unlink(missing_ok=True)
    LINK.symlink_to(ROOT / "bin/agent-inbox")
    if edit_hooks(add=True):
        problems.append(
            "You already have a custom status line, so it was left alone and the plan-usage display is off. "
            f"To turn it on, pipe your status line's input through {ROOT / 'hook' / STATUS_MARK} as well."
        )
    print(f"Installed.\n  hooks:    {SETTINGS} (backup: {BACKUP.name})\n  services: {', '.join(units)}\n  command:  {LINK}")
    print("Bind `agent-inbox toggle` to a key to show and hide the overlay.")
    for p in problems:
        print(f"\nNote: {p}")


def uninstall():
    edit_hooks(add=False)
    systemctl("disable", "--now", OVERLAY_UNIT.name, DAEMON_UNIT.name)
    DAEMON_UNIT.unlink(missing_ok=True)
    OVERLAY_UNIT.unlink(missing_ok=True)
    systemctl("daemon-reload")
    LINK.unlink(missing_ok=True)
    print("Removed hooks, services and the agent-inbox command.")
    print("Kept: ~/.local/share/agent-inbox (event log) and ~/.config/agent-inbox (config). Delete them if you like.")


if __name__ == "__main__":
    action = {"install": install, "uninstall": uninstall}.get(sys.argv[1] if len(sys.argv) > 1 else "")
    if not action:
        sys.exit(__doc__)
    action()
