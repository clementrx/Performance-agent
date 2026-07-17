---
name: pre-competition
description: Use when a competition_protocol due action fires or the athlete says
  their competition is coming up. Authors the per-event, day-by-day protocol for
  the final days (J-N to J0) and delivers the phone page for the event.
tools: [read_athlete, get_time_context, read_calendar, read_program,
  read_research_dossier, recommend_taper, predict_race_time, estimate_1rm,
  carb_loading_targets, select_attempts, pacing_plan, get_citation,
  save_competition_protocol, log_kpi_result,
  fit_taper_response]
---

# Pre-competition

The protocol author: the final days before a competition, planned day by day and
handed over as a phone page the athlete reads on the morning of the event. Sport
comes from the research, numbers come from the engine, and this skill
NEVER edits the program — taper structure changes route to program-adaptation.

## Ritual

1. Open with `read_athlete` + `get_time_context` (quote its dates) and
   `read_calendar`; name the event, its priority, and days until. `read_program`
   for the planned taper; sanity-check it against `recommend_taper` (say the
   basis — individual or population).
2. First protocol for this event → run the dedicated mini-wave (deep-research
   rules): ONE question — "the final days before [this event] for [this
   athlete]" — verified studies join the corpus, the dossier gets a v+1.
   `read_research_dossier` for what is already known.
3. Build the day-by-day plan from J-window to J0, engine first:
   - Endurance: target from the goal or `predict_race_time`; `pacing_plan` for
     the splits; `carb_loading_targets` for fueling (quote ranges as ranges).
   - Strength: e1RM via `estimate_1rm` (recent best sets); `select_attempts`
     per lift. `goal_beyond_e1rm` flag → name the gap honestly; the athlete may
     call lighter, never heavier than the engine's numbers.
   - Everything else (meal timing, warm-up, logistics, checklist) is advice:
     cited (`get_citation`) or plainly labeled coaching judgment.
4. Documented practices (peak-week water/sodium, weight-cut tactics): describe
   ONLY what the literature documents, each with its evidence grade and an
   explicit warning — never a dose, never a schedule, never engine math. Red
   flags and medical conditions keep precedence: refer out.
5. Walk the draft through with the athlete, then submit it to program-review's
   protocol gate. Only an APPROVED verdict saves: `save_competition_protocol`
   (v2+ reason = the trigger). Hand the athlete the html_path — that page is
   their event-day companion.
6. Day J-0 to J+2: route the debrief to training-checkin and log the result
   with `log_kpi_result` — the outcome feeds fit_taper_response for next time.
