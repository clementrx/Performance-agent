# Proactive follow-up (optional client-side reminders)

PerformanceAgent's MCP server is a **passive** stdio request/response process: it
answers when your agent calls it and cannot push a message on its own. So the coach
cannot literally text you "your check-in is overdue." What it *can* do is know what
is due the moment a conversation starts.

That knowledge is centralised in one tool: **`list_due_actions`**. The
`performance-coach` ritual calls it right after `get_time_context` and opens with the
top items, so the coach speaks first — you never have to remember to ask "is anything
overdue?"

## What `list_due_actions` surfaces

It reads the active program, calendar, session log, readiness log and response
profile, and returns a severity-ordered list of facts (never prose — the agent
renders the sentence in your language):

- an **overdue check-in** (past the program's `checkin_cadence_days`);
- an **A/B event within three weeks** (taper or peaking is about to start);
- **planned sessions missed** this week;
- **three or more recent training days with no readiness read** (the
  serious-competitor standard);
- an active goal whose **deadline has no dated calendar events** (incomplete
  calendar);
- a **response profile older than six weeks** (time to recalibrate);
- a **streak of red readiness days** (persistent under-recovery).

An all-green athlete gets an empty list, and the coach opens normally.

## Making the coach reach out on a schedule (optional)

Because the server is passive, "the coach messages me first" is a **client-side**
choice — no server change, nothing to configure in PerformanceAgent itself. If your
agent CLI can be launched non-interactively, schedule a run that opens a session with
a short prompt like `coach check`. The `performance-coach` ritual then fires
`list_due_actions` and the agent tells you what is due.

These are illustrative recipes; adapt them to your CLI and OS. All of this is
**optional** — the tool works the same whether you invoke it by hand or on a timer.

### macOS / Linux — cron

```cron
# 8am every day: open a coaching session that runs the follow-up check.
0 8 * * *  cd ~/athlete && your-agent-cli --prompt "coach check" >> ~/coach-check.log 2>&1
```

### macOS — launchd

A `launchd` agent (`~/Library/LaunchAgents/…plist`) with a `StartCalendarInterval`
key runs the same command at a fixed time and survives reboots.

### A scheduled agent run

If your agent supports scheduled or "routine" runs, point one at the same `coach
check` prompt on whatever cadence matches your `checkin_cadence_days` (e.g. weekly).

## Notes

- `list_due_actions` is deterministic given the athlete's files and the current date;
  running it more often never changes what is genuinely due, it only surfaces it
  sooner.
- Nothing here sends data anywhere. The recipes launch your existing local agent
  against your local athlete directory; the follow-up is computed on your machine.
