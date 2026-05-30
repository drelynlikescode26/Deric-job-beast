#!/usr/bin/env python3
"""Executor: processes queued jobs and applies using Playwright automation."""
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
PROFILE_PATH = ROOT / "profile.json"
QUEUE_PATH = ROOT / "queue.json"
STATE_PATH = ROOT / "state_tracker.json"
ACCOUNTS_PATH = ROOT / "accounts.json"
FAILED_PATH = ROOT / "failed_jobs.txt"
SCREENSHOT_DIR = ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

from telegram_bot import send_message, send_photo


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, value):
    with open(path, "w") as f:
        json.dump(value, f, indent=2)


def append_failed(url, reason):
    with open(FAILED_PATH, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{url}\t{reason}\n")


def generate_credentials(profile):
    base_email = profile.get("email", "applicant@example.com")
    if "@" in base_email:
        local, domain = base_email.split("@", 1)
    else:
        local, domain = base_email, "example.com"
    email = f"{local}+{int(time.time())}@{domain}"
    password = secrets.token_urlsafe(12)
    return email, password


def fill_common_fields(page, profile, email, password):
    fields = {
        "input[name='email']": email,
        "input[name='username']": email,
        "input[name='password']": password,
        "input[name='confirm_password']": password,
        "input[name='first_name']": profile.get("first_name", profile.get("name", "")),
        "input[name='last_name']": profile.get("last_name", ""),
        "input[name='phone']": profile.get("phone", ""),
    }
    for selector, value in fields.items():
        try:
            if page.query_selector(selector):
                page.fill(selector, value)
        except Exception:
            pass


def upload_resume(page, resume_path):
    file_inputs = page.query_selector_all("input[type='file']")
    for field in file_inputs:
        try:
            field.set_input_files(resume_path)
        except Exception:
            pass


def safe_click(page, query):
    try:
        element = page.query_selector(query)
        if element:
            element.click()
            time.sleep(1)
            return True
    except Exception:
        pass
    return False


def has_confirmation(page):
    text = page.content().lower()
    return any(substring in text for substring in ["thank you", "application submitted", "confirmation", "we received your application"])


def process_linkedin(page, resume_path):
    if safe_click(page, "button:has-text('Easy Apply'), a:has-text('Easy Apply')"):
        pass
    upload_resume(page, resume_path)
    if safe_click(page, "button:has-text('Submit application'), button:has-text('Submit'), button:has-text('Review'), button:has-text('Save')"):
        return True, "submitted"
    if safe_click(page, "button:has-text('Next'), button:has-text('Continue')"):
        upload_resume(page, resume_path)
        if safe_click(page, "button:has-text('Submit'), button:has-text('Submit application')"):
            return True, "submitted"
    return False, "linkedin-no-submit"


def process_workday(page, profile, resume_path, email, password):
    fill_common_fields(page, profile, email, password)
    upload_resume(page, resume_path)
    if safe_click(page, "button:has-text('Apply'), button:has-text('Submit')"):
        return True, "submitted"
    if safe_click(page, "button:has-text('Continue')"):
        upload_resume(page, resume_path)
        if safe_click(page, "button:has-text('Submit')"):
            return True, "submitted"
    return False, "workday-no-submit"


def process_taleo(page, profile, resume_path, email, password):
    fill_common_fields(page, profile, email, password)
    upload_resume(page, resume_path)
    if safe_click(page, "button:has-text('Submit application'), button:has-text('Submit'), button:has-text('Apply')"):
        return True, "submitted"
    return False, "taleo-no-submit"


def process_generic_career_site(page, profile, resume_path, email, password):
    fill_common_fields(page, profile, email, password)
    upload_resume(page, resume_path)
    if safe_click(page, "button:has-text('Submit'), button:has-text('Apply'), input[type='submit']"):
        return True, "submitted"
    return False, "generic-no-submit"


def choose_executor(page, url, profile, resume_path):
    if "linkedin.com/jobs" in url:
        result, reason = process_linkedin(page, resume_path)
        return result, reason, None, None
    if "workday" in url:
        email, password = generate_credentials(profile)
        result, reason = process_workday(page, profile, resume_path, email, password)
        return result, reason, email, password
    if "taleo" in url:
        email, password = generate_credentials(profile)
        result, reason = process_taleo(page, profile, resume_path, email, password)
        return result, reason, email, password
    email, password = generate_credentials(profile)
    result, reason = process_generic_career_site(page, profile, resume_path, email, password)
    return result, reason, email, password


def record_account(url, email, password):
    host = urlparse(url).hostname or "unknown"
    accounts = read_json(ACCOUNTS_PATH, {})
    accounts.setdefault(host, []).append({
        "email": email,
        "password": password,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    write_json(ACCOUNTS_PATH, accounts)


def run_executor():
    profile = read_json(PROFILE_PATH, {})
    resume_path = profile.get("resume_path")
    if not resume_path or not Path(resume_path).exists():
        send_message("Executor: resume_path missing or not found in profile.json.")
        return

    queue = read_json(QUEUE_PATH, [])
    if not queue:
        send_message("Executor: queue.json is empty.")
        return

    states = set(read_json(STATE_PATH, []))
    profile_dir = os.getenv("BROWSER_PROFILE_PATH")

    for item in queue:
        url = item["url"] if isinstance(item, dict) else item
        job_type = item.get("type", "EASY_APPLY") if isinstance(item, dict) else "EASY_APPLY"
        if url in states:
            continue

        start_ts = time.time()
        try:
            with sync_playwright() as p:
                if profile_dir:
                    context = p.chromium.launch_persistent_context(user_data_dir=profile_dir, headless=True)
                else:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context()
                page = context.new_page()
                page.set_default_navigation_timeout(120000)
                page.goto(url)
                time.sleep(2)

                result = False
                reason = "unknown"
                account_email = None
                account_password = None
                account_email = None
                account_password = None
                if "linkedin.com/jobs" in url:
                    result, reason = process_linkedin(page, resume_path)
                elif "workday" in url or "taleo" in url:
                    result, reason, account_email, account_password = choose_executor(page, url, profile, resume_path)
                    if result and account_email and account_password:
                        record_account(url, account_email, account_password)
                else:
                    if job_type == "EASY_APPLY":
                        if "linkedin.com/jobs" in url:
                            result, reason = process_linkedin(page, resume_path)
                        else:
                            email, password = generate_credentials(profile)
                            result, reason = process_generic_career_site(page, profile, resume_path, email, password)
                            if result:
                                record_account(url, email, password)
                    else:
                        result, reason, account_email, account_password = choose_executor(page, url, profile, resume_path)
                        if result and account_email and account_password:
                            record_account(url, account_email, account_password)

                screenshot_path = SCREENSHOT_DIR / f"{int(time.time())}.png"
                try:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                except Exception:
                    pass

                if result:
                    states.add(url)
                    write_json(STATE_PATH, list(states))
                    send_photo(str(screenshot_path), caption=f"Applied: {url}")
                else:
                    append_failed(url, reason)
                    send_message(f"Failed to apply to {url}: {reason}")

                try:
                    context.close()
                except Exception:
                    pass
                if not profile_dir:
                    browser.close()
        except Exception as e:
            append_failed(url, str(e))
            send_message(f"Executor error for {url}: {e}")

        if time.time() - start_ts > 300:
            append_failed(url, "timeout")
            send_message(f"Executor timed out on {url}")

    write_json(QUEUE_PATH, [])


if __name__ == '__main__':
    run_executor()
