#!/usr/bin/env python3
"""Scouter: discover job URLs from configured targets, enforce quotas, and update the queue."""
import asyncio
import json
import os
import random
import time
from pathlib import Path
from urllib.parse import urljoin

from dotenv import load_dotenv
from playwright.async_api import async_playwright

try:
    from browser_use import Agent
    from langchain_openai import ChatOpenAI
    from browser_use.browser.browser import Browser, BrowserConfig
except Exception:
    Agent = None
    ChatOpenAI = None
    Browser = None
    BrowserConfig = None

load_dotenv()

ROOT = Path(__file__).parent
PROFILE_PATH = ROOT / "profile.json"
QUEUE_PATH = ROOT / "queue.json"
STATE_PATH = ROOT / "state_tracker.json"
BROWSER_PROFILE_PATH = ROOT / "chrome_profile"
BROWSER_PROFILE_PATH.mkdir(exist_ok=True)

from telegram_bot import send_message


def get_browser_profile_path():
    env_path = os.getenv("BROWSER_PROFILE_PATH")
    if env_path:
        profile_dir = Path(env_path)
    else:
        profile_dir = BROWSER_PROFILE_PATH
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, value):
    with open(path, "w") as f:
        json.dump(value, f, indent=2)


def get_chrome_path():
    return os.getenv("CHROME_PATH") or os.getenv("chrome_path")


def get_chrome_cdp_url():
    return os.getenv("CHROME_CDP_URL") or os.getenv("BROWSER_CDP_URL")


def normalize_link(base, href):
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href.split("#")[0]
    return urljoin(base, href).split("#")[0]


CAREER_SITE_KEYWORDS = (
    "workday", "myworkdayjobs", "taleo", "icims", "greenhouse",
    "lever.co", "smartrecruiters", "jobvite", "breezy", "bamboohr",
    "successfactors", "ultipro", "silkroad", "applicantpro", "oracle.com/hcm",
)


def classify_link(url, page_text):
    u = url.lower()
    text = page_text.lower()
    if "linkedin.com/jobs/view" in u or "/jobs/view/" in u:
        return "EASY_APPLY"
    if "easy apply" in text:
        return "EASY_APPLY"
    for kw in CAREER_SITE_KEYWORDS:
        if kw in u:
            return "CAREER_SITE"
    if "apply now" in text or "apply for this" in text:
        return "CAREER_SITE"
    return "CAREER_SITE"


def score_job(url, page_text, profile):
    """Score 0–100: how closely the job matches target roles and preferred locations."""
    score = 40
    target_roles = profile.get("target_roles", [])
    combined = (url + " " + page_text).lower()

    for role in target_roles:
        for word in role.lower().split():
            if len(word) > 3 and word in combined:
                score += 6
                break

    for loc_word in ("athens", "atlanta", "remote", "hybrid"):
        if loc_word in combined:
            score += 4

    for penalty in ("senior director", "vp ", "vice president", "executive director", "internship", "intern "):
        if penalty in combined:
            score -= 40
            break

    return max(0, min(100, score))


def is_job_link(url):
    job_markers = ["/jobs/", "/careers/", "apply", "requisition", "job/", "viewjob"]
    lower = url.lower()
    return any(marker in lower for marker in job_markers)


async def maybe_await(value):
    if asyncio.iscoroutine(value):
        return await value
    return value


async def page_content(page):
    return await maybe_await(page.content())


async def page_goto(page, target_url):
    return await maybe_await(page.goto(target_url))


async def collect_links(page, target_url):
    anchors = await maybe_await(page.query_selector_all("a[href]"))
    links = []
    for anchor in anchors:
        href = await maybe_await(anchor.get_attribute("href"))
        link = normalize_link(target_url, href)
        if not link:
            continue
        if not is_job_link(link):
            continue
        links.append(link)
    return list(dict.fromkeys(links))


SCOUT_AI_PROMPT = """
You are an expert job board scanner. Review the page content and return only a JSON array of job objects.
Each object must include:
- title
- url
- type (EASY_APPLY or CAREER_SITE)
- level (junior, mid, senior, director, executive)

Only include roles that match IT infrastructure, networking, systems, or operations.
Do not include senior director, VP, executive, or internship roles.
Ignore roles unrelated to networking and infrastructure.
Return direct application URLs; do not invent URLs.
"""


def browser_agent_available():
    return Agent is not None and ChatOpenAI is not None


def build_browser_use_browser():
    cdp_url = get_chrome_cdp_url()
    if not cdp_url or Browser is None or BrowserConfig is None:
        return None
    return Browser(config=BrowserConfig(cdp_url=cdp_url))


async def run_browser_scouter(task: str):
    if not browser_agent_available():
        return []
    llm = ChatOpenAI(model="gpt-4o-mini")
    browser = build_browser_use_browser()
    agent_kwargs = {"task": task, "llm": llm}
    if browser:
        agent_kwargs["browser"] = browser
    agent = Agent(**agent_kwargs)
    result = agent.run()
    if asyncio.iscoroutine(result):
        result = await result
    if hasattr(result, "final_result"):
        return result.final_result()
    return str(result)


def parse_ai_job_links(text: str):
    try:
        data = json.loads(text)
        if isinstance(data, list):
            jobs = []
            for item in data:
                if isinstance(item, dict) and item.get("url"):
                    jobs.append(item)
            return jobs
    except Exception:
        pass
    return []


async def ai_extract_job_links(page, target, profile):
    if not browser_agent_available():
        return []
    page_html = await page_content(page)
    task = f"Profile Context:\n{json.dumps(profile, indent=2)}\n\nTask:\n{SCOUT_AI_PROMPT}\n\nPage HTML:\n{page_html}\n\nBase URL:{target}"
    try:
        response = await run_browser_scouter(task)
        return parse_ai_job_links(response)
    except Exception:
        return []


def scout_once():
    return asyncio.run(scout_once_async())


async def scout_once_async():
    profile = read_json(PROFILE_PATH, {})
    targets = profile.get("targets", [])
    if not targets:
        send_message("Scouter: no targets configured in profile.json.")
        return []

    raw_state = read_json(STATE_PATH, [])
    existing = set(
        item if isinstance(item, str) else item.get("url", "")
        for item in raw_state
    )
    queued = read_json(QUEUE_PATH, [])
    queued_urls = {item["url"] if isinstance(item, dict) else item for item in queued}

    easy_limit = 2
    career_limit = 1
    easy_count = 0
    career_count = 0
    results = []

    chrome_path = get_chrome_path()
    cdp_url = get_chrome_cdp_url()
    browser_handle = None
    context = None
    page = None

    try:
        if Browser and BrowserConfig and chrome_path and not cdp_url:
            browser_handle = Browser(
                config=BrowserConfig(
                    headless=False,
                    chrome_instance_path=chrome_path,
                    extra_browser_args=[f"--user-data-dir={str(get_browser_profile_path())}"],
                )
            )
            context = browser_handle.new_context() if hasattr(browser_handle, "new_context") else browser_handle
            page = context.new_page()
            page.set_default_navigation_timeout(60000)

            for target in targets:
                try:
                    await page_goto(page, target)
                    await asyncio.sleep(random.uniform(4, 8))
                    if browser_agent_available():
                        ai_jobs = await ai_extract_job_links(page, target, profile)
                        candidate_links = [job["url"] for job in ai_jobs if job.get("url")]
                    else:
                        candidate_links = await collect_links(page, target)

                    scored = []
                    for link in candidate_links:
                        if link in existing or link in queued_urls:
                            continue
                        if any(link.lower().endswith(ext) for ext in [".jpg", ".png", ".pdf", ".zip"]):
                            continue
                        try:
                            await page_goto(page, link)
                            await asyncio.sleep(random.uniform(4, 12))
                            page_text = await page_content(page)
                        except Exception:
                            page_text = ""
                        typ = classify_link(link, page_text)
                        job_score = score_job(link, page_text, profile)
                        scored.append((job_score, link, typ))

                    scored.sort(key=lambda x: x[0], reverse=True)

                    for job_score, link, typ in scored:
                        if typ == "EASY_APPLY" and easy_count < easy_limit:
                            results.append({"url": link, "type": typ, "source": "scouter", "score": job_score})
                            easy_count += 1
                        elif typ == "CAREER_SITE" and career_count < career_limit:
                            results.append({"url": link, "type": typ, "source": "scouter", "score": job_score})
                            career_count += 1
                        if easy_count >= easy_limit and career_count >= career_limit:
                            break
                    if easy_count >= easy_limit and career_count >= career_limit:
                        break
                except Exception:
                    continue
        else:
            profile_dir = get_browser_profile_path()
            async with async_playwright() as playwright:
                if cdp_url:
                    browser_handle = await playwright.chromium.connect_over_cdp(cdp_url)
                    if browser_handle.contexts:
                        context = browser_handle.contexts[0]
                    else:
                        context = await browser_handle.new_context()
                    page = context.pages[0] if context.pages else await context.new_page()
                else:
                    context = await playwright.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        headless=False,
                        executable_path=chrome_path if chrome_path else None,
                    )
                    page = await context.new_page()
                page.set_default_navigation_timeout(60000)

                for target in targets:
                    try:
                        await page_goto(page, target)
                        await asyncio.sleep(random.uniform(4, 8))
                        if browser_agent_available():
                            ai_jobs = await ai_extract_job_links(page, target, profile)
                            candidate_links = [job["url"] for job in ai_jobs if job.get("url")]
                        else:
                            candidate_links = await collect_links(page, target)

                        scored = []
                        for link in candidate_links:
                            if link in existing or link in queued_urls:
                                continue
                            if any(link.lower().endswith(ext) for ext in [".jpg", ".png", ".pdf", ".zip"]):
                                continue
                            try:
                                await page_goto(page, link)
                                await asyncio.sleep(random.uniform(4, 12))
                                page_text = await page_content(page)
                            except Exception:
                                page_text = ""
                            typ = classify_link(link, page_text)
                            job_score = score_job(link, page_text, profile)
                            scored.append((job_score, link, typ))

                        scored.sort(key=lambda x: x[0], reverse=True)

                        for job_score, link, typ in scored:
                            if typ == "EASY_APPLY" and easy_count < easy_limit:
                                results.append({"url": link, "type": typ, "source": "scouter", "score": job_score})
                                easy_count += 1
                            elif typ == "CAREER_SITE" and career_count < career_limit:
                                results.append({"url": link, "type": typ, "source": "scouter", "score": job_score})
                                career_count += 1
                            if easy_count >= easy_limit and career_count >= career_limit:
                                break
                        if easy_count >= easy_limit and career_count >= career_limit:
                            break
                    except Exception:
                        continue

        queued.extend(results)
        write_json(QUEUE_PATH, queued)
        send_message(
            f"Scouting complete. I found {easy_count} Easy Applies and {career_count} Career Site roles. Reply 'RUN' to execute the queue."
        )
        return results
    finally:
        try:
            if context and not get_chrome_cdp_url() and hasattr(context, "close"):
                await maybe_await(context.close())
        except Exception:
            pass
        try:
            if browser_handle and not get_chrome_cdp_url() and hasattr(browser_handle, "stop"):
                await maybe_await(browser_handle.stop())
        except Exception:
            pass


if __name__ == '__main__':
    scout_once()
