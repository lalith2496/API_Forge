import environment_profiles


def test_default_profiles_has_all_tiers():
    profiles = environment_profiles.default_profiles()
    assert set(profiles.keys()) == set(environment_profiles.TIERS)


def test_save_and_get_profile():
    profiles = environment_profiles.default_profiles()
    profiles = environment_profiles.save_profile(
        profiles, "QA", {"API_BASE_URL": "https://qa.example.com", "ACCESS_TOKEN": "tok"}
    )
    got = environment_profiles.get_profile(profiles, "QA")
    assert got["API_BASE_URL"] == "https://qa.example.com"
    assert got["ACCESS_TOKEN"] == "tok"


def test_prod_guardrails():
    prod = environment_profiles.prod_guardrails("PROD")
    assert prod["require_confirmation"] is True
    assert prod["max_concurrency"] == 2
