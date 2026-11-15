#!/usr/bin/python3
"""Agent Monitor daemon: receives hook events, tracks sessions, serves the overlay and amctl.

One unix socket, newline-delimited JSON. The first line of a connection sets its role:
  {"kind":"event","event":{...}}         from the hook script
  {"kind":"ask","event":{...}}           a PermissionRequest; the hook waits for {"decision":...} or EOF
  {"kind":"cmd","cmd":"toggle",...}      one command, one snapshot reply
  {"kind":"subscribe","role":"overlay"}  snapshot on every change; further lines are commands
"""
import asyncio
import json
import os
import signal
import sqlite3
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state import BLOCKED, Session, apply  # noqa: E402

SOCK = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}") + "/agent-monitor.sock"
DATA = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "agent-monitor"
ALERT_DELAY = 4  # s a permission/question must stay unanswered before the overlay pops up
KEEP_DAYS = 14  # event log retention
STALE_HOURS = 6  # drop sessions with unknown pid after this long without events
LABEL = {
    "permission": "needs permission",
    "question": "has a question",
    "plan": "plan ready for review",
    "done": "finished",
    "error": "stopped on an error",
}


def is_claude(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return b"claude" in f.read()
    except OSError:
        return False


class Daemon:
    def __init__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DATA / "events.db", isolation_level=None)
        self.db.executescript(
            """create table if not exists events(ts real, session text, name text, data text);
               create index if not exists events_session on events(session, ts);
               create table if not exists sessions(id text primary key, data text);"""
        )
        self.db.execute("delete from events where ts < ?", (time.time() - KEEP_DAYS * 86400,))
        self.sessions = {}
        for (data,) in self.db.execute("select data from sessions"):
            s = Session.load(json.loads(data))
            self.sessions[s.id] = s
        self.subs = {}  # writer -> role
        self.pending = {}  # session id -> {"fut", "ts", "input"}: a hook waiting for an answer
        self.ui = {"visible": False, "view": "inbox", "auto": False}

    # ---- state out
    def snapshot(self):
        ss = sorted(self.sessions.values(), key=lambda s: (s.attention is None, -s.last))
        return {"type": "state", "now": time.time(), "ui": self.ui, "sessions": [asdict(s) for s in ss]}

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
        self.db.execute("insert into events values(?, ?, ?, ?)", (now, sid, name, json.dumps(ev)))
        if s.ended:
            self.drop(s)
        else:
            self.save(s)
            if kind:
                delay = ALERT_DELAY if kind in BLOCKED else 0
                asyncio.get_running_loop().call_later(delay, self.alert, sid, s.attention["ts"])
        self.settle()
        self.broadcast()

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
        self.broadcast()
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
        elif c == "view" and m.get("view") in ("inbox", "all"):
            self.ui["view"] = m["view"]
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
                q = (p["input"].get("questions") or [{}])[0]
                want = (m.get("label") or "\0").rstrip("…")  # the overlay may send a shortened label
                label = next((o["label"] for o in q.get("options") or [] if o.get("label", "").startswith(want)), None)
                if label is None:
                    return {"type": "error", "error": "no such option"}
                decision = {"behavior": "allow", "updatedInput": {**p["input"], "answers": {q["question"]: label}}}
            p["fut"].set_result(decision)
            s.attention = None
            self.save(s)
        elif c == "stop":
            if not (s and s.pid and is_claude(s.pid)):
                return {"type": "error", "error": "session process not known"}
            os.kill(s.pid, signal.SIGTERM)
        elif c != "status":
            return {"type": "error", "error": f"unknown command '{c}'"}
        self.settle()
        self.broadcast()
        return self.snapshot()

    # ---- plumbing
    async def handle(self, r, w):
        try:
            m = json.loads(await r.readline() or b"{}")
            kind = m.get("kind")
            if kind == "event":
                self.on_event(m.get("event") or {})
            elif kind == "ask":
                await self.ask(m.get("event") or {}, r, w)
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
            if gone:
                self.settle()
                self.broadcast()


async def notify(title, body):
    try:
        await asyncio.create_subprocess_exec("notify-send", "-a", "Agent Monitor", title, body)
    except OSError:
        pass


async def main():
    os.umask(0o077)
    try:
        _, w = await asyncio.open_unix_connection(SOCK)
        w.close()
        sys.exit("agent-monitor daemon already running")
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
