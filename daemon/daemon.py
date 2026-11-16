#!/usr/bin/python3
"""agent-inbox daemon: receives hook events, tracks sessions, serves the overlay and agent-inbox.

One unix socket, newline-delimited JSON. The first line of a connection sets its role:
  {"kind":"event","event":{...}}         from the hook script
  {"kind":"status","status":{...}}       from the status line script: plan usage and context share
  {"kind":"terminal","session":id}       `agent-inbox run`: further lines are events; we write {"data":...} to type into it
  {"kind":"ask","event":{...}}           a PermissionRequest; the hook waits for {"decision":...} or EOF
  {"kind":"cmd","cmd":"toggle",...}      one command, one snapshot reply
  {"kind":"subscribe","role":"overlay"}  snapshot on every change; further lines are commands
"""
import asyncio
import json
import os
import shutil
import signal
import sqlite3
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state  # noqa: E402
from focus import focus  # noqa: E402
from state import BLOCKED, Session, apply, base, short  # noqa: E402

SOCK = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}") + "/agent-inbox.sock"
DATA = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "agent-inbox"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "agent-inbox/config.json"
DEFAULTS = {
    "position": "top-right",  # top-right | top-left | bottom-right | bottom-left
    "screen": "active",  # active (the one you are working on) | primary | a screen name, see `agent-inbox screen`
    "margin": 14,  # px from the screen edges
    "width": 460,  # px
    "font": "",  # font family; empty picks the first installed monospace from a built-in list
    "alert_delay": 4,  # s a permission/question must stay unanswered before the overlay pops up
    "done_min_turn": 30,  # s a turn must run before "finished" counts as needing you
    "keep_days": 14,  # event log retention
    "sound": True,  # play a short sound when the overlay pops up
    "usage_warn": 80,  # % of the 5-hour or 7-day plan limit that triggers a warning
    "terminal_idle": 10,  # s of silence before a program under `agent-inbox run` counts as waiting at a prompt
    "copilot_gate": False,  # offer Copilot's shell commands to the overlay before VS Code asks
    "copilot_wait": 30,  # s the overlay gets to answer such a command
    "antigravity_gate": False,  # the same for Antigravity's run_command (needs install.py install to apply)
    "antigravity_wait": 30,
    "theme": "tokyo-night",  # tokyo-night | catppuccin | gruvbox | nord
}
STALE_HOURS = 6  # drop sessions with unknown pid after this long without events
LABEL = {
    "permission": "needs permission",
    "question": "has a question",
    "plan": "plan ready for review",
    "done": "finished",
    "error": "stopped on an error",
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        user = json.loads(CONFIG.read_text())
        cfg.update({k: v for k, v in user.items() if k in DEFAULTS and type(v) is type(DEFAULTS[k])})
    except (OSError, ValueError, AttributeError):
        pass
    return cfg


def is_agent(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read()
        return b"claude" in cmd or b"codex" in cmd or b"opencode" in cmd
    except OSError:
        return False


class Daemon:
    def __init__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        self.cfg = load_config()
        state.DONE_MIN_TURN = self.cfg["done_min_turn"]
        self.db = sqlite3.connect(DATA / "events.db", isolation_level=None)
        self.db.executescript(
            """create table if not exists events(ts real, session text, name text, data text);
               create index if not exists events_session on events(session, ts);
               create table if not exists sessions(id text primary key, data text);"""
        )
        self.db.execute("delete from events where ts < ?", (time.time() - self.cfg["keep_days"] * 86400,))
        self.sessions = {}
        for (data,) in self.db.execute("select data from sessions"):
            s = Session.load(json.loads(data))
            self.sessions[s.id] = s
        self.subs = {}  # writer -> role
        self.usage = {}  # session id -> {"pos", "out", "ctx", "at"}: transcript reading state
        self.terms = {}  # session id -> writer of its `agent-inbox run` wrapper
        self.pending = {}  # session id -> {"fut", "ts", "input"}: a hook waiting for an answer
        # view: inbox | all | today. screen: where the overlay opens; screens / on: reported by the overlay
        self.ui = {"visible": False, "view": "inbox", "auto": False, "screen": self.cfg["screen"], "screens": [], "on": ""}
        self.limits = {}  # "five_hour" / "seven_day" -> {"pct", "resets_at"}, from the status line
        self.warned = {}  # window -> resets_at already warned about
        self.history = []  # today's turns, only kept fresh while the "today" view is open

    # ---- state out
    def snapshot(self):
        ss = sorted(self.sessions.values(), key=lambda s: (s.attention is None, -s.last))
        look = {k: self.cfg[k] for k in ("position", "margin", "width", "font", "theme")}
        return {
            "type": "state", "now": time.time(), "ui": self.ui, "config": look,
            "sessions": [asdict(s) for s in ss],
            "history": self.history if self.ui["view"] == "today" else [],
            "limits": {**{k: w for k, w in self.limits.items() if w["resets_at"] > time.time()}, "warn": self.cfg["usage_warn"]},
        }  # fmt: skip

    def load_history(self):
        """Today's turns, newest first: one entry per prompt, closed by the Stop that ended it."""
        midnight = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        turns, running = [], {}
        rows = self.db.execute(
            "select ts, session, name, data from events where ts >= ? "
            "and name in ('UserPromptSubmit', 'PreToolUse', 'Stop') order by ts",
            (midnight,),
        )
        for ts, sid, name, data in rows:
            if name == "UserPromptSubmit":
                ev = json.loads(data)
                prev = running.get(sid)
                if prev and not prev["tools"]:
                    turns.remove(prev)  # replaced before it did anything (queued or corrected prompt)
                elif prev:
                    prev["end"], prev["result"] = ts, "(interrupted by the next prompt)"
                turn = running[sid] = {
                    "start": ts, "end": None, "session": sid, "tools": 0, "result": "",
                    "project": base(ev.get("_project_dir") or ev.get("cwd")),
                    "prompt": short(ev.get("prompt"), 120),
                }  # fmt: skip
                turns.append(turn)
            elif sid in running:
                if name == "PreToolUse":
                    running[sid]["tools"] += 1
                else:
                    turn = running.pop(sid)
                    turn["end"] = ts
                    turn["result"] = short(json.loads(data).get("last_assistant_message"), 200)
        for turn in running.values():  # no Stop seen: still going, or the session was closed mid-turn
            s = self.sessions.get(turn["session"])
            turn["live"] = bool(s and s.state == "working")
        self.history = turns[::-1][:60]

    def broadcast(self):
        line = (json.dumps(self.snapshot()) + "\n").encode()
        for w in list(self.subs):
            if w.is_closing():
                self.subs.pop(w, None)
            else:
                w.write(line)

    def save(self, s):
        self.db.execute("insert or replace into sessions values(?, ?)", (s.id, json.dumps(asdict(s))))

    def drop(self, s):
        self.sessions.pop(s.id, None)
        self.db.execute("delete from sessions where id = ?", (s.id,))

    def settle(self):
        """Run after every change: let go of hooks whose question is no longer open, and
        hide an overlay that popped up by itself once nothing needs the user."""
        for sid, p in list(self.pending.items()):
            s = self.sessions.get(sid)
            if not (s and s.attention and s.attention["ts"] == p["ts"]) and not p["fut"].done():
                p["fut"].set_result(None)
        if self.ui["auto"] and not any(s.attention for s in self.sessions.values()):
            self.ui.update(visible=False, auto=False)

    # ---- events in
    def on_event(self, ev):
        sid = ev.get("session_id")
        name = ev.get("hook_event_name", "")
        if not sid:
            return
        now = time.time()
        s = self.sessions.get(sid)
        if not s:
            if name == "SessionEnd":
                return
            s = self.sessions[sid] = Session(id=sid, since=now)
        kind = apply(s, ev, now)
        if s.pid:  # it may have been listed by discover() until now
            self.sessions.pop(f"pid-{s.pid}", None)
        if s.agent == "claude" and name in ("Stop", "PostToolUse", "SessionStart") and ev.get("transcript_path"):
            self.read_usage(s, ev["transcript_path"], now, force=name != "PostToolUse")
        self.db.execute("insert into events values(?, ?, ?, ?)", (now, sid, name, json.dumps(ev)))
        if self.ui["view"] == "today" and name in ("UserPromptSubmit", "Stop"):
            self.load_history()
        if s.ended:
            self.drop(s)
        else:
            self.save(s)
            if kind:
                delay = self.cfg["alert_delay"] if kind in BLOCKED else 0
                asyncio.get_running_loop().call_later(delay, self.alert, sid, s.attention["ts"])
        self.settle()
        self.broadcast()

    def on_status(self, st):
        """Plan usage is account-wide, so the latest report from any session wins."""
        before = json.dumps(self.limits)
        for key, name in (("five_hour", "5-hour"), ("seven_day", "7-day")):
            w = (st.get("rate_limits") or {}).get(key)
            if not isinstance(w, dict) or w.get("used_percentage") is None:
                continue
            pct, resets = round(float(w["used_percentage"])), w.get("resets_at") or 0
            self.limits[key] = {"pct": pct, "resets_at": resets}
            if pct >= self.cfg["usage_warn"] and self.warned.get(key) != resets:
                self.warned[key] = resets
                when = time.strftime("%a %H:%M", time.localtime(resets))
                asyncio.ensure_future(notify(f"Claude usage: {name} limit at {pct}%", f"Resets {when}"))
                if self.cfg["sound"]:
                    asyncio.ensure_future(play("dialog-warning"))
        s = self.sessions.get(st.get("session_id"))
        ctx = st.get("ctx_pct")
        changed = json.dumps(self.limits) != before
        if s and ctx is not None and s.ctx_pct != round(ctx):
            s.ctx_pct, changed = round(ctx), True
        if changed:
            self.broadcast()

    def read_usage(self, s, path, now, force):
        """Token counts from the session transcript, read incrementally."""
        u = self.usage.setdefault(s.id, {"pos": 0, "out": {}, "ctx": 0, "at": 0})
        if not force and now - u["at"] < 3:
            return
        u["at"] = now
        try:
            with open(path, "rb") as f:
                f.seek(u["pos"])
                for line in f:
                    if not line.endswith(b"\n"):
                        break  # still being written
                    u["pos"] += len(line)
                    if b'"usage"' not in line:
                        continue
                    o = json.loads(line)
                    m = o.get("message") or {}
                    use = m.get("usage")
                    if o.get("type") != "assistant" or o.get("isSidechain") or not isinstance(use, dict):
                        continue
                    u["out"][m.get("id")] = use.get("output_tokens") or 0  # one message can span several lines
                    u["ctx"] = sum(use.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        except (OSError, ValueError):
            return
        s.ctx_tokens, s.out_tokens = u["ctx"], sum(u["out"].values())

    async def ask(self, ev, r, w):
        """A PermissionRequest hook is waiting. Hold it until the overlay answers, the
        question is settled some other way (terminal, dismiss), or the hook goes away."""
        self.on_event(ev)
        s = self.sessions.get(ev.get("session_id"))
        if not s or not s.attention or s.attention["kind"] not in ("permission", "question"):
            return
        fut = asyncio.get_running_loop().create_future()
        p = self.pending[s.id] = {"fut": fut, "ts": s.attention["ts"], "input": ev.get("tool_input") or {}}
        s.attention["answerable"] = True
        if s.agent not in ("claude", "opencode"):  # its own prompt is held back until we answer, so show the card now
            self.alert(s.id, p["ts"])
        self.broadcast()
        gone = asyncio.ensure_future(r.read(1))
        try:
            await asyncio.wait({fut, gone}, return_when=asyncio.FIRST_COMPLETED)
            if fut.done() and fut.result():
                w.write((json.dumps({"decision": fut.result()}) + "\n").encode())
                await w.drain()
        finally:
            gone.cancel()
            if self.pending.get(s.id) is p:
                del self.pending[s.id]
            if s.attention and s.attention["ts"] == p["ts"]:
                s.attention.pop("answerable", None)
                self.broadcast()

    def alert(self, sid, ts):
        s = self.sessions.get(sid)
        if not s or not s.attention or s.attention["ts"] != ts:
            return  # answered or dismissed in the meantime
        if not self.ui["visible"]:
            self.ui.update(visible=True, auto=True)
        if self.ui["view"] == "today":
            self.ui["view"] = "inbox"
        self.broadcast()
        if self.cfg["sound"]:
            asyncio.ensure_future(play("dialog-error" if s.attention["kind"] == "error" else "message-new-instant"))
        if "overlay" not in self.subs.values():
            asyncio.ensure_future(notify(f"{s.project}: {LABEL[s.attention['kind']]}", s.attention["text"]))

    # ---- commands in
    def find(self, key):
        hits = [s for s in self.sessions.values() if key and s.id.startswith(key)]
        return hits[0] if len(hits) == 1 else None

    def command(self, m):
        c, key = m.get("cmd"), m.get("session", "")
        s = self.find(key)
        if key and not s:
            return {"type": "error", "error": f"no single session matches '{key}'"}
        if c == "toggle":
            self.ui.update(visible=not self.ui["visible"], auto=False)
        elif c in ("show", "hide"):
            self.ui.update(visible=c == "show", auto=False)
        elif c == "view" and m.get("view") in ("inbox", "all", "today"):
            self.ui["view"] = m["view"]
            if m["view"] == "today":
                self.load_history()
        elif c == "screen":
            err = self.place(m.get("screen") or "")
            if err:
                return {"type": "error", "error": err}
        elif c == "screens":  # from the overlay: the screens it sees and the one it is on
            names = m.get("names")
            self.ui.update(screens=[n for n in names if isinstance(n, str)] if isinstance(names, list) else [],
                           on=str(m.get("on") or ""))  # fmt: skip
        elif c == "history":
            self.load_history()
            return {"type": "history", "turns": self.history}
        elif c == "dismiss":
            for x in [s] if s else list(self.sessions.values()):
                x.attention, x.quiet = None, True
                self.save(x)
        elif c in ("approve", "deny", "answer"):
            p = self.pending.get(s.id) if s else None
            if not p or p["fut"].done():
                return {"type": "error", "error": "nothing to answer for that session"}
            if c == "deny":
                decision = {"behavior": "deny", "message": "Denied by the user from the agent-inbox overlay"}
            elif c == "approve":
                decision = {"behavior": "allow"}
            else:
                qs = p["input"].get("questions") or []
                given = m.get("answers") or []
                if len(given) != len(qs) or not all(isinstance(a, str) and a.strip() for a in given):
                    return {"type": "error", "error": f"need one answer for each of the {len(qs)} question(s)"}
                answers = {}
                for q, a in zip(qs, given):
                    a = a.strip()
                    # an option label, possibly shortened or just a prefix; anything else is free text
                    full = [o["label"] for o in q.get("options") or [] if o.get("label", "").startswith(a.rstrip("…"))]
                    answers[q["question"]] = full[0] if len(full) == 1 else a
                decision = {"behavior": "allow", "updatedInput": {**p["input"], "answers": answers}}
            p["fut"].set_result(decision)
            s.attention = None
            self.save(s)
        elif c == "type":
            w = self.terms.get(s.id) if s else None
            if not w or w.is_closing():
                return {"type": "error", "error": "not a program started with `agent-inbox run`"}
            w.write((json.dumps({"data": str(m.get("text") or "")}) + "\n").encode())
        elif c == "focus":
            if not s:
                return {"type": "error", "error": "which session?"}
            if not focus(([s.pid] if s.pid else []) + s.chain, s.project):
                return {"type": "error", "error": "no supported compositor found (KWin, Hyprland, Sway)"}
        elif c == "stop":
            if not (s and s.pid and is_agent(s.pid)):
                return {"type": "error", "error": "session process not known"}
            os.kill(s.pid, signal.SIGTERM)
        elif c != "status":
            return {"type": "error", "error": f"unknown command '{c}'"}
        self.settle()
        self.broadcast()
        return self.snapshot()

    def place(self, want):
        """Choose where the overlay opens: active | primary | next | a screen name."""
        names = self.ui["screens"]
        if want == "next":
            if len(names) < 2:
                return "there is only one screen"
            on = self.ui["on"]
            want = names[(names.index(on) + 1) % len(names)] if on in names else names[0]
        if want not in ("", "active", "primary") and names and want not in names:
            return f"no screen named '{want}'. Screens: {', '.join(names)}"
        if want:
            self.ui.update(screen=want, visible=True, auto=False)  # show it, so you see where it went
        return None

    # ---- plumbing
    async def handle(self, r, w):
        try:
            m = json.loads(await r.readline() or b"{}")
            kind = m.get("kind")
            if kind == "event":
                self.on_event(m.get("event") or {})
            elif kind == "status":
                self.on_status(m.get("status") or {})
            elif kind == "ask":
                await self.ask(m.get("event") or {}, r, w)
            elif kind == "terminal":
                sid = str(m.get("session"))
                self.terms[sid] = w
                try:
                    while line := await r.readline():
                        self.on_event(json.loads(line))
                finally:
                    self.terms.pop(sid, None)
                    self.on_event({"hook_event_name": "SessionEnd", "session_id": sid})
            elif kind == "cmd":
                w.write((json.dumps(self.command(m)) + "\n").encode())
                await w.drain()
            elif kind == "subscribe":
                self.subs[w] = m.get("role", "")
                w.write((json.dumps(self.snapshot()) + "\n").encode())
                while line := await r.readline():
                    self.command(json.loads(line))
        except (ValueError, ConnectionError):
            pass
        finally:
            self.subs.pop(w, None)
            w.close()

    def discover(self):
        """List Claude Code processes that have not sent an event yet (idle since before the
        hooks were installed, or since the daemon started). Their session id is unknown, so
        they get a placeholder that the first real event replaces."""
        known = {s.pid for s in self.sessions.values()}
        found = False
        for entry in os.listdir("/proc"):
            if not entry.isdigit() or int(entry) in known:
                continue
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as f:
                    argv = f.read().split(b"\0")
                helpers = (b"-p", b"--print", b"--chrome-native-host")  # not interactive sessions
                if os.path.basename(argv[0]) != b"claude" or any(a in helpers for a in argv):
                    continue
                cwd = os.readlink(f"/proc/{entry}/cwd")
            except OSError:
                continue
            now = time.time()
            self.sessions[f"pid-{entry}"] = Session(
                id=f"pid-{entry}", pid=int(entry), cwd=cwd, project=os.path.basename(cwd) or "?",
                action="No activity seen yet", since=now, last=now,
            )  # fmt: skip
            found = True
        return found

    async def housekeeping(self):
        while True:
            await asyncio.sleep(3)
            now = time.time()
            gone = [
                s
                for s in self.sessions.values()
                if (s.pid and not os.path.exists(f"/proc/{s.pid}"))
                or (not s.pid and now - s.last > STALE_HOURS * 3600)
            ]
            for s in gone:
                self.drop(s)
            if self.discover() or gone:
                self.settle()
                self.broadcast()


async def play(name):
    path = f"/usr/share/sounds/freedesktop/stereo/{name}.oga"
    tool = shutil.which("pw-play") or shutil.which("paplay")
    if tool and os.path.exists(path):
        try:
            await asyncio.create_subprocess_exec(tool, path)
        except OSError:
            pass


async def notify(title, body):
    try:
        await asyncio.create_subprocess_exec("notify-send", "-a", "agent-inbox", title, body)
    except OSError:
        pass


async def main():
    os.umask(0o077)
    try:
        _, w = await asyncio.open_unix_connection(SOCK)
        w.close()
        sys.exit("agent-inbox daemon already running")
    except OSError:
        if os.path.exists(SOCK):
            os.unlink(SOCK)
    d = Daemon()
    server = await asyncio.start_unix_server(d.handle, SOCK, limit=4 << 20)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    chores = asyncio.ensure_future(d.housekeeping())
    await stop.wait()
    chores.cancel()
    server.close()
    if os.path.exists(SOCK):  # newer Pythons remove it on close
        os.unlink(SOCK)


if __name__ == "__main__":
    asyncio.run(main())
