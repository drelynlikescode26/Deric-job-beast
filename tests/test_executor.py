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


def test_mark_job_state_applied():
    states = {}
    executor.mark_job_state(states, "https://company.workday.com/job/99", "applied", "CAREER_SITE")
    assert "https://company.workday.com/job/99" in states
    entry = states["https://company.workday.com/job/99"]
    assert entry["status"] == "applied"
    assert entry["type"] == "CAREER_SITE"
    assert entry["company"] == "company.workday.com"
    assert entry["recorded_at"] is not None


def test_mark_job_state_assessment():
    states = {}
    executor.mark_job_state(
        states, "https://jobs.lever.co/acme/123", "assessment_required",
        "CAREER_SITE", notes="HireVue video interview"
    )
    entry = states["https://jobs.lever.co/acme/123"]
    assert entry["status"] == "assessment_required"
    assert entry["notes"] == "HireVue video interview"


def test_detect_assessment_positive():
    found, kw = executor.detect_assessment("Please complete an assessment to continue.")
    assert found is True
    assert kw is not None


def test_detect_assessment_negative():
    found, kw = executor.detect_assessment("Apply now by filling in your details below.")
    assert found is False
    assert kw is None


def test_detect_assessment_hirevue():
    found, kw = executor.detect_assessment("You will be invited to complete a HireVue video interview.")
    assert found is True


def test_detect_assessment_hackerrank():
    found, kw = executor.detect_assessment("Next step is a HackerRank coding challenge.")
    assert found is True


def test_parse_assessment_flag_positive():
    text = "I started the application but found:\nASSESSMENT_REQUIRED: HireVue video interview detected"
    found, desc = executor.parse_assessment_flag(text)
    assert found is True
    assert "HireVue" in desc


def test_parse_assessment_flag_negative():
    text = "Application submitted successfully. Generated Password: abc123"
    found, desc = executor.parse_assessment_flag(text)
    assert found is False


def test_get_or_create_credentials_new():
    """No existing account → should generate fresh credentials."""
    import json, tempfile, os
    from pathlib import Path

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({}, f)
        tmp = f.name

    original = executor.ACCOUNTS_PATH
    executor.ACCOUNTS_PATH = Path(tmp)
    try:
        email, password, is_new = executor.get_or_create_credentials("https://company.workday.com/job/1", PROFILE)
        assert is_new is True
        assert "@" in email
        assert len(password) >= 12
    finally:
        executor.ACCOUNTS_PATH = original
        os.unlink(tmp)


def test_get_or_create_credentials_existing():
    """Existing account for domain → should return stored credentials."""
    import json, tempfile, os
    from pathlib import Path

    stored = {"company.workday.com": [{"email": "saved@test.com", "password": "saved-pass", "status": "Created", "created_at": "2025-01-01"}]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(stored, f)
        tmp = f.name

    original = executor.ACCOUNTS_PATH
    executor.ACCOUNTS_PATH = Path(tmp)
    try:
        email, password, is_new = executor.get_or_create_credentials("https://company.workday.com/job/99", PROFILE)
        assert is_new is False
        assert email == "saved@test.com"
        assert password == "saved-pass"
    finally:
        executor.ACCOUNTS_PATH = original
        os.unlink(tmp)


def test_load_states_migrates_applied_at():
    """Old entries with applied_at should be migrated to recorded_at."""
    import json, tempfile, os
    from pathlib import Path

    data = [{"url": "https://example.com/job/1", "applied_at": "2025-01-01 10:00:00",
             "company": "example.com", "status": "applied", "type": None}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp = f.name

    original = executor.STATE_PATH
    executor.STATE_PATH = Path(tmp)
    try:
        states = executor.load_states()
        entry = states["https://example.com/job/1"]
        assert "recorded_at" in entry
        assert "applied_at" not in entry
    finally:
        executor.STATE_PATH = original
        os.unlink(tmp)
