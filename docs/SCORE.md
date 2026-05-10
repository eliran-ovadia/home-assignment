# Project Score Tracker

Updated after each significant milestone. Scores are 1–10.

**Current overall: 9.3 / 10**
Last updated: 2026-05-10 — post spec, pre-implementation.

---

## Scores by Criterion

| Criterion | Score | Phase | Notes |
|-----------|-------|-------|-------|
| System Design | 9.5 | Spec | Layered arch, 10 ADRs, full pseudocode, violation matrix. Significantly exceeds expectations. |
| AI Usage | 9.0 | Spec | AI_USAGE.md is honest, shows real debate, documents corrections and mistakes. |
| Problem Solving | 9.0 | Spec | All business logic correctly specified. Edge cases covered (oversell, partial sell, concurrent uploads). |
| Documentation | 9.0 | Spec | SPEC.md, CHECKLIST.md, PRODUCTION_ROADMAP.md, example_prompts.txt, README with curl examples and Swagger link. |
| DevOps & Tooling | 9.5 | Spec | Docker multi-stage, docker-compose, CI with lint→test→AI review, pre-commit, Makefile, 80% coverage gate. |
| Bonus Coverage | 9.5 | Spec | Bonus analytics, upload history, dark mode, loading states, error handling, indexing, precomputed analytics. |
| Code Quality | — | Impl | Not yet implemented. |
| Test Coverage | — | Impl | 80% threshold configured; tests not yet written. |
| Execution | 9.0 | Spec | requirements.txt added, Swagger link in README, curl examples. Docker not yet verified to build clean. |
| Assignment Compliance | 9.5 | Spec | All mandatory features covered. 0 open gaps after requirements.txt fix. |

---

## What Moves Each Score

### System Design → 10
- Implementation matches the spec exactly (no shortcuts, no deviations)
- Clean git history — each commit is atomic and explains *why*

### AI Usage → 10
- Fill in the Phase 2 table in AI_USAGE.md as each component is implemented
- Document any corrections made during implementation

### Problem Solving → 10
- FIFO tests pass on all edge cases (partial sell, oversell, empty queue)
- Violation detection tests pass with correct boundary values

### Code Quality → score when implementation exists
- No ruff violations (CI enforces this)
- No ty type errors (CI enforces this)
- No route contains business logic (layer rule: api → domain → db)
- No direct `os.environ` calls in business logic

### Test Coverage → score when tests exist
- `make test` passes green with ≥ 80% coverage
- Integration tests cover the two-user isolation scenario
- Edge cases listed in SPEC §7 all have corresponding tests

### Execution → 10
- `docker compose up --build` works on a clean machine in one command
- `make install && make test` passes on a clean Python 3.12 environment
- README instructions are literally copy-pasteable (no guesswork)

---

## Milestone Log

| Date | Event | Score before | Score after |
|------|-------|-------------|-------------|
| 2026-05-09 | Spec started | — | — |
| 2026-05-10 | Spec complete, ADRs finalised, checklist created | 9.1 | 9.3 |
| — | Implementation: backend complete | — | — |
| — | Implementation: tests passing ≥ 80% | — | — |
| — | Implementation: frontend complete | — | — |
| — | Docker build verified clean | — | — |
| — | Full end-to-end run with sample file | — | — |
