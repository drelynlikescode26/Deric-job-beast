#!/usr/bin/env python3
"""Single-link browser tester for the Auto-Applier project."""
import argparse
import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
PROFILE_PATH = ROOT / "profile.json"
QUEUE_PATH = ROOT / "queue.json"
STATE_PATH = ROOT / "state_tracker.json"
FAILED_PATH = ROOT / "failed_jobs.txt"
SCREENSHOT_DIR = ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def record_failure(url, reason):
    with open(FAILED_PATH, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{url}\t{reason}\n")


def pick_url(cli_url):
    if cli_url:
        return cli_url
    queue = read_json(QUEUE_PATH, [])
    if queue:
        first = queue[0]
        return first.get("url") if isinstance(first, dict) else first
    return None


def main():
    parser = argparse.ArgumentParser(description="Single-link browser tester")
    parser.add_argument("--url", help="Job URL to test", default=None)
    parser.add_argument("--headless", action="store_true", help="Run headless")
    args = parser.parse_args()

    profile = read_json(PROFILE_PATH, {})
    resume_path = profile.get("resume_path")
    if not resume_path or not Path(resume_path).exists():
        print("resume_path missing or not found in profile.json; set an absolute path to a PDF")
        return

    url = pick_url(args.url)
    if not url:
        print("No URL provided and queue.json is empty. Pass --url or add a URL to queue.json.")
        return

    print(f"Testing URL: {url}")
    profile_dir = os.getenv("BROWSER_PROFILE_PATH")

    try:
        with sync_playwright() as p:
            if profile_dir:
                context = p.chromium.launch_persistent_context(user_data_dir=profile_dir, headless=args.headless)
                page = context.new_page()
            else:
                browser = p.chromium.launch(headless=args.headless)
                page = browser.new_page()

            page.set_default_navigation_timeout(120000)
            page.goto(url)
            time.sleep(2)

            file_inputs = page.query_selector_all('input[type="file"]')
            if not file_inputs:
                print("No file input found on page. Taking screenshot for inspection.")
            else:
                for idx, field in enumerate(file_inputs, start=1):
                    try:
                        field.set_input_files(resume_path)
                        print(f"Set resume file on input #{idx}")
                    except Exception as e:
                        print(f"Failed to set file on input #{idx}: {e}")

            try:
                submit = page.query_selector('button[type="submit"], input[type="submit"]')
                if submit:
                    submit.click()
                    print("Clicked submit button.")
            except Exception:
                print("Could not click submit button.")

            screenshot_path = SCREENSHOT_DIR / f"browser_tester_{int(time.time())}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Saved screenshot: {screenshot_path}")

            states = read_json(STATE_PATH, [])
            if url not in states:
                states.append(url)
                write_json(STATE_PATH, states)
                print("Recorded URL in state_tracker.json")

            try:
                if profile_dir:
                    context.close()
                else:
                    browser.close()
            except Exception:
                pass

    except Exception as e:
        print(f"Error during test: {e}")
        record_failure(url, str(e))


if __name__ == '__main__':
    main()
