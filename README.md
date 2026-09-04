# API Forge

AI-powered API test suite generator. Upload an **OpenAPI/Swagger spec**, **Postman collection**, or **cURL command**, pick endpoints, and generate a full test suite. Run tests in the browser or export to **Postman**, **pytest**, or **JSON**.

## What is API Forge?

API Forge turns your API definition into a ready-to-run test suite in minutes. Instead of writing every happy path, negative case, and auth check by hand, you import your spec or collection, select the endpoints you care about, and let AI plus rule-based generators build structured test cases for you.

The workflow is simple:

1. **Import** — OpenAPI 3, Swagger 2, Postman collection, or cURL
2. **Generate** — LLM creates test cases; supplements add validation, security, and RFC-style coverage
3. **Run** — Execute in the browser with your base URL, access token, and API key
4. **Export** — Hand off to QA or CI as Postman, pytest, JSON, or a `.env` template

## Benefits

| Benefit | Description |
|--------|-------------|
| **Faster test creation** | Generate dozens of cases from a spec or collection instead of writing them manually |
| **Spec-aligned coverage** | Happy paths use correct payloads, query params, and auth headers from your API definition |
| **Run immediately** | In-browser runner with pass/fail results, response details, and per-case rerun |
| **Export anywhere** | Postman collection, pytest file, JSON suite, and `.env` template for your existing toolchain |
| **Broader coverage** | Includes happy path, auth, validation, boundary, security, and invalid-payload cases |
| **Less repetitive setup** | Fill `USER_INPUT:*` values once; they apply across the whole suite |
| **Team-friendly output** | QA, developers, and automation can share the same generated suite |

### Who is it for?

- **QA engineers** who need quick regression coverage for new or existing APIs
- **Backend developers** validating endpoints before release
- **Teams with OpenAPI or Postman** who want automated tests without building everything from scratch

## Features

- Import from **OpenAPI 3 / Swagger 2** (JSON or YAML), **Postman collections**, or **cURL** commands.
- Parse OpenAPI specs with `$ref`, `allOf/anyOf/oneOf`, and cyclic-ref handling.
- Multi-endpoint selection (1–10) with a token-minimized payload sent to the LLM.
- Pluggable LLM providers (Gemini included; see "Adding a new provider").
- Fill `USER_INPUT:*` values once and apply them across the whole suite.
- In-browser test runner with an editable environment-variable panel
  (e.g. `ACCESS_TOKEN`, `API_KEY`, `API_BASE_URL`).
- Exports: JSON suite, Postman collection (with pre-request guards), pytest file, `.env` template.
- Inline API docs rendered with ReDoc.

## Tech Stack

- Python 3
- Streamlit (UI)
- google-genai (LLM)
- requests, PyYAML, python-dotenv, pandas

## Setup

1. Ensure **Python 3.9+** is installed.

2. (Recommended) Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   python3 -m pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root with your Gemini API key:
   ```bash
   GEMINI_API_KEY=your_api_key_here
   ```
   > The model is selected from the UI at runtime, so no model env var is required.

5. Run the app:
   ```bash
   python3 -m streamlit run streamlit_app.py
   ```

## Team adoption

For **local team rollout** (setup, conventions, sharing suites, onboarding checklist), see **[TEAM_GUIDE.md](TEAM_GUIDE.md)**.

- Shared exports: [test-suites/](test-suites/)
- Pilot checklist: [docs/PILOT_CHECKLIST.md](docs/PILOT_CHECKLIST.md)
- Feedback log: [docs/FEEDBACK.md](docs/FEEDBACK.md)

## Usage

1. **Import** an OpenAPI/Swagger spec, Postman collection, or cURL command in the **Test Generator** tab.
2. **Select** 1–10 endpoints.
3. Choose an **LLM provider** and **model**, then **Generate Test Cases**.
4. (If prompted) fill in **Test data** values for any `USER_INPUT:*` fields.
5. **Run Tests** in the browser:
   - Set the **Base URL** and any environment variables (e.g. `ACCESS_TOKEN`).
   - Results show pass/fail/error/skipped with response details.
6. **Download** the suite as JSON, a Postman collection, or a pytest file, and grab the
   `.env` template.
7. The **API Docs** tab renders the uploaded spec with ReDoc.

### Running exports

- **Postman:** import the collection, open the collection → **Variables**, set values
  (`BASE_URL`, `ACCESS_TOKEN`, etc.), then run. Pre-request scripts block a request
  until its required variables are set.
- **pytest:** put the values in a `.env` next to the downloaded file, then run `pytest`.
  The suite is embedded in the file; tests needing a token skip cleanly if it's unset.

## Adding a new provider

1. Read `llm/base.py` and create a new file in `llm/` implementing `LLMProvider`:
   1. `is_configured() -> bool`
   2. `list_models() -> list[[name, display_name]]`
   3. `generate_result(model, prompt) -> dict`
2. Register it in `llm/provider_registry.py` by importing the class and adding it to
   the `providers` dict.

## Notes

- The in-browser runner sends HTTP requests from the host machine to the Base URL you
  enter. When deploying, restrict access (VPN/SSO) and serve over HTTPS.
- For offline/corporate deployments, note that the API Docs tab loads ReDoc from a CDN.
