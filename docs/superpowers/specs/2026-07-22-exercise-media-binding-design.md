# Exercise media binding — agent-chosen GIFs on program blocks

**Date:** 2026-07-22
**Status:** approved

## Problem

Program HTML pages support embedded exercise GIFs (from the auto-synced
`hasaneyldrm/exercises-dataset` clone), but resolution from a program block to a
dataset record fails whenever the coach writes exercise names in the athlete's
language. The dataset's 1,324 record names are English-only; the resolver
(seed map → exact normalised name → fuzzy ≥ 0.9) has no cross-language path.
Real case: a Spanish-language program ("Sentadilla trasera", "Zancadas",
"Plancha", `exercise_id: null` on every block) rendered zero media out of a
fully synced 420 MB dataset.

The dataset install/sync layer is **not** the problem — `exercises/dataset.py`
already clones on first server start and fast-forward pulls on every start,
offline-tolerant.

## Decision

Bind media at program-creation time, by the agent. The coach (Claude) is the
translation layer: it searches the dataset in English, picks the right record,
and stamps its id on the block. No server-side alias tables, no cross-language
guessing in code.

Rejected alternatives:

- **Curated multilingual alias file** (es/fr → dataset id): retroactive but
  partial coverage and permanent manual maintenance.
- **Fuzzy matching over localised instruction text**: fragile, high risk of
  wrong-GIF matches, which is worse than no GIF.

## Design

### 1. Schema: `media_id` on `ExerciseBlock`

New optional field on `ExerciseBlock` (`memory/schemas.py`):

```python
media_id: str | None = Field(default=None, min_length=1, max_length=16)
```

- Holds a dataset record id (e.g. `"0043"`). Loose validation only — the
  dataset is external and its id scheme may evolve; an unknown id degrades to
  "no media" at render, never an error.
- Backward compatible: absent in every existing plan YAML, default `None`.

### 2. Resolution order in `render_html.py`

`_MediaResolver` (currently `index.resolve(block.exercise, block.exercise_id)`)
gains a prioritised first step:

1. `block.media_id` → direct `by_id` lookup in the index (new public
   `ExerciseMediaIndex.get(dataset_id)` accessor).
2. Existing chain unchanged as fallback: curated seed map (by `exercise_id`),
   exact normalised name, fuzzy ≥ 0.9.

Unknown `media_id` or absent dataset clone → fall through to the name chain,
then to no media. Best-effort by design, as today.

### 3. New MCP tool: `search_exercise_media`

In `server/exercise_tools.py`:

```python
def search_exercise_media(
    query: str,
    equipment: str | None = None,
    target: str | None = None,
    limit: int = 10,
) -> ExerciseMediaSearchView
```

- Searches the local clone's index: normalised substring match on English
  names, then fuzzy completion up to `limit`; optional case-insensitive
  filters on the dataset's `equipment` and `target` fields.
- Returns per candidate: `media_id`, `name`, `equipment`, `target`,
  `secondary_muscles`. No GIF payload — the agent picks by metadata.
- Dataset not cloned yet (first start, sync in progress, or offline install):
  returns a structured `dataset_available: false` with a human-readable hint,
  never an exception.
- The tool docstring tells the agent its role explicitly: translate the
  athlete-language exercise name to English gym vocabulary, search, pick the
  matching record, set `media_id` on the block; leave `media_id` unset when no
  candidate clearly matches (wrong GIF is worse than no GIF).

### 4. Skill update: `program-optimization`

The session-composition skill gains one step before `save_program`: for each
strength-training block, call `search_exercise_media` (English query) and set
`media_id`. Explicitly best-effort — no candidate, no `media_id`. Conditioning
blocks (runs, intervals) are skipped; the dataset is gym-exercise media.

## Out of scope

- Multilingual alias table (rejected above).
- `render_report` (analysis reports): program pages come from `save_program`,
  which already carries the media pipeline.
- Regenerating existing athlete programs — usage, not code. After release, a
  v2 save with reason "add exercise media" rebinds an existing program.
- Dataset sync changes — install/update automation already exists and works.

## Licensing

Dataset metadata is MIT. GIFs are © Gym visual, redistributed with permission
at 180×180 with mandatory attribution — already emitted in the page footer
(`render_html.py`). No change needed.

## Testing

- **Schema:** `media_id` accepted, absent (default None), rejected when empty
  or over-long; existing plan YAML round-trips unchanged.
- **Resolution:** `media_id` wins over a contradicting name; unknown
  `media_id` falls back to the name chain; no dataset → no media, no error.
- **Tool:** query with/without filters returns ranked candidates; empty query
  rejected; dataset absent → `dataset_available: false`, no exception.
- **Render:** block with valid `media_id` emits the `media` div with the GIF
  data URI; block with unknown `media_id` renders without media.
