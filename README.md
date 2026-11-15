# agent-inbox

A floating overlay for Linux that shows what your open Claude Code sessions are doing, pops up when one needs you, and lets you answer without switching windows.

![preview](docs/preview.png)

- **Sees every session.** Any terminal, any folder, and the VS Code extension, through Claude Code hooks.
- **Works like an inbox.** A session appears when it asks for permission, asks a question, fails, or finishes a long turn. It disappears once you have dealt with it.
- **Answer from the overlay.** Approve or deny a permission prompt. Answer the agent's questions by picking options or typing your own reply, including multi-part and multi-select questions. The prompt in the terminal keeps working too; whichever you answer first wins.
- **Token counts.** Each card shows the session's current context size and total output tokens.
- **Stays out of the way.** Sits above other windows, only takes keyboard focus when you click a reply box, hides itself when nothing needs you.
- **Local only.** One unix socket, no network port, no telemetry.

Status: v0.1, tested on KDE Plasma 6 (Wayland) with Claude Code 2.1.

## Requirements

- A Wayland compositor with layer-shell support. KDE Plasma 6 is tested. Hyprland, Sway and niri should work but are untested. GNOME and X11 are not supported.
- Python 3.10+, PySide6, layer-shell-qt, a systemd user session.
- Claude Code.

Arch / CachyOS:

```
sudo pacman -S --needed pyside6 layer-shell-qt
```

Other distributions: install PySide6 (with QtQuick) and layer-shell-qt from your package manager. PySide6 from pip will not work for the overlay, because layer-shell-qt has to match the Qt it runs in.

## Install

```
git clone https://github.com/vp916/agent-inbox.git
cd agent-inbox
python3 install.py install
```

This does three things, all reversed by `python3 install.py uninstall`:

| Change | Where |
|---|---|
| Hook entries (your existing settings are kept, a backup is made first) | `~/.claude/settings.json` |
| Two user services: daemon and overlay | `~/.config/systemd/user/agent-inbox*.service` |
| The `agent-inbox` command | `~/.local/bin/agent-inbox` |

The hooks and services point at the cloned folder. If you move it, run install again.

Sessions that are already open pick the hooks up on their own; if one does not show, restart it.

### Hotkey

Bind `agent-inbox toggle` to a key.

- KDE: System Settings → Keyboard → Shortcuts → Add New → Command.
- Hyprland: `bind = SUPER, A, exec, agent-inbox toggle`

## Using it

The overlay stays hidden until something needs you, then appears in a corner of the screen:

| Card | Meaning | What you can do |
|---|---|---|
| `allow?` | waiting on a permission prompt | approve, deny, or answer in the terminal |
| `asks` | the agent asked a question | pick options or type a reply, or answer in the terminal |
| `plan` | a plan is ready for review | read it under `more`; approve it in the terminal (click the card to jump there) |
| `done` | a long turn finished | dismiss, or just send the next prompt |
| `error` | the turn failed | dismiss |

Click a card to jump to that session's terminal window (KDE: also switches to the right Konsole tab; Hyprland and Sway are supported but untested). `more` (shown on hover) expands a card: the prompt you gave and the last few actions. `stop` (shown on hover) ends that session after a confirmation click. The `all` tab lists every open session, including the ones working quietly.

To keep it quiet while you are already at the terminal, a permission prompt or question only pops the overlay up if it is still unanswered after 4 seconds, and "done" only counts for turns longer than 30 seconds. Both are configurable.

From the terminal:

```
agent-inbox status                 list sessions
agent-inbox watch                  live list
agent-inbox toggle | show | hide   overlay visibility
agent-inbox view inbox|all         only sessions that need you, or everything
agent-inbox dismiss [id]           clear "needs you" on one session or all
agent-inbox approve <id>           approve a permission prompt
agent-inbox deny <id>              deny it
agent-inbox answer <id> <a>...     answer a question: one answer per part (an option or any text)
agent-inbox focus <id>             bring that session's terminal to the front
agent-inbox stop <id>              end a session
```

`<id>` is any unique prefix of the session id shown by `status`.

## Configuration

Optional. Create `~/.config/agent-inbox/config.json` with any of these keys (defaults shown), then `systemctl --user restart agent-inbox`:

```json
{
  "position": "top-right",
  "margin": 14,
  "width": 460,
  "font": "",
  "alert_delay": 4,
  "done_min_turn": 30,
  "keep_days": 14,
  "sound": true
}
```

- `position`: `top-right`, `top-left`, `bottom-right` or `bottom-left`.
- `font`: a font family. Empty picks the first installed one from a built-in list of monospace fonts.
- `alert_delay`: seconds a permission prompt or question must stay unanswered before the overlay pops up.
- `done_min_turn`: seconds a turn must run before "finished" counts as needing you.
- `keep_days`: how long the event log is kept.
- `sound`: play a short sound when the overlay pops up (needs `pw-play` or `paplay` and the freedesktop sound theme).

## How it works

```
Claude Code hooks -> hook/agent_inbox_hook.py -> unix socket -> daemon/daemon.py -> ui/overlay.py
```

- **Hook script.** Forwards each hook event to the daemon and exits. It runs in the background, takes about 15 ms, and exits cleanly if the daemon is not running, so it never slows or blocks the agent. The one hook that waits is the permission request: it holds on for an answer from the overlay while Claude Code shows its own prompt as usual.
- **Daemon.** Keeps one state per session (`daemon/state.py`, a small pure state machine), decides what needs attention and when to pop the overlay up, and removes sessions whose process has gone.
- **Overlay.** A PySide6/QML window placed with layer-shell. `ui/Panel.qml` is the whole look; `ui/Preview.qml` renders it with sample data.

## Privacy

Your prompts, tool calls and the agent's last message of each turn are written to `~/.local/share/agent-inbox/events.db` on your machine so the overlay can show history and survive restarts. Events older than `keep_days` are deleted. Nothing leaves the machine.

## Limits

- You can answer a question the agent asked, but you cannot send a new prompt to an idle session from the overlay.
- Plans can be read in the overlay but must be approved in the terminal; Claude Code does not accept a plan approval from a hook.
- Claude Code only.

## Development

```
python3 tests/test_state.py
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software qml6 ui/Preview.qml -- preview.png
```

## License

MIT
