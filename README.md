# agent-inbox

A floating overlay for Linux that shows what your open Claude Code sessions are doing and pops up when one needs you.

![preview](docs/preview.png)

- Follows every Claude Code session on the machine (terminal and VS Code) through Claude Code hooks.
- Works like an inbox: a session appears when it asks for permission, asks a question, fails, or finishes a long turn, and disappears once you have dealt with it.
- Stays above other windows without taking keyboard focus.

Status: early. Tested on KDE Plasma 6 (Wayland) only.

## Requirements

- A Wayland compositor with layer-shell support (KDE Plasma 6; Hyprland, Sway and niri are untested). Not GNOME, not X11.
- Python 3.10+, PySide6, layer-shell-qt, systemd user session.
- Arch: `sudo pacman -S --needed pyside6 layer-shell-qt`

## Install

```
python3 install.py install
```

This adds hook entries to `~/.claude/settings.json` (a backup is made first), two user systemd services, and an `amctl` link in `~/.local/bin`. `python3 install.py uninstall` reverses it.

Bind `amctl toggle` to a key to show and hide the overlay.

## Usage

```
amctl status          list sessions
amctl watch           live list in the terminal
amctl toggle          show / hide the overlay
amctl view inbox|all  only sessions that need you, or everything
amctl dismiss [id]    clear "needs you" on one session or all
amctl stop <id>       end a session
```

## How it works

```
Claude Code hooks -> hook/am_hook.py -> unix socket -> daemon/amd.py -> ui/overlay.py
```

The hook script forwards each event and exits; it runs in the background and never blocks the agent. The daemon keeps one state per session and decides what needs attention. Everything stays on the machine: one unix socket, no network port.

Prompts and commands are logged to `~/.local/share/agent-monitor/events.db` and pruned after 14 days.
