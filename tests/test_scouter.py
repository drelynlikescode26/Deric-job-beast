import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "Auto-Applier"
spec = importlib.util.spec_from_file_location("scouter", ROOT / "scouter.py")
scouter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scouter)


def test_normalize_link_absolute():
    assert scouter.normalize_link("https://example.com", "https://example.com/jobs/1") == "https://example.com/jobs/1"


def test_normalize_link_relative():
    assert scouter.normalize_link("https://example.com/careers/", "/jobs/1") == "https://example.com/jobs/1"


def test_classify_link_easy_apply():
    assert scouter.classify_link("https://linkedin.com/jobs/view/123", "") == "EASY_APPLY"


def test_classify_link_career_site():
    assert scouter.classify_link("https://company.workday.com/job/123", "") == "CAREER_SITE"
