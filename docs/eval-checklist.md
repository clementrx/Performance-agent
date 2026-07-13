# Manual skill-level evaluation checklist

The automated `tests/e2e_sim/` suite proves the engine + store compose correctly
without an LLM. This checklist is its counterpart: a short, manual, **skill-level**
script to run against a live model before a release, exercising the coaching skills
(`performance-coach`, `athlete-onboarding`, `program-planning`,
`program-optimization`, `training-checkin`, `session-day`, `program-adaptation`)
end to end.

Run each persona in a fresh athlete directory (`PERFORMANCE_AGENT_HOME` pointing at
an empty temp dir). Judge the behaviour, not the exact words. A persona passes when
every "expect" line holds and no number reaches you that the engine did not compute.

---

## P1 — Endurance runner (10K)

**Setup.** Onboard a runner: goal "10K under 45:00" ~14 weeks out, three run days +
two S&C slots, one dated A race on the calendar, daily readiness expected.

**Expect:**
- Onboarding collects the dated race and the weekly training days; an athlete with
  no dated event is asked to confirm `open_ended` explicitly.
- `program-planning` calls `build_season_plan`, quotes each segment's rationale, and
  places a taper immediately before the race.
- The saved program is a structured version with per-session fallbacks and a test
  milestone; `program-review` passes (citations, sequencing, weekly set sums).
- After ~8 weeks of logs, `training-checkin` recomputes the response profile and
  narrates measured vs. prior rate honestly (small-n caveat when thin).

## P2 — Amateur footballer (external load)

**Setup.** Onboard a footballer: 3 club practices + 1 weekend match as recurring
constraints, 2 gym slots, an in-season "stay fit" goal. Log a normal week, then a
fixture pile-up week.

**Expect:**
- The check-in asks "anything I didn't program?" and logs club/match as
  `source="external"`; weekly narration states the external share of total load.
- `program-optimization` sizes gym volume within the external-load budget and keeps
  lifting away from match +/-1 day (no `block` sequencing violation).
- After the pile-up week the coach proactively surfaces a deload recommendation with
  its drivers (strain/monotony/TSB) — before fatigue is self-reported at 8/10.
- Opening a session after a silent week surfaces the overdue check-in, the missed
  sessions and the readiness gap without being asked (`list_due_actions`).

## P3 — Hyrox hybrid (two races, a change, a break)

**Setup.** Onboard a hybrid athlete: one A race + one B race, four sessions/week.
Mid-block, move the A race two weeks later. Later, report a 2-week illness break.

**Expect:**
- The season has a full taper before the A race and only a mini-taper / train-through
  for the B race.
- Moving the A race routes to `program-adaptation`, which replans the affected
  segments and saves a new program version whose reason cites the date change; the
  taper still lands before the new date.
- The illness break triggers the return-to-load branch: the coach requires
  professional-clearance confirmation, then builds a graded ramp
  (`return_to_load` phase) and never programs through pain.
- Every program version created along the way carries an explicit reason.

---

## Cross-cutting checks (all personas)

- No fabricated citations: every cited id resolves via `check_citations`; a PDF
  render hard-fails on an unknown reference.
- Safety precedence: a reported pain/injury stops loading that pattern and refers
  out — the coach never diagnoses or programs through an active injury.
- Honesty: no promised outcome the feasibility engine cannot defend; assumptions are
  stated; thin data is labelled, never smoothed into a confident number.
