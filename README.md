# Digital Mechanic — AI agent for ICE diagnostics

Web prototype of the "Digital Mechanic" AI agent for the «ИИкузница / НейроДВС»
hackathon (26–27.11.2026): a mechanic selects a vehicle, runs an acoustic check,
the agent explains the result against the engine's manuals (RAG) with page
citations and files a defect inspection ticket.

> README is a stub for now — the full five-minute startup guide lands with the
> release. Issued mock services and synthetic test data are published here;
> **copyrighted factory manuals are not** (see `data/manuals/README.md`) and
> connect through configuration.

## Repository layout

| Path | Contents |
|---|---|
| `src/mechanic/` | FastAPI backend: agent loop, tools, services, API |
| `shared/` | Contract Pydantic models (shared with the RAG module) |
| `frontend/` | Vue 3 + TypeScript SPA (added in a later stage) |
| `data/` | Issued synthetic test data: `vehicles.json`, `fault_types.json`; `manuals/` holds the doc manifest — PDFs are supplied separately (copyright) |
| `vendor/` | Issued mock services: Mock ML (`POST /diagnose`), Mock ТОиР (`POST /tickets`), OpenAPI specs |
| `prompts/` | Agent system prompt (skeleton + manual-specific parts) |
| `tests/` | pytest suite |
