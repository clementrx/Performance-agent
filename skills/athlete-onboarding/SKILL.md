---
name: athlete-onboarding
description: Use when the athlete profile is empty or missing key facts. Runs the
  structured intake questionnaire and persists everything through the memory tools.
tools: [read_athlete, write_profile, upsert_goal, log_session, estimate_1rm]
---

# Athlete Onboarding — l'Entretien

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
   Weight goes to profile.weight_kg — the STATIC profile fact. Later weigh-ins are a
   time series recorded as bodyweight_kg on check-ins, never by rewriting the
   profile; downstream skills read the trend from check-ins and the baseline from
   the profile. If they happen to know their body-fat percentage, record
   body_fat_pct — but this is sensitive: never demand it, never suggest measuring
   it, accept "no idea" instantly and move on.
4. **Sport & history** — main sport, discipline, competition level, years of
   structured training (maps to training_age: beginner < 2y structured, intermediate
   2-5y, advanced > 5y — state your mapping when you write it).
5. **Performance inventory** — the benchmarks the needs analysis will require.
   - Strength or mixed-sport athletes: build the multi-lift 1RM inventory
     (profile.lift_inventory), one lift at a time, for the lifts relevant to the
     goal (typically squat, bench, deadlift, plus sport-specific lifts). Per lift:
     a tested 1RM → record with source "tested" and its date; only a recent heavy
     set (e.g. "5 reps at 100 kg with 2 in reserve")? → convert via `estimate_1rm`
     and record with source "estimated" — always tell the athlete you estimated it.
   - Endurance athletes: recent race times over the relevant distances.
6. **Goal** — objective, target metric and value, deadline, priority. Also confirm
   the CURRENT benchmark from step 5 that matches it — the assessment needs it.
7. **Calendar type** — profile.calendar_type, one of single_deadline (one race or
   meet date), recurring_fixtures (weekly matches), open_ended (no fixed date). It
   drives the periodization model later, so probe in plain language — e.g. in
   French: "une compétition précise, des matchs chaque semaine, ou pas
   d'échéance ?"
8. **Environment** — equipment (be concrete: barbell? rack? treadmill? track
   access?), sessions per week, minutes per session, and split_preferences (e.g.
   "upper/lower", "full body", "push/pull/legs" — scheduling quirks go to notes).
9. **Injuries & flags** — current or recent injuries, pain, medical constraints.
   Anything active: call `write_profile` immediately with the flag (don't wait for
   the batch), then continue, applying the red-flag rules from performance-coach.
10. **Preferences** — anything they hate/love, schedule quirks → profile notes.

## Persistence rules

- After steps 3-5, 7-8, and 10: call `write_profile` with the FULL updated profile
  (read first — it is a whole-document replace; omitted fields are dropped,
  including lift_inventory, body_fat_pct, calendar_type, split_preferences).
  Step 9 flags were already written immediately, per the protocol.
- After step 6: `upsert_goal` (id: short kebab slug, e.g. sub-45-10k). If the goal
  is later renegotiated during the needs analysis, that skill REUSES this same goal
  id so the milestone overwrites the raw ask — never leave an unassessed original
  goal active.
- If they mention recent training sessions, offer to `log_session` them — history
  improves everything downstream (strength sessions with structured exercises →
  sets {reps, load_kg, rir} when they can recall them).
- Timestamps are naive local wall-clock time; dates ISO (YYYY-MM-DD).

## Exit

Summarize what you stored (quote the profile back briefly), then route: new goal →
needs-analysis. Never skip the needs analysis on the way to a program.
