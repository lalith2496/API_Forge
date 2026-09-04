# Shared test suites

Version-controlled exports from API Forge for team handoff (manual regression, no CI).

## Layout

```
test-suites/
  <api-name>/
    README.md                              # Required metadata for this API
    YYYY-MM-DD_<env>_<description>.json    # Generated suite (placeholders only)
```

## Naming exports

| Part | Example | Meaning |
|------|---------|---------|
| Date | `2026-09-03` | Generation date |
| Env | `qa6` | Target environment |
| Description | `postman-v3` | Source or spec version hint |

Example file: `2026-09-03_qa6_postman-v3.json`

## Before you commit

- Suites should contain **placeholders** (`VALID_TOKEN`, `API_KEY`, `USER_INPUT:*`) — not live secrets.
- Update the API’s `README.md` with base URL, generator name, and categories skipped.
- Do not commit `.env` files or Postman exports with real tokens.

## Adding a new API

1. Copy [\_template/README.md](_template/README.md) to `test-suites/<your-api>/README.md`
2. Fill in metadata after your first successful generation
3. Drop the JSON export from Step 4 — Downloads into that folder

## Using a teammate’s export

1. Open API Forge locally
2. Use the JSON as reference or re-import workflow: share the same Postman/OpenAPI source + compare case IDs
3. For Postman: import the **Postman collection** download from the same generation run
4. Set collection variables (`BASE_URL`, `ACCESS_TOKEN`, etc.) in Postman — never from committed secrets
