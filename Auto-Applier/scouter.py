#!/usr/bin/env python3
"""Scouter: discover job URLs from configured targets, enforce quotas, and update the queue."""
import json
import time
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
PROFILE_PATH = ROOT / "profile.json"
QUEUE_PATH = ROOT / "queue.json"
STATE_PATH = ROOT / "state_tracker.json"

from telegram_bot import send_message


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, value):
    with open(path, "w") as f:
        json.dump(value, f, indent=2)


def normalize_link(base, href):
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href.split("#")[0]
    return urljoin(base, href).split("#")[0]


def classify_link(url, page_text):
    u = url.lower()
    text = page_text.lower()
    if "linkedin.com/jobs/view" in u or "/jobs/view/" in u or "easy apply" in u or "easy apply" in text:
        return "EASY_APPLY"
    if "workday" in u or "taleo" in u or "icims" in u or "greenhouse" in u or "lever" in u:
        return "CAREER_SITE"
    if "easy apply" in text or "apply now" in text:
        return "EASY_APPLY"
    return "CAREER_SITE"


def is_job_link(url):
    job_markers = ["/jobs/", "/careers/", "apply", "requisition", "job/", "viewjob"]
    lower = url.lower()
    return any(marker in lower for marker in job_markers)


def schedule_target_links(page, target):
    anchors = page.query_selector_all("a[href]")
    links = []
    for anchor in anchors:
        href = anchor.get_attribute("href")
        link = normalize_link(target, href)
        if not link:
            continue
        if not is_job_link(link):
            continue
        links.append(link)
    return list(dict.fromkeys(links))


def scout_once():
    profile = read_json(PROFILE_PATH, {})
    targets = profile.get("targets", [])
    if not targets:
        send_message("Scouter: no targets configured in profile.json.")
        return []

    existing = set(read_json(STATE_PATH, []))
    queued = read_json(QUEUE_PATH, [])
    queued_urls = {item["url"] if isinstance(item, dict) else item for item in queued}

    easy_limit = 15
    career_limit = 5
    easy_count = 0
    career_count = 0
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_navigation_timeout(60000)

        for target in targets:
            try:
                page.goto(target)
                time.sleep(2)
                candidate_links = schedule_target_links(page, target)
                for link in candidate_links:
                    if link in existing or link in queued_urls:
                        continue
                    if any(link.lower().endswith(ext) for ext in [".jpg", ".png", ".pdf", ".zip"]):
                        continue
                    try:
                        page.goto(link)
                        time.sleep(1)
                        page_text = page.content()
                    except Exception:
                        page_text = ""
                    typ = classify_link(link, page_text)
                    if typ == "EASY_APPLY" and easy_count < easy_limit:
                        results.append({"url": link, "type": typ, "source": "scouter"})
                        easy_count += 1
                    elif typ == "CAREER_SITE" and career_count < career_limit:
                        results.append({"url": link, "type": typ, "source": "scouter"})
                        career_count += 1
                    if easy_count >= easy_limit and career_count >= career_limit:
                        break
                if easy_count >= easy_limit and career_count >= career_limit:
                    break
            except Exception:
                continue

        browser.close()

    queued.extend(results)
    write_json(QUEUE_PATH, queued)
    send_message(f"Scouting complete. I found {easy_count} Easy Applies and {career_count} Career Site roles. Reply 'RUN' to execute the queue.")
    return results


if __name__ == '__main__':
    scout_once()
