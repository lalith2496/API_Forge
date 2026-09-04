# API Forge — Team Guide (Local + Manual)

Operational guide for QA and developers running API Forge on their laptops. For technical reference (features, providers, exports), see [README.md](README.md).

---

## Quick start (every teammate)

### 1. Clone and install

```bash
git clone <your-repo-url>
cd API_Forge-main
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Requires **Python 3.9+**.

### 2. Configure `.env`

Copy [.env.example](.env.example) to `.env` and set **one** LLM option:

| Provider | `.env` | When to use |
|----------|--------|-------------|
| **Gemini** (default) | `GEMINI_API_KEY=your_key` | External / no corporate VPN |
| **QA6 LLM** (internal) | No key needed | On corporate network; select **QA6 LLM** in the UI |

Optional — allow staging API hosts (SSRF guard in the runner):

```bash
ALLOWED_HOSTS=qa6-api2.sprinklr.com,qa6-api2-bdi.sprinklr.com
```

**Never commit `.env`** with real API keys or tokens.

### 3. Run the app

```bash
streamlit run streamlit_app.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

---

## Team conventions

Agree these once with your squad and record any overrides in your API folder under [test-suites/](test-suites/).

### Input source of truth

| Source | Best for |
|--------|----------|
| **OpenAPI / Swagger** | Full coverage, spec-aligned happy paths |
| **Postman collection** | Teams that already maintain Postman requests |
| **cURL** | Quick single-endpoint checks |

**Default for this team:** Postman collection (update if your squad standardizes on OpenAPI).

### Credentials

- Enter **Access token** and **API key** only in **Step 3 — Run Tests** (session-only).
- Bearer token → `Authorization` header; API key → `Key` header (when the spec defines both).
- Exported suites use placeholders (`VALID_TOKEN`, `API_KEY`) — **never** paste live secrets into JSON you commit.
- Do not commit `.env` or downloaded `.env` profiles with real values.

### Default environments

| Environment | Base URL (example) |
|-------------|-------------------|
| QA | `https://qa6-api2.sprinklr.com` |
| QA BDI | `https://qa6-api2-bdi.sprinklr.com` |

Adjust for your service; document per API in `test-suites/<api-name>/README.md`.

### Category filters (Step 3 — Run Tests)

Our APIs do **not** consistently return RFC 7807 problem+json. When running regression:

- **Run:** `happy_path`, `auth`, `validation`, `boundary`, `security`
- **Skip (unless API supports it):** `rfc_problem`, `rfc_semantics`, `rfc_cookies`

Use the **Categories to run** multiselect in Step 3.

### What counts as “pass”

A test passes only when **both** match:

1. **HTTP status** (Expected vs Got)
2. **All response assertions** (schema, RFC 7807, etc.)

If status matches but the row shows fail, read the red banner — e.g. `missing RFC 7807 field 'type'` means the body shape failed, not the status code.

### When to re-generate a suite

Re-run **Generate Test Cases** when:

- OpenAPI or Postman source changes
- New endpoints are added
- Tool fixes affect finalize (auth/body injection)

Saved session suites do **not** auto-update.

---

## Day-to-day workflow

### QA engineer (primary)

1. **Test Generator** tab → import Postman / OpenAPI / cURL
2. Select **1–10 endpoints**
3. Choose **LLM provider + model** → **Generate Test Cases**
4. Fill **Test data** for `USER_INPUT:*` fields (IDs, filters, etc.)
5. **Step 3 — Run Tests:** Base URL, Access token, API key
6. Filter categories (see conventions above)
7. Review **Response details** for failures
8. **Step 4 — Downloads:** export JSON + Postman; save under [test-suites/](test-suites/) (see naming below)

### Developer

1. Same flow for owned endpoints before release
2. **API Docs** tab to verify uploaded spec
3. Send updated OpenAPI/Postman to QA when contracts change

### Team lead

1. Review new exports in `test-suites/<api>/`
2. Ensure each folder has an updated `README.md` (env, date, generator, known skips)
3. Triage feedback via [docs/FEEDBACK.md](docs/FEEDBACK.md)

---

## Walkthrough — Steps 1–4

### Step 1 — Import and select

- Choose input mode: OpenAPI spec, Postman collection, or cURL
- Upload or paste source
- Select endpoints to include (max 10 per generation)

### Step 2 — Generate

- Pick provider: **Gemini** or **QA6 LLM**
- Pick model and max test depth
- Click **Generate Test Cases**
- Complete **Test data** fields if prompted

### Step 3 — Run Tests

- Paste **Access token** and **API key** (if the API uses both)
- Set **Base URL**
- Optionally filter **Categories to run**
- Click **Run Tests**; inspect pass/fail and per-case response details

### Step 4 — Download and share

- JSON suite → store in `test-suites/<api-name>/`
- Postman collection → share with teammates for manual runs
- pytest / `.env` template → optional local use later

---

## Sharing test suites (no CI)

| Artifact | Purpose |
|----------|---------|
| `*.json` | Source of truth for generated cases |
| Postman export | Manual runs in Postman with collection variables |
| `README.md` per API | Base URL, spec version, who generated, category skips |

**Folder layout:**

```
test-suites/
  <api-name>/
    README.md
    YYYY-MM-DD_<env>_<short-description>.json
```

Example: `test-suites/kb-api/2026-09-03_qa6_postman-v3.json`

See [test-suites/README.md](test-suites/README.md) and [test-suites/_template/README.md](test-suites/_template/README.md).

---

## Onboarding checklist

Copy for each new teammate:

- [ ] Clone repo, create venv, `pip install -r requirements.txt`
- [ ] Copy `.env.example` → `.env`; set `GEMINI_API_KEY` or confirm QA6 LLM on VPN
- [ ] Set `ALLOWED_HOSTS` if hitting QA/staging hosts
- [ ] Run `streamlit run streamlit_app.py`
- [ ] Import a known Postman collection
- [ ] Generate suite for 1–2 endpoints
- [ ] Run `happy_path` + `auth` against QA base URL
- [ ] Export JSON and Postman; confirm a peer can import Postman export
- [ ] Understand status vs assertion failures (see conventions)
- [ ] Read [docs/PILOT_CHECKLIST.md](docs/PILOT_CHECKLIST.md) if joining the pilot

---

## Common pitfalls

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| Empty auth tests still send token | Old generated suite | Re-generate suite |
| Empty body tests send full payload | Old generated suite | Re-generate suite |
| 401 instead of 200 on happy path | Missing API key or token | Fill both Access token and API key |
| Expected/Got match but test fails | Assertion (e.g. RFC 7807) | Read red banner; skip `rfc_problem` or fix API |
| `Host not in ALLOWED_HOSTS` | SSRF guard | Add host to `ALLOWED_HOSTS` in `.env` |
| Generation error / no LLM | Missing key or VPN | Check `GEMINI_API_KEY` or QA6 network |

---

## Pilot and feedback

- **Pilot:** [docs/PILOT_CHECKLIST.md](docs/PILOT_CHECKLIST.md) — first 1–2 adopters
- **Rollout:** [docs/ONBOARDING.md](docs/ONBOARDING.md) — full team after pilot
- **Feedback:** [docs/FEEDBACK.md](docs/FEEDBACK.md) — false failures and improvement ideas

---

## Out of scope (for now)

- Shared hosted Streamlit instance
- Docker / Kubernetes deployment
- Jenkins or Newman CI
- Production test runs without explicit approval

These can be added in a later phase if the team moves beyond local manual workflows.
