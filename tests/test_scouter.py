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


def test_classify_link_easy_apply_page_text():
    assert scouter.classify_link("https://company.com/job/456", "Easy Apply button available") == "EASY_APPLY"


def test_classify_link_career_site_workday():
    assert scouter.classify_link("https://company.myworkdayjobs.com/job/123", "") == "CAREER_SITE"


def test_classify_link_career_site_workday_legacy():
    assert scouter.classify_link("https://company.workday.com/job/123", "") == "CAREER_SITE"


def test_classify_link_career_site_greenhouse():
    assert scouter.classify_link("https://boards.greenhouse.io/company/jobs/123", "") == "CAREER_SITE"


def test_classify_link_career_site_lever():
    assert scouter.classify_link("https://jobs.lever.co/company/123", "") == "CAREER_SITE"


def test_classify_link_career_site_icims():
    assert scouter.classify_link("https://company.icims.com/jobs/123/job", "") == "CAREER_SITE"


def test_classify_link_career_site_smartrecruiters():
    assert scouter.classify_link("https://jobs.smartrecruiters.com/company/123", "") == "CAREER_SITE"


def test_classify_link_career_site_taleo():
    assert scouter.classify_link("https://company.taleo.net/careersection/job", "") == "CAREER_SITE"


PROFILE = {
    "target_roles": [
        "Network Technician",
        "IT Support Specialist",
        "Systems Administrator",
    ]
}


def test_score_job_relevant_role_increases_score():
    base = scouter.score_job("https://company.com/jobs/unrelated-role", "", PROFILE)
    score = scouter.score_job("https://company.com/jobs/network-technician", "Network Technician role in Atlanta", PROFILE)
    assert score > base


def test_score_job_remote_location_bonus():
    score_remote = scouter.score_job("https://company.com/jobs/123", "Remote IT Support Specialist", PROFILE)
    score_no_loc = scouter.score_job("https://company.com/jobs/123", "IT Support Specialist", PROFILE)
    assert score_remote >= score_no_loc


def test_score_job_executive_penalty():
    score = scouter.score_job("https://company.com/jobs/123", "Vice President of IT Infrastructure", PROFILE)
    assert score < 40


def test_score_job_intern_penalty():
    score = scouter.score_job("https://company.com/jobs/123", "IT Support Internship Summer 2025", PROFILE)
    assert score < 40


def test_score_job_clamps_between_0_and_100():
    score = scouter.score_job("https://company.com/jobs/123", "", PROFILE)
    assert 0 <= score <= 100
