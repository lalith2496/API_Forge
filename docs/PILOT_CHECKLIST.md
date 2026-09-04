# Pilot checklist (1–2 early adopters)

Use this for the first team pilot before wider rollout. Complete within one sprint.

## Participants

| Role | Name | Date started |
|------|------|--------------|
| QA pilot | | |
| Dev observer (optional) | | |
| Team lead | | |

## Prerequisites

- [ ] Both pilots completed [TEAM_GUIDE.md](../TEAM_GUIDE.md) Quick start
- [ ] Same Postman collection or OpenAPI file agreed as pilot input
- [ ] QA staging base URL and test credentials available (not committed to git)

## Pilot steps

### A — Generate

- [ ] Import shared Postman collection (or OpenAPI) in **Test Generator**
- [ ] Select **2–3 endpoints** (include one POST with body, one GET with query params)
- [ ] Generate with team-default LLM (Gemini or QA6 LLM)
- [ ] Note generation time and case count

### B — Run in browser

- [ ] Set Base URL to QA
- [ ] Enter Access token and API key
- [ ] Run with categories: `happy_path`, `auth`, `validation` only (first pass)
- [ ] Record pass / fail / error counts
- [ ] Open 2 failed cases: confirm whether failure is status or assertion

### C — Export and handoff

- [ ] Download JSON suite → save to `test-suites/<api-name>/` with dated filename
- [ ] Download Postman collection
- [ ] Second pilot imports Postman collection and runs 3 requests manually
- [ ] Update `test-suites/<api-name>/README.md` from [_template](../test-suites/_template/README.md)

### D — Retro (30 min)

- [ ] List false failures (auth injection, empty body, RFC assertions)
- [ ] Log items in [FEEDBACK.md](FEEDBACK.md)
- [ ] Decide category skip list for this API
- [ ] Go / no-go for onboarding rest of team

## Success criteria

- [ ] Both pilots can run app locally without blocker
- [ ] Happy path + auth cases run with correct headers/body
- [ ] Postman handoff works for at least one peer
- [ ] Shared folder has one JSON + README with metadata

## Pilot sign-off

| | Name | Date |
|---|------|------|
| QA pilot | | |
| Team lead | | |
