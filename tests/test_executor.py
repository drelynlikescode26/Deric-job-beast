import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "Auto-Applier"
spec = importlib.util.spec_from_file_location("executor", ROOT / "executor.py")
executor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(executor)


def test_generate_credentials():
    profile = {"email": "jane.doe@example.com"}
    email, password = executor.generate_credentials(profile)
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
    executor.fill_common_fields(page, {"name": "Jane Doe", "first_name": "Jane", "last_name": "Doe", "phone": "123"}, "jane@example.com", "secret")
    assert page.filled["input[name='email']"] == "jane@example.com"
    assert page.filled["input[name='first_name']"] == "Jane"
