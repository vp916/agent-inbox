// agent-inbox plugin for OpenCode: reports what this OpenCode's sessions are doing to the
// agent-inbox daemon, and lets the overlay answer OpenCode's permission prompts and questions.
//
// install.py copies this file to ~/.config/opencode/plugins/agent-inbox.js and fills in the
// two paths below. Every event goes through the same hook script the other agents use
// (agent_inbox_hook.py opencode), already translated into its common event shape.
//
// OpenCode shows its own prompt at the same time, so either side can answer: an answer from
// the overlay is sent through OpenCode's reply API, and an answer in OpenCode clears the card.
import { spawn } from "child_process"

const PYTHON = "__PYTHON__"
const HOOK = "__HOOK__"

const TOOLS = {
  bash: "Bash", read: "Read", edit: "Edit", write: "Write", grep: "Grep", glob: "Glob",
  webfetch: "WebFetch", websearch: "WebSearch", task: "Agent", question: "AskUserQuestion", todowrite: "TodoWrite",
}
const PERMISSIONS = { bash: "Bash", edit: "Edit", read: "Read", webfetch: "WebFetch", websearch: "WebSearch", task: "Agent" }

const questions = (qs) =>
  (qs || []).map((q) => ({ question: q.question, header: q.header, options: q.options || [], multiSelect: !!q.multiple }))

function toolInput(tool, input) {
  input = input || {}
  switch (tool) {
    case "bash": return { command: input.command, description: input.description }
    case "read": case "edit": case "write": return { file_path: input.filePath }
    case "grep": case "glob": return { pattern: input.pattern }
    case "webfetch": return { url: input.url }
    case "websearch": return { query: input.query }
    case "task": return { description: input.description }
    case "question": return { questions: questions(input.questions) }
    default: return input
  }
}

function permissionInput(req) {
  const meta = req.metadata || {}
  const what = (req.patterns || []).join(", ")
  switch (req.permission) {
    case "bash": return ["Bash", { command: meta.command || what }]
    case "edit": case "read": return [PERMISSIONS[req.permission], { file_path: meta.filepath || meta.filePath || what }]
    case "webfetch": return ["WebFetch", { url: meta.url || what }]
    default: return ["Bash", { command: `${req.permission}${what ? ": " + what : ""}` }]
  }
}

// one answer list per question, each a list of option labels or the typed text
function answersFor(qs, given) {
  return (qs || []).map((q) => {
    const a = String(given[q.question] ?? "")
    const labels = (q.options || []).map((o) => o.label)
    const parts = a.split(", ")
    return q.multiple && parts.every((p) => labels.includes(p)) ? parts : [a]
  })
}

// Run the hook with one event. With `wait`, return the decision it prints (or null).
function hook(ev, wait) {
  return new Promise((resolve) => {
    let out = ""
    try {
      const p = spawn(PYTHON, ["-I", "-S", HOOK, "opencode"], { stdio: ["pipe", wait ? "pipe" : "ignore", "ignore"] })
      if (wait) p.stdout.on("data", (d) => (out += d))
      p.on("error", () => resolve(null))
      p.on("close", () => {
        try {
          resolve(out.trim() ? JSON.parse(out).decision || null : null)
        } catch {
          resolve(null)
        }
      })
      p.stdin.on("error", () => {})
      p.stdin.end(JSON.stringify(ev))
    } catch {
      resolve(null)
    }
  })
}

export const AgentInbox = async ({ client, directory }) => {
  let queue = Promise.resolve() // events reach the daemon in the order they happened
  const report = (ev) => (queue = queue.then(() => hook(ev, false)))

  const parent = new Map() // subagent session -> the session that started it
  const dirs = new Map() // session -> its directory
  const roles = new Map() // message -> "user" | "assistant"
  const said = new Map() // session -> the assistant's latest text
  const models = new Map() // session -> model
  const prompted = new Set() // user messages already reported
  const toolState = new Map() // tool call -> last reported status

  const top = (sid) => parent.get(sid) || sid
  const base = (sid, name, extra) => ({
    session_id: top(sid),
    hook_event_name: name,
    cwd: dirs.get(top(sid)) || directory,
    model: models.get(top(sid)),
    ...(parent.has(sid) ? { agent_id: sid } : {}),
    ...extra,
  })

  function post(url, requestID, body) {
    const c = client && client._client
    if (!c) return
    c.post({ url, path: { requestID }, body, query: { directory } }).catch(() => {})
  }

  async function ask(sid, req, ev, isQuestion) {
    await queue
    const decision = await hook(base(sid, "PermissionRequest", ev), true)
    if (!decision) return // answered in OpenCode, dismissed, or no overlay
    if (!isQuestion) {
      const allow = decision.behavior === "allow"
      post("/permission/{requestID}/reply", req.id, allow ? { reply: "once" } : { reply: "reject", message: decision.message })
    } else if (decision.behavior !== "allow") {
      post("/question/{requestID}/reject", req.id)
    } else {
      post("/question/{requestID}/reply", req.id, { answers: answersFor(req.questions, (decision.updatedInput || {}).answers || {}) })
    }
  }

  return {
    event: async ({ event }) => {
      try {
        const p = event.properties || {}
        switch (event.type) {
          case "session.created":
          case "session.updated": {
            const info = p.info || {}
            if (info.parentID) parent.set(info.id, info.parentID)
            if (info.directory) dirs.set(info.id, info.directory)
            break
          }
          case "message.updated": {
            const m = p.info || {}
            roles.set(m.id, m.role)
            if (m.role === "assistant" && m.modelID) models.set(top(m.sessionID), m.modelID)
            break
          }
          case "message.part.updated": {
            const part = p.part || {}
            const sid = part.sessionID
            if (part.type === "text" && !part.synthetic) {
              if (roles.get(part.messageID) === "user") {
                if (!prompted.has(part.messageID) && !parent.has(sid)) {
                  prompted.add(part.messageID)
                  report(base(sid, "UserPromptSubmit", { prompt: part.text }))
                }
              } else if (part.text) {
                said.set(top(sid), part.text)
              }
            } else if (part.type === "tool") {
              const status = (part.state || {}).status
              if (status === "pending" || toolState.get(part.callID) === status) break
              const ev = { tool_name: TOOLS[part.tool] || part.tool, tool_input: toolInput(part.tool, (part.state || {}).input) }
              if (status === "running") {
                toolState.set(part.callID, status)
                report(base(sid, "PreToolUse", ev))
              } else {
                toolState.delete(part.callID)
                report(base(sid, status === "error" ? "PostToolUseFailure" : "PostToolUse", ev))
              }
            }
            break
          }
          case "permission.asked": {
            const [tool_name, tool_input] = permissionInput(p)
            ask(p.sessionID, p, { tool_name, tool_input }, false)
            break
          }
          case "question.asked":
            ask(p.sessionID, p, { tool_name: "AskUserQuestion", tool_input: { questions: questions(p.questions) } }, true)
            break
          case "permission.replied":
          case "question.replied":
          case "question.rejected": // answered (in OpenCode or from the overlay): the agent moves on
            report(base(p.sessionID, "PostToolUse", { tool_name: "Answered" }))
            break
          case "session.idle":
            if (!parent.has(p.sessionID)) report(base(p.sessionID, "Stop", { last_assistant_message: said.get(p.sessionID) || "" }))
            break
          case "session.error": {
            const err = p.error || {}
            if (!p.sessionID || parent.has(p.sessionID) || err.name === "MessageAbortedError") break
            report(base(p.sessionID, "StopFailure", { error: (err.data && err.data.message) || err.name || "Error" }))
            break
          }
          case "session.deleted": {
            const info = p.info || {}
            if (!info.parentID) report(base(info.id, "SessionEnd", {}))
            break
          }
        }
      } catch {
        // never disturb OpenCode
      }
    },
  }
}
