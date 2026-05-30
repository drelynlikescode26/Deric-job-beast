import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "Auto-Applier"
spec = importlib.util.spec_from_file_location("executor", ROOT / "executor.py")
executor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(executor)


PROFILE = {
    "contact_info": {
        "first_name": "Jane",
        "last_name": "Doe",
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "phone": "555-1234",
    }
}


def test_generate_credentials():
    email, password = executor.generate_credentials(PROFILE)
    assert email.startswith("jane.doe+")
    assert email.endswith("@example.com")
    assert len(password) >= 12


def test_fill_common_fields_no_error():
    class DummyPage:
        def __init__(self):
            self.filled = {}

        def query_selector(self, selector):
            return self

        def fill(self, selector, value):
            self.filled[selector] = value

    page = DummyPage()
    executor.fill_common_fields(page, PROFILE, "jane@example.com", "secret")
    assert page.filled["input[name='email']"] == "jane@example.com"
    assert page.filled["input[name='first_name']"] == "Jane"
    assert page.filled["input[name='last_name']"] == "Doe"
    assert page.filled["input[name='phone']"] == "555-1234"


def test_with_retry_success_first_try():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = executor.with_retry(fn, retries=3, delay=0)
    assert result == "ok"
    assert len(calls) == 1


def test_with_retry_succeeds_after_failures():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("transient")
        return "done"

    result = executor.with_retry(fn, retries=3, delay=0)
    assert result == "done"
    assert len(calls) == 3


def test_with_retry_raises_after_exhaustion():
    import pytest

    def fn():
        raise RuntimeError("always fails")

    with pytest.raises(RuntimeError):
        executor.with_retry(fn, retries=2, delay=0)


def test_load_states_old_format():
    """Old format: list of URL strings."""
    import json, tempfile, os
    from pathlib import Path

    data = ["https://example.com/job/1", "https://example.com/job/2"]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp = f.name

    original = executor.STATE_PATH
    executor.STATE_PATH = Path(tmp)
    try:
        states = executor.load_states()
        assert "https://example.com/job/1" in states
        assert states["https://example.com/job/1"]["status"] == "applied"
    finally:
        executor.STATE_PATH = original
        os.unlink(tmp)


def test_load_states_new_format():
    """New format: list of dicts."""
    import json, tempfile, os
    from pathlib import Path

    data = [{"url": "https://example.com/job/3", "applied_at": "2025-01-01 10:00:00", "company": "example.com", "status": "applied", "type": "CAREER_SITE"}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp = f.name

    original = executor.STATE_PATH
    executor.STATE_PATH = Path(tmp)
    try:
        states = executor.load_states()
        assert "https://example.com/job/3" in states
        assert states["https://example.com/job/3"]["type"] == "CAREER_SITE"
    finally:
        executor.STATE_PATH = original
        os.unlink(tmp)


def test_mark_applied_state():
    states = {}
    executor.mark_applied_state(states, "https://company.workday.com/job/99", "CAREER_SITE")
    assert "https://company.workday.com/job/99" in states
    entry = states["https://company.workday.com/job/99"]
    assert entry["status"] == "applied"
    assert entry["type"] == "CAREER_SITE"
    assert entry["company"] == "company.workday.com"
    assert entry["applied_at"] is not None
