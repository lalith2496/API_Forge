from streamlit_app import (
    _filter_run_results,
    _result_icon,
    _result_option_label,
)


def _sample_results():
    return [
        {"id": "TC-01", "passed": True, "description": "ok"},
        {"id": "TC-02", "passed": False, "description": "fail"},
        {"id": "TC-03", "error": "timeout", "description": "err"},
        {"id": "TC-04", "skipped": True, "description": "skip"},
    ]


def test_filter_run_results():
    rows = _sample_results()
    assert len(_filter_run_results(rows, "All")) == 4
    assert len(_filter_run_results(rows, "Passed")) == 1
    assert len(_filter_run_results(rows, "Failed")) == 1
    assert len(_filter_run_results(rows, "Errors")) == 1
    assert len(_filter_run_results(rows, "Skipped")) == 1


def test_result_option_label():
    label = _result_option_label({"id": "TC-01", "passed": True, "description": "happy path"})
    assert label.startswith("✅ TC-01")


def test_result_icon():
    assert _result_icon({"passed": True}) == "✅"
    assert _result_icon({"error": "x"}) == "⚠"
