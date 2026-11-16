# agent-inbox

**One inbox for your coding agents.**

You start an agent in a terminal, switch to the browser, and ten minutes later find it has been waiting for a "yes" the whole time. agent-inbox fixes that. It is a small overlay for Linux that sits in a corner of your screen, shows what every agent session on your machine is doing, pops up the moment one needs you, and lets you answer right there.

![demo](docs/demo.gif)

It works with Claude Code, OpenCode, Codex, GitHub Copilot and Antigravity out of the box, and with any other terminal program (a local model, another agent, a long script) through `agent-inbox run`.

## What you get

- **Every session in one place.** Any terminal, any folder, any editor. Each card is tagged with its agent and where it runs, for example `■ claude · cli`, `■ opencode · cli`, `■ copilot · vscode`.
- **It only bothers you when needed.** The overlay stays hidden and appears when a session asks for permission, asks a question, fails, or finishes a long task. When you have dealt with it, it hides again.
- **Answer without switching windows.** Approve or deny a command, pick an option, or type a reply in the overlay.
- **Jump to the right window.** Click a card and the terminal or editor running that session comes to the front.
- **Today at a glance.** A `today` tab lists everything your agents did today: when, how long, the prompt and the result.
- **Usage in view.** For Claude subscriptions, how much of your 5-hour and weekly limit is used, with a warning before you run out.
- **Private.** Everything stays on your machine. No account, no network port, no telemetry.

All states and themes in one picture: [docs/preview.png](docs/preview.png).

## Supported agents

| Agent | You see | You can answer from the overlay |
|---|---|---|
| **Claude Code** (terminal and VS Code extension) | current action, permission requests, questions, plans, finished, errors, tokens, plan usage | approve / deny, pick options, typed replies |
| **OpenCode** 1.x and 2.x | current action, permission requests, questions, finished, errors | approve / deny, pick options, typed replies |
| **Codex CLI** | current action, permission requests, finished | approve / deny |
| **GitHub Copilot** (VS Code agent and Copilot CLI) | current action, finished, errors | approve / deny shell commands (opt-in in VS Code) |
| **Antigravity** | current action, finished | approve / deny shell commands (opt-in) |
| **Anything else** in a terminal, via `agent-inbox run` | last output, "waiting for input" | typed replies and key presses |

Tested on KDE Plasma 6 (Wayland). Details and limits for each agent are under [Agent notes](#agent-notes).

## Install

You need Linux with a **Wayland** desktop that supports layer-shell: KDE Plasma 6 (tested), Hyprland, Sway or niri (should work, untested). **GNOME and X11 are not supported.**

**1. Install the package** for your distribution:

Fedora 42+:
```
curl -LO https://github.com/vp916/agent-inbox/releases/download/v0.4.0/agent-inbox-0.4.0-1.noarch.rpm
sudo dnf install ./agent-inbox-0.4.0-1.noarch.rpm
```

Kubuntu / Ubuntu 25.04+, Debian 13:
```
curl -LO https://github.com/vp916/agent-inbox/releases/download/v0.4.0/agent-inbox_0.4.0-1_all.deb
sudo apt install ./agent-inbox_0.4.0-1_all.deb
```

Arch / CachyOS:
```
sudo pacman -U https://github.com/vp916/agent-inbox/releases/download/v0.4.0/agent-inbox-0.4.0-1-any.pkg.tar.zst
```

Other distributions: see [From source](#from-source) below.

**2. Set it up**, as your normal user (no sudo):
```
agent-inbox-setup install
```

**3. One-time steps for some agents:**
- **Codex:** Codex only runs hooks you have approved. Open Codex, type `/hooks`, and trust the agent-inbox entries.
- **OpenCode 2:** OpenCode loads plugins when its background service starts, so run `opencode service restart` once.

**4. Check it works:**
```
agent-inbox status
```
It should list your open agent sessions. Give an agent a task: when it needs you, a card appears in the top-right corner of the screen.

### Uninstall

```
agent-inbox-setup uninstall
```

Removes every hook, the services and the command; your event log and config are kept. Then remove the package with `dnf`, `apt` or `pacman`.

### From source

Install PySide6 (with QtQuick) and layer-shell-qt from your package manager, then run the installer from the repository:

```
sudo pacman -S --needed pyside6 layer-shell-qt     # Arch / CachyOS
sudo dnf install python3-pyside6 layer-shell-qt    # Fedora

git clone https://github.com/vp916/agent-inbox.git
cd agent-inbox
python3 install.py install                          # uninstall: python3 install.py uninstall
```

Requires Python 3.10+ and a systemd user session. PySide6 from pip does not work for the overlay, because layer-shell-qt has to match the Qt version it runs in. The hooks point at the cloned folder, so if you move it, run the install again. Arch users can also build the package from [`packaging/aur/PKGBUILD`](packaging/aur/PKGBUILD) with `makepkg -si`.

<details>
<summary>What setup changes on your machine</summary>

| Does this | Where |
|---|---|
| Adds hooks for each agent it finds on your machine | Claude Code `~/.claude/settings.json`, Codex `~/.codex/hooks.json`, Copilot `~/.copilot/hooks/agent-inbox.json`, Antigravity `~/.gemini/config/hooks.json`, OpenCode `~/.config/opencode/plugins/agent-inbox.js` |
| Adds a Claude Code status line (only if you have none), needed for plan usage | `~/.claude/settings.json` |
| Starts two background services: the daemon and the overlay | `~/.config/systemd/user/agent-inbox*.service` |
| Puts the `agent-inbox` command on your PATH | `~/.local/bin/agent-inbox` (source install only) |

Your existing settings are kept, and a backup of the Claude Code and Codex files is made first.

</details>

## Using it

Just use your agents as usual. The overlay appears on its own when something needs you.

| Card | Meaning | What you can do |
|---|---|---|
| `allow?` | the agent wants to run something and needs your OK | approve, deny, or answer in the agent's own window |
| `asks` | the agent asked you a question | pick an option, type a reply, or answer in its window |
| `plan` | a plan is ready for review | read it under `more`, approve it in the agent's window |
| `done` | a long task finished | dismiss, or just send your next prompt |
| `error` | the task failed | dismiss |

- **Click a card** to bring that session's terminal or editor window to the front. On KDE this also selects the right Konsole tab.
- **`more`** (shown on hover) expands a card: your prompt and the last few actions.
- **`dismiss`** clears one card. **`✕`** in the header hides the overlay until the next thing needs you.
- **`stop`** (shown on hover) ends that session after a confirmation click.
- **Tabs:** `inbox` shows only what needs you, `all` shows every open session, `today` shows today's history.

To keep it quiet while you are already looking at the agent, a permission request or question only pops the overlay up if it is still unanswered after 4 seconds, and `done` only counts for tasks longer than 30 seconds. Both are adjustable.

To open the overlay yourself, bind `agent-inbox toggle` to a key:

- KDE: System Settings → Keyboard → Shortcuts → Add New → Command or Script.
- Hyprland: `bind = SUPER, A, exec, agent-inbox toggle`

## Any other program: `agent-inbox run`

For anything without its own integration (a local model in a terminal, another agent, an installer, a long build), start it through agent-inbox:

```
agent-inbox run ollama run deepseek-r1
agent-inbox run ./deploy.sh
```

The program runs in your terminal exactly as before. In addition it gets a card in the overlay that shows what it last printed, an alert when it looks like it is waiting for you, and a reply box:

- **Type a reply** in the overlay and press Enter; it is typed into the program.
- **Key buttons** (`y`, `n`, `⏎`, `1` `2` `3`, `↑` `↓`, `esc`, `^C`) cover yes/no prompts and menus.

How "waiting for you" is decided: the program has been silent for 10 seconds and its last line looks like a prompt (ends in `?`, `:`, `>`, contains `[y/n]`, and so on), or it has been silent for 30 seconds after a long run. This is a guess, so expect an occasional false alarm or miss.

An alias makes it automatic: `alias ollama='agent-inbox run ollama'`.

Limits: the program has to be started this way (a terminal that is already running cannot be attached), and agent-inbox only knows what the program prints, not what it is doing.

## Commands

```
agent-inbox status                 list sessions
agent-inbox watch                  live list in the terminal
agent-inbox toggle | show | hide   overlay visibility
agent-inbox view inbox|all|today   what the overlay lists
agent-inbox screen [next|<name>]   list screens, or move the overlay to the next / a named screen
agent-inbox history                today's tasks in the terminal
agent-inbox dismiss [id]           clear "needs you" on one session or all
agent-inbox approve <id>           approve a permission request
agent-inbox deny <id>              deny it
agent-inbox answer <id> <a>...     answer a question: one answer per part (an option or any text)
agent-inbox focus <id>             bring that session's window to the front
agent-inbox stop <id>              end a session
agent-inbox run <command...>       run any program under agent-inbox
agent-inbox type <id> <text>       type text + Enter into a program started with `run`
```

`<id>` is any unique prefix of the session id shown by `status`.

## Configuration

Optional. Create `~/.config/agent-inbox/config.json` with any of these keys (defaults shown), then run `systemctl --user restart agent-inbox`:

```json
{
  "position": "top-right",
  "screen": "active",
  "margin": 14,
  "width": 460,
  "font": "",
  "theme": "tokyo-night",
  "sound": true,
  "alert_delay": 4,
  "done_min_turn": 30,
  "usage_warn": 80,
  "keep_days": 14,
  "terminal_idle": 10,
  "copilot_gate": false,
  "copilot_wait": 30,
  "antigravity_gate": false,
  "antigravity_wait": 30
}
```

| Key | Meaning |
|---|---|
| `position` | `top-right`, `top-left`, `bottom-right` or `bottom-left` |
| `screen` | with several monitors: `active` opens the overlay on the screen you are working on, `primary` on the primary screen, or a screen name (see `agent-inbox screen`) pins it there |
| `margin`, `width` | distance from the screen edges and overlay width, in pixels |
| `font` | a font family; empty picks the first installed one from a list of common monospace fonts |
| `theme` | `tokyo-night`, `catppuccin`, `gruvbox` or `nord` |
| `sound` | play a short sound when the overlay pops up (needs `pw-play` or `paplay` and the freedesktop sound theme) |
| `alert_delay` | seconds a permission request or question must stay unanswered before the overlay pops up |
| `done_min_turn` | seconds a task must run before "finished" counts as needing you |
| `usage_warn` | percentage of the Claude 5-hour or weekly limit at which you get a warning |
| `keep_days` | how long the event log is kept |
| `terminal_idle` | seconds of silence before a program started with `agent-inbox run` counts as waiting at a prompt |
| `copilot_gate`, `copilot_wait` | see [Agent notes](#agent-notes) |
| `antigravity_gate`, `antigravity_wait` | see [Agent notes](#agent-notes) |

## Agent notes

Each agent exposes different things to outside tools, so what agent-inbox can do differs.

**Claude Code.** Full support. Claude Code shows its own prompt and the overlay card at the same time, and whichever you answer first wins. Plans can be read in the overlay but have to be approved in Claude Code. Plan usage needs a status line script, so the installer sets one up: a row at the bottom of each session such as `Fable 5.2 · ctx 34% · 5h 62% · 7d 41%`. If you already have a status line, it is left alone and usage is not shown. To remove ours, delete the `statusLine` entry from `~/.claude/settings.json`.

**OpenCode.** Full support for permissions and questions, through a plugin the installer puts in `~/.config/opencode/plugins/agent-inbox.js` (OpenCode has no hook scripts). As with Claude Code, OpenCode's own prompt and the overlay card are open at the same time and either can answer; `approve` allows the command once. The same plugin works with OpenCode 1.x and 2.x. On 1.x, restart open OpenCode windows after installing; 2.x picks it up by itself. OpenCode 2 runs every session in one shared background service rather than in its window, so for 2.x sessions `stop` and click-to-focus are not available, and a session whose window you closed stays in the `all` list until it has been idle for 6 hours.

**Codex CLI.** Codex holds back its own prompt while the overlay is asking. So the card appears immediately, and its button reads `answer there`, which hands the question back to Codex. If you do nothing, Codex's prompt appears after 60 seconds. Codex asks you to re-approve hooks (`/hooks`) whenever an agent-inbox update changes them.

**GitHub Copilot.** Inside VS Code, Copilot does not tell outside tools when it asks for permission ("Allow once"); it only announces that it is about to run a tool. To answer from the overlay anyway, set `"copilot_gate": true`. Every shell command Copilot wants to run, except plainly read-only ones (`ls`, `cat`, `grep`, `git status` ...), is then offered to the overlay first: `approve` runs it without VS Code asking, `deny` blocks it, and `answer there` or no answer within `copilot_wait` seconds leaves it to VS Code as before. The cost: commands VS Code would have run without asking also wait for you. File edits and Copilot's own questions cannot be answered from the overlay.

**Antigravity.** Same idea, with `"antigravity_gate": true` followed by `python3 install.py install` (the extra hook is only registered while the gate is on, because Antigravity requires an answer from it every time). Read-only commands, `answer there` and timeouts fall back to Antigravity's own prompt. Without the gate, Antigravity is watch only and a tool call is shown after it ran.

**In general.** Token counts and plan usage are Claude Code only. Sessions of other agents appear at their first event. `stop` is offered for agents that run as their own process, not for agents inside an editor. Questions with options can be answered from the overlay for Claude Code and OpenCode, and for anything started with `agent-inbox run`.

What has been tested how: Claude Code, OpenCode 1.19 and 2.3, Codex, the VS Code Copilot gate and the Antigravity gate on live sessions; `agent-inbox run` with interactive scripts.

## How it works

```
agent hooks ───────► hook script ─┐
OpenCode plugin ───► hook script ─┤
                                  ├─► unix socket ─► daemon ─► overlay
agent-inbox run ──────────────────┘
```

- **Hook script** (`hook/agent_inbox_hook.py`). Each agent calls it on events such as "prompt sent", "about to run a tool", "permission requested", "finished". It translates every agent's format into one common shape, passes it on and exits in about 15 ms. If agent-inbox is not running it does nothing, so your agents are never slowed down or blocked. The one event that waits is a permission request, so that the overlay can answer it.
- **OpenCode plugin** (`hook/opencode-plugin.js`). OpenCode has no hook scripts, so a plugin inside OpenCode turns its events into the same calls to the hook script, and passes answers from the overlay to OpenCode's reply API.
- **Daemon** (`daemon/`). Keeps one state per session, decides what needs your attention and when to show the overlay, and removes sessions whose process is gone. The state logic is a small, tested state machine (`daemon/state.py`).
- **Overlay** (`ui/`). A PySide6/QML window placed with layer-shell, which is what keeps it above other windows without stealing keyboard focus. It takes the keyboard only while you type in a reply box.
- **`agent-inbox run`** (`bin/agent-inbox`). Starts the program on a pseudo-terminal it owns, relays everything unchanged, and reports output and silence to the daemon.

## Privacy

Prompts, tool calls and each task's final message are written to `~/.local/share/agent-inbox/events.db` on your machine, so the overlay can show history and survive restarts. Entries older than `keep_days` are deleted. Input typed while the terminal hides it (passwords) is not recorded for programs started with `agent-inbox run`. Nothing is sent anywhere.

## Limits

- Wayland with layer-shell only. No GNOME, no X11.
- You can answer what an agent asks, but you cannot start a new prompt in an idle agent session from the overlay (except for programs started with `agent-inbox run`).
- Tested on one desktop (KDE Plasma 6). Reports from Hyprland, Sway and niri are welcome.

## Development

```
python3 tests/test_state.py
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software qml6 ui/Preview.qml -- preview.png
```

`ui/Preview.qml` renders every state with sample data, without touching your screen. `ui/Demo.qml` renders the demo GIF the same way; the commands are in its header.

## License

MIT
