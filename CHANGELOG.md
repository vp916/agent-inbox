# Changelog

## 0.4.0

- Ready-made packages on the release page: Fedora (`.rpm`), Debian / Ubuntu (`.deb`), Arch (`.pkg.tar.zst`), plus a source tarball for any distribution. No git needed to install.
- OpenCode support (1.x and 2.x): sessions, permission prompts and questions (including multi-select and typed answers) can be seen and answered from the overlay; `stop` works on 1.x. Installed as an OpenCode plugin.
- Several monitors: the overlay opens on the screen you are working on (`screen` option), and `agent-inbox screen next` moves it to the next one. It used to always open on the primary screen.
- `stop` on a Codex session ends Codex itself. It used to end Codex's background app-server, which only disconnected the Codex window.
- Long project names are cut short on a card instead of running into the text next to them.
- The overlay also runs with older layer-shell-qt versions (Debian 13 ships 6.3).

## 0.3.0

agent-inbox is no longer Claude Code only.

- `agent-inbox run <command>`: any terminal program gets a card, a "waiting for input" alert, and a reply box with key buttons in the overlay.

- Codex CLI sessions are shown, with approve / deny from the overlay (hooks in `~/.codex/hooks.json`).
- GitHub Copilot sessions are shown, with approve / deny from the overlay.
- `copilot_gate`: approve or deny Copilot's shell commands from the overlay in VS Code, where Copilot sends no permission event.
- Close button in the overlay header.
- Antigravity sessions are shown; `antigravity_gate` adds approve / deny for its shell commands.
- Each card is tagged with its agent and where it runs.
- The hook script translates every agent's events into one common shape.

## 0.2.0

- Click a session to jump to its terminal window (KWin, Hyprland, Sway; Konsole also switches tab).
- Answer questions with your own typed reply, and answer multi-part and multi-select questions from the overlay.
- Sessions that were already open before install are listed straight away.
- `today` tab and `agent-inbox history`: today's turns across all projects.
- Plan usage (5-hour and 7-day) in the overlay and in a status line, with a warning at a configurable threshold.
- Context size and output tokens on each card.
- Themes: Tokyo Night, Catppuccin, Gruvbox, Nord.
- Sound when the overlay pops up.
- Plan cards show the plan text.
- The list scrolls when it is long.
- PKGBUILD for Arch.

## 0.1.0

- First release: hooks, daemon, overlay, approve / deny and option picking from the overlay, config file.
