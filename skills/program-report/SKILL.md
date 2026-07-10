---
name: program-report
description: Use when the athlete wants their program as a shareable PDF document.
  Chooses the mode, pre-checks citations, renders via Typst, and hands back the file.
tools: [read_athlete, read_program, check_citations, render_report]
---

# Program Report

Follow performance-coach global rules. The report is the athlete's take-away
document — it must be as honest as the conversation that produced it.

## Protocol

1. Confirm there is a program: `read_athlete` → program_version. Null → route to
   program-generation; a report of nothing helps nobody.
2. Ask which mode (one question): **coach** — terse instructions to train with;
   **expert** — adds the adaptation reason and the full references section with
   evidence grades. Default to coach for athletes, expert for anyone who asks
   "why" a lot.
3. Pre-flight: `read_program` and run `check_citations` on the body. If anything
   is flagged, do NOT render — fix the program first (route to program-adaptation
   to save a corrected version with a reason). The renderer enforces the same
   gate and will refuse; the pre-flight just saves the athlete a failed attempt.
4. `render_report` (mode; version only if the athlete asked for an old one). The
   language follows the athlete's stored locale automatically.
5. Hand back the PDF path, note that the .typ source sits next to it, and — for
   coach mode — offer the expert version if they ever want the "why".

## If the render fails

- Unknown references: the program cites something outside the corpus — route to
  program-adaptation, replace the claim with an evidence-corpus-backed one (or
  drop it), save vN+1, render again.
- typst not installed: give the athlete the install hint from the error message
  and point them at the .typ source that was still written.
