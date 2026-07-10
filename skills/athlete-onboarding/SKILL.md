---
name: athlete-onboarding
description: Use when the athlete profile is empty or missing key facts. Runs the
  structured intake questionnaire and persists everything through the memory tools.
tools: [read_athlete, write_profile, upsert_goal, log_session]
---

# Athlete Onboarding

Collect the athlete's structured facts conversationally and persist them. Follow the
performance-coach skill's global rules (language, honesty, safety). Start by calling
`read_athlete` — never re-ask for facts already on file; only fill the gaps.

## Protocol

Ask ONE question at a time — this is a conversation, not a form. Adapt follow-ups to
the answers. If they decline a question, note it as unknown and move on — don't
insist more than once. Collect, in this order:

1. **Language** (en/fr/es) — first question, then switch to it immediately.
2. **Mode** — one-shot program (Mode A) or ongoing coaching (Mode B)? Explain the
   difference in one sentence each.
3. **Identity & biometrics** — name (optional), birth date, sex, height, weight.
4. **Sport & history** — main sport, discipline, competition level, years of
   structured training (maps to training_age: beginner < 2y structured, intermediate
   2-5y, advanced > 5y — state your mapping when you write it).
5. **Goal** — objective, target metric and value, deadline, priority. Also ask for a
   CURRENT benchmark (recent race time, recent 1RM) — the assessment needs it.
6. **Environment** — equipment (be concrete: barbell? rack? treadmill? track
   access?), sessions per week, minutes per session.
7. **Injuries & flags** — current or recent injuries, pain, medical constraints.
   Anything active: call `write_profile` immediately with the flag (don't wait for
   the batch), then continue, applying the red-flag rules from performance-coach.
8. **Preferences** — anything they hate/love, schedule quirks → profile notes.

## Persistence rules

- After steps 3-4, 6, and 8: call `write_profile` with the FULL updated profile
  (read first — it is a whole-document replace; omitted fields are dropped).
  Step 7 flags were already written immediately, per the protocol.
- After step 5: `upsert_goal` (id: short kebab slug, e.g. sub-45-10k).
- If they mention recent training sessions, offer to `log_session` them — history
  improves everything downstream.
- Timestamps are naive local wall-clock time; dates ISO (YYYY-MM-DD).

## Exit

Summarize what you stored (quote the profile back briefly), then route: new goal →
goal-assessment. Never skip assessment on the way to a program.
