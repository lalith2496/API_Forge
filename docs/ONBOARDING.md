# Onboarding — full team rollout

After the [pilot](PILOT_CHECKLIST.md) sign-off, use this checklist for each additional teammate.

## Lead actions (once)

- [ ] Announce repo URL and link to [TEAM_GUIDE.md](../TEAM_GUIDE.md)
- [ ] Confirm team LLM choice (Gemini vs QA6 LLM)
- [ ] Publish default Base URLs and category skip list in `test-suites/<api>/README.md`
- [ ] Schedule 30-minute walkthrough (Steps 1–4 live demo)

## Per teammate

- [ ] Clone, venv, `pip install -r requirements.txt`
- [ ] `.env` from `.env.example` (Gemini key or QA6 on VPN)
- [ ] `ALLOWED_HOSTS` set if needed
- [ ] `streamlit run streamlit_app.py` opens successfully
- [ ] Import team-standard Postman/OpenAPI file
- [ ] Generate + run happy_path and auth against QA
- [ ] Import a colleague’s Postman export from `test-suites/`
- [ ] Knows status vs assertion failures (TEAM_GUIDE conventions)
- [ ] Knows where to log issues ([FEEDBACK.md](FEEDBACK.md))

## Week 1 check-in

- [ ] Each member ran at least one full suite
- [ ] Review [FEEDBACK.md](FEEDBACK.md) themes with team lead
- [ ] Update TEAM_GUIDE conventions if pilot retro changed defaults

## Sign-off

| Teammate | Onboarded | Date |
|----------|-----------|------|
| | | |
| | | |
