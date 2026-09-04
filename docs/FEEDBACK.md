# API Forge — team feedback log

Use this file to collect false failures and improvement ideas during pilot and rollout. Team lead triages weekly.

## How to add an entry

Copy the template below into the **Open** section. Do not paste live tokens or response bodies with secrets.

---

## Open

### YYYY-MM-DD — `<your name>` — short title

- **API / suite:** e.g. `task-api`, `2026-09-03_qa6_postman-v3.json`
- **Test case ID:** e.g. `TC-12`
- **Symptom:** What failed (status vs assertion)
- **Expected behavior:** What the test should do
- **Actual behavior:** What API Forge or the API did
- **Category:** happy_path / auth / validation / rfc_problem / other
- **Suggested action:** re-generate / skip category / tool bug / API bug

---

## Resolved

_Move items here when fixed or accepted as known limitation._

### Example — 2026-09-03 — RFC 7807 false failures

- **Decision:** Skip `rfc_problem` for Sprinklr QA APIs until services adopt problem+json
- **Doc update:** TEAM_GUIDE category filters

---

## Themes (rollup)

| Theme | Count | Status |
|-------|-------|--------|
| RFC 7807 assertions | | |
| Auth header injection | | |
| Empty body cases | | |
| Missing API key vs token | | |
| Generation quality / LLM | | |
