# PerformanceAgent

Open-source, AI-powered, evidence-based physical preparation platform — a digital
strength & conditioning assistant that designs, explains, monitors, and adapts
training programs.

**Status:** early development (MVP in progress).

## Design principles

- **Evidence first** — recommendations trace to a graded, verifiable evidence database.
- **LLMs narrate, the engine calculates** — all sports-science math lives in a
  deterministic, fully tested Python package (`performance_agent.engine`).
- **Long-term athlete memory** — no conversation starts from zero.
- **Multilingual** — English (default), French, Spanish.

## Repository layout

- `apps/api` — Python backend (FastAPI, agents, sports science engine)
- `docs/superpowers/specs` — architecture blueprint and design docs
- `docs/superpowers/plans` — implementation plans

## License

Apache-2.0 — see [LICENSE](LICENSE).
