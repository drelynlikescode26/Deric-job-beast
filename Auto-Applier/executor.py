#!/usr/bin/env python3
"""Executor: processes queued jobs and applies using Playwright or browser-use with prompt routing."""
import asyncio
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

try:
    from browser_use import Agent
    from browser_use.browser.browser import Browser, BrowserConfig
    from langchain_openai import ChatOpenAI
except Exception:
    Agent = None
    Browser = None
    BrowserConfig = None
    ChatOpenAI = None

load_dotenv()

ROOT = Path(__file__).parent
PROFILE_PATH = ROOT / "profile.json"
QUEUE_PATH = ROOT / "queue.json"
STATE_PATH = ROOT / "state_tracker.json"
ACCOUNTS_PATH = ROOT / "accounts.json"
FAILED_PATH = ROOT / "failed_jobs.txt"
SCREENSHOT_DIR = ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)
BROWSER_PROFILE_PATH = ROOT / "chrome_profile"
BROWSER_PROFILE_PATH.mkdir(exist_ok=True)

from telegram_bot import send_message, send_photo


def get_chrome_cdp_url():
    return os.getenv("CHROME_CDP_URL") or os.getenv("BROWSER_CDP_URL")


def get_browser_profile_path():
    env_path = os.getenv("BROWSER_PROFILE_PATH")
    if env_path:
        profile_dir = Path(env_path)
    else:
        profile_dir = BROWSER_PROFILE_PATH
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def get_or_create_page(context):
    if context.pages:
        return context.pages[0]
    return context.new_page()


def connect_playwright_context(playwright, cdp_url, profile_dir, chrome_path):
    browser = None
    if cdp_url:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        if browser.contexts:
            return browser, browser.contexts[0]
        return browser, browser.new_context()
    if profile_dir:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            executable_path=chrome_path if chrome_path else None,
        )
        return None, context
    browser = playwright.chromium.launch(headless=False, executable_path=chrome_path if chrome_path else None)
    return browser, browser.new_context()


def close_playwright_session(browser, context, cdp_url):
    try:
        if context and not cdp_url:
            context.close()
    except Exception:
        pass
    try:
        if browser and not cdp_url:
            browser.close()
    except Exception:
        pass

WORKDAY_PROMPT_TEMPLATE = """
You are an expert autonomous application assistant. Your goal is to apply for the job at the current URL using the provided profile data.

CRITICAL LOGIN RULES - AVOID GOOGLE SSO:
- NEVER click "Continue with Google", "Sign in with Google", or "Apply with LinkedIn".
- ALWAYS look for and click "Apply Manually", "Use Email and Password", "Create Account", or "Register".
- If presented with a choice, choose the native email/password account creation route.

CRITICAL WORKDAY INSTRUCTIONS:
1. LOOK FOR ACCESS GATE: Look at the page. If you see 'Sign In', 'Apply', or 'Apply Manually' button, click it.
2. ACCOUNT CREATION: If prompted to log in or create an account, click 'Create Account' or 'Sign Up' and complete registration.
3. CREDENTIAL GENERATION:
   - Use the primary email provided in the profile: {email}
   - Generate a unique, random, strong password using uppercase, lowercase, numbers, and symbols.
   - IMPORTANT: Output the generated password clearly in the final response as 'Generated Password: <password>'.
4. FORM COMPLETION:
   - Personal Info: Use profile details exactly.
   - Current Employment: Use the current employer data exactly as provided.
   - Certifications: Answer the CompTIA Network+ N10-009 certification question as "In progress" or "Studying" if asked.
   - EEO/Demographics: Use the exact string values from profile.eeo and do not guess.
5. RESUME UPLOAD: When you reach resume upload, use the backend file injector and attach the file at '{resume_path}'.
6. SUBMIT & RECEIPT: Complete the application flow, click the final submit button, and wait for a confirmation screen such as 'Application Submitted' or 'Thank You'.
7. FINAL RESPONSE: At the end, output only a short confirmation message and include the generated password exactly as: 'Generated Password: <password>'.
"""

TALEO_PROMPT_TEMPLATE = """
You are an expert autonomous application assistant. The URL is on Taleo or a legacy career portal.
CRITICAL LOGIN RULES - AVOID GOOGLE SSO:
- NEVER click "Continue with Google", "Sign in with Google", or "Apply with LinkedIn".
- ALWAYS look for and click "Apply Manually", "Use Email and Password", "Create Account", or "Register".
1. If prompted to sign in, find and click 'Create Account' or 'Register'.
2. Use the profile data to fill the registration form.
3. Use the generated email and password, and store the password clearly as 'Generated Password: <password>'.
4. Upload the resume from '{resume_path}'.
5. Submit the application and wait for a confirmation screen.
"""

GENERIC_PROMPT_TEMPLATE = """
You are an intelligent job application assistant. Use the provided profile data to complete the application.
CRITICAL LOGIN RULES - AVOID GOOGLE SSO:
- NEVER click "Continue with Google", "Sign in with Google", or "Apply with LinkedIn".
- ALWAYS look for and click "Apply Manually", "Use Email and Password", "Create Account", or "Register".
- If presented with a login choice, choose the native email/password route.
- If there is a manual account creation path, prioritize it over SSO.
- Do not try to bypass Google SSO with the browser debugger.
- Use the provided profile information and generated credentials instead.
- If this is a credential creation flow, output 'Generated Password: <password>' in the final response.
- If there is a resume upload, attach '{resume_path}'.
- Do not invent answers for EEO or certification questions.
"""

GREENHOUSE_PROMPT_TEMPLATE = """
You are an expert autonomous application assistant. The URL is on Greenhouse (greenhouse.io or boards.greenhouse.io).
CRITICAL RULES:
- Greenhouse typically does NOT require account creation — fill the application form directly.
- NEVER click "Apply with LinkedIn" or "Apply with Google".
- Always use the standard form fields.
1. Click "Apply for this Job" or the primary Apply button.
2. Fill all required fields (name, email, phone, address) using profile data.
3. Upload the resume from '{resume_path}'.
4. Complete any voluntary demographic/EEO sections using profile.eeo values.
5. Answer any free-text questions clearly and professionally using profile data.
6. Click the final Submit button and wait for a confirmation page.
"""

LEVER_PROMPT_TEMPLATE = """
You are an expert autonomous application assistant. The URL is on Lever (lever.co or jobs.lever.co).
CRITICAL RULES:
- NEVER use "Apply with LinkedIn" or Google SSO.
- Lever typically shows an inline application form — no account creation needed.
1. Click "Apply" or "Apply for this position".
2. Fill all visible fields (name, email, phone, LinkedIn, resume) using profile data.
3. Upload resume from '{resume_path}'.
4. Answer any additional written questions using profile data.
5. Submit the application and wait for a confirmation message.
"""

ICIMS_PROMPT_TEMPLATE = """
You are an expert autonomous application assistant. The URL is on an iCIMS career portal.
CRITICAL LOGIN RULES - AVOID GOOGLE SSO:
- NEVER click "Continue with Google", "Sign in with Google", or "Apply with LinkedIn".
- Look for "Apply Now", "Create Profile", "Sign Up", or "Register" with email and password.
1. Create a new iCIMS profile using the email: {email} and a newly generated strong password.
2. IMPORTANT: Output the generated password clearly in your final response as 'Generated Password: <password>'.
3. Fill all profile sections (personal info, work history, education) using profile data.
4. Upload resume from '{resume_path}'.
5. Complete EEO questions using profile.eeo values.
6. Submit the application and wait for a confirmation screen.
"""

SMARTRECRUITERS_PROMPT_TEMPLATE = """
You are an expert autonomous application assistant. The URL is on SmartRecruiters.
CRITICAL RULES:
- NEVER use Google SSO or LinkedIn SSO.
- SmartRecruiters may allow applying as a guest or with email registration.
1. Click "Apply" or "Apply Now". Choose guest or email-based flow.
2. Fill all required fields using profile data.
3. Upload resume from '{resume_path}'.
4. Complete EEO sections using profile.eeo values.
5. Submit and wait for confirmation.
"""


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, value):
    with open(path, "w") as f:
        json.dump(value, f, indent=2)


def resolve_resume_path(profile):
    """Resolve resume: try explicit path first, then find the latest PDF in resume_folder."""
    explicit_path = profile.get("resume_path")
    if explicit_path:
        expanded = Path(os.path.expanduser(explicit_path))
        if expanded.exists():
            return str(expanded)

    folder = profile.get("resume_folder")
    if folder:
        folder_path = Path(os.path.expanduser(folder))
        if folder_path.is_dir():
            pdfs = sorted(folder_path.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
            if pdfs:
                return str(pdfs[0])

    return explicit_path


def append_failed(url, reason):
    with open(FAILED_PATH, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{url}\t{reason}\n")


def with_retry(fn, retries=3, delay=2, backoff=2):
    """Call fn(), retrying up to `retries` times with exponential backoff on any exception."""
    last_exc = None
    wait = delay
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(wait)
                wait *= backoff
    raise last_exc


def safe_goto(page, url, retries=2):
    """Navigate to url with retries on transient failures."""
    def go():
        page.goto(url)
        time.sleep(2)
    with_retry(go, retries=retries, delay=3)


def load_states():
    """Load state_tracker.json, normalizing both old (list of strings) and new (list of dicts) formats."""
    raw = read_json(STATE_PATH, [])
    states = {}
    for item in raw:
        if isinstance(item, str):
            states[item] = {"url": item, "applied_at": None, "company": None, "status": "applied", "type": None}
        elif isinstance(item, dict) and item.get("url"):
            states[item["url"]] = item
    return states


def save_states(states):
    write_json(STATE_PATH, list(states.values()))


def mark_applied_state(states, url, job_type=None):
    company = urlparse(url).hostname or "unknown"
    states[url] = {
        "url": url,
        "applied_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "company": company,
        "status": "applied",
        "type": job_type,
    }


def browser_agent_available():
    return Agent is not None and ChatOpenAI is not None


def build_browser_use_browser():
    cdp_url = get_chrome_cdp_url()
    if not cdp_url or Browser is None or BrowserConfig is None:
        return None
    return Browser(config=BrowserConfig(cdp_url=cdp_url))


def generate_credentials(profile):
    base_email = profile.get("contact_info", {}).get("email", "applicant@example.com")
    if "@" in base_email:
        local, domain = base_email.split("@", 1)
    else:
        local, domain = base_email, "example.com"
    email = f"{local}+{int(time.time())}@{domain}"
    password = secrets.token_urlsafe(12)
    return email, password


def save_account_credentials(company_name, email, password):
    accounts = read_json(ACCOUNTS_PATH, {})
    accounts.setdefault(company_name, []).append({
        "email": email,
        "password": password,
        "status": "Created",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    write_json(ACCOUNTS_PATH, accounts)


def parse_generated_password(text):
    if not text:
        return None
    for line in text.splitlines():
        if "Generated Password:" in line:
            return line.split("Generated Password:", 1)[1].strip()
        if "Password:" in line:
            return line.split("Password:", 1)[1].strip()
    return None


def build_agent_task(url, profile):
    email = profile.get("contact_info", {}).get("email", "")
    resume_path = resolve_resume_path(profile) or profile.get("resume_path", "")
    u = url.lower()
    if "workday" in u or "myworkdayjobs" in u:
        prompt = WORKDAY_PROMPT_TEMPLATE.format(email=email, resume_path=resume_path)
    elif "taleo" in u:
        prompt = TALEO_PROMPT_TEMPLATE.format(resume_path=resume_path)
    elif "greenhouse" in u:
        prompt = GREENHOUSE_PROMPT_TEMPLATE.format(resume_path=resume_path)
    elif "lever.co" in u:
        prompt = LEVER_PROMPT_TEMPLATE.format(resume_path=resume_path)
    elif "icims" in u:
        prompt = ICIMS_PROMPT_TEMPLATE.format(email=email, resume_path=resume_path)
    elif "smartrecruiters" in u:
        prompt = SMARTRECRUITERS_PROMPT_TEMPLATE.format(resume_path=resume_path)
    else:
        prompt = GENERIC_PROMPT_TEMPLATE.format(resume_path=resume_path)
    return f"Profile Context:\n{json.dumps(profile, indent=2)}\n\nTask:\n{prompt}\n\nTarget URL: {url}"


async def run_browser_agent(task, resume_path):
    if not browser_agent_available():
        raise RuntimeError("browser_use or langchain_openai is not installed")

    llm = ChatOpenAI(model="gpt-4o-mini")
    browser = build_browser_use_browser()
    agent_kwargs = {
        "task": task,
        "llm": llm,
        "available_file_paths": [resume_path],
    }
    if browser:
        agent_kwargs["browser"] = browser
    agent = Agent(**agent_kwargs)

    try:
        maybe_response = await asyncio.wait_for(asyncio.to_thread(agent.run), timeout=300)
        if asyncio.iscoroutine(maybe_response):
            response = await asyncio.wait_for(maybe_response, timeout=300)
        else:
            response = maybe_response
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError("browser agent timed out after 300 seconds")

    if hasattr(response, "final_result"):
        response = response.final_result()
    return str(response)


def resolve_agent_response(result):
    if isinstance(result, str):
        return result
    if hasattr(result, "final_result"):
        return result.final_result()
    return str(result)


def fill_common_fields(page, profile, email, password):
    info = profile.get("contact_info", profile)
    first = info.get("first_name") or info.get("name", "").split()[0] if info.get("name") else ""
    last = info.get("last_name") or (" ".join(info.get("name", "").split()[1:]) if info.get("name") else "")
    phone = info.get("phone", "")
    fields = {
        "input[name='email']": email,
        "input[name='username']": email,
        "input[name='password']": password,
        "input[name='confirm_password']": password,
        "input[name='confirmPassword']": password,
        "input[name='first_name']": first,
        "input[name='firstName']": first,
        "input[name='last_name']": last,
        "input[name='lastName']": last,
        "input[name='phone']": phone,
        "input[name='phoneNumber']": phone,
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


def process_generic_career_site(page, profile, resume_path, email, password):
    fill_common_fields(page, profile, email, password)
    upload_resume(page, resume_path)
    if safe_click(page, "button:has-text('Submit'), button:has-text('Apply'), input[type='submit']"):
        return True, "submitted"
    return False, "generic-no-submit"


def process_with_browser_agent(url, profile):
    task = build_agent_task(url, profile)
    resume_path = resolve_resume_path(profile) or profile.get("resume_path", "")

    def run():
        return asyncio.run(run_browser_agent(task, resume_path))

    try:
        response_text = with_retry(run, retries=2, delay=5)
    except asyncio.TimeoutError as e:
        return str(e), None
    except Exception as e:
        return f"browser agent error: {e}", None
    password = parse_generated_password(response_text)
    return response_text, password


def process_workday_fallback(page, profile, resume_path, email, password):
    fill_common_fields(page, profile, email, password)
    upload_resume(page, resume_path)
    if safe_click(page, "button:has-text('Apply'), button:has-text('Submit')"):
        return True, "submitted"
    if safe_click(page, "button:has-text('Continue')"):
        upload_resume(page, resume_path)
        if safe_click(page, "button:has-text('Submit')"):
            return True, "submitted"
    return False, "workday-no-submit"


def process_taleo_fallback(page, profile, resume_path, email, password):
    fill_common_fields(page, profile, email, password)
    upload_resume(page, resume_path)
    if safe_click(page, "button:has-text('Submit application'), button:has-text('Submit'), button:has-text('Apply')"):
        return True, "submitted"
    return False, "taleo-no-submit"


def record_account(url, email, password):
    company = urlparse(url).hostname or "unknown"
    save_account_credentials(company, email, password)


def run_executor():
    profile = read_json(PROFILE_PATH, {})
    resume_path = resolve_resume_path(profile)
    if not resume_path or not Path(resume_path).exists():
        send_message("Executor: resume_path missing or not found in profile.json.")
        return

    queue = read_json(QUEUE_PATH, [])
    if not queue:
        send_message("Executor: queue.json is empty.")
        return

    # Verification step: ensure the warmed Chrome profile is actually logged in
    def verify_profile_and_send(profile_dir, chrome_path, cdp_url, queued_urls):
        try:
            with sync_playwright() as p:
                browser, context = connect_playwright_context(p, cdp_url, profile_dir, chrome_path)
                page = get_or_create_page(context)
                page.set_default_navigation_timeout(60000)

                # Check Google login status
                google_ok = False
                try:
                    page.goto("https://www.google.com")
                    time.sleep(1)
                    # if 'Sign in' text is present, assume not signed in
                    body = page.content()
                    if "Sign in" not in body and "Sign in" not in (page.title() or ""):
                        google_ok = True
                except Exception:
                    pass

                # Check LinkedIn login status
                linkedin_ok = False
                try:
                    page.goto("https://www.linkedin.com/feed")
                    time.sleep(2)
                    # if redirected to login or url contains 'login', consider not signed in
                    cur_url = page.url or ""
                    body = page.content()
                    if "login" not in cur_url.lower() and "Sign in" not in body:
                        linkedin_ok = True
                except Exception:
                    pass

                # Take a screenshot for manual verification
                ts = int(time.time())
                shot_path = SCREENSHOT_DIR / f"pre_run_{ts}.png"
                try:
                    page.screenshot(path=str(shot_path), full_page=True)
                except Exception:
                    pass

                close_playwright_session(browser, context, cdp_url)

                summary = f"Verification results - Google:{google_ok} LinkedIn:{linkedin_ok}"
                send_message(f"Executor verification: using profile {str(profile_dir)}")
                send_message(summary)
                send_photo(str(shot_path), caption=f"Pre-run verification: {summary}")

                # If we have LinkedIn jobs queued but LinkedIn isn't signed in, abort
                if any("linkedin.com" in (u if isinstance(u, str) else u.get("url", "") ) for u in queued_urls) and not linkedin_ok:
                    send_message("Executor abort: LinkedIn appears not signed in in the warmed profile. Please run ./run.sh warmup and log in, then retry.")
                    return False

                return True
        except Exception as e:
            send_message(f"Executor verification error: {e}")
            return False

    profile_dir = get_browser_profile_path()
    chrome_path = os.getenv("CHROME_PATH")
    cdp_url = get_chrome_cdp_url()

    # Run verification before processing the queue
    ok = verify_profile_and_send(profile_dir, chrome_path, cdp_url, queue)
    if not ok:
        return

    states = load_states()
    profile_dir = get_browser_profile_path()
    chrome_path = os.getenv("CHROME_PATH")
    cdp_url = get_chrome_cdp_url()

    ATS_AGENT_KEYWORDS = ("workday", "myworkdayjobs", "taleo", "greenhouse", "lever.co", "icims", "smartrecruiters")

    for item in queue:
        url = item["url"] if isinstance(item, dict) else item
        job_type = item.get("type") if isinstance(item, dict) else None
        if url in states:
            continue

        start_ts = time.time()
        result = False
        reason = "unknown"
        screenshot_path = SCREENSHOT_DIR / f"{int(time.time())}.png"

        try:
            if any(k in url.lower() for k in ATS_AGENT_KEYWORDS):
                if browser_agent_available():
                    response_text, password = process_with_browser_agent(url, profile)
                    result = any(
                        kw in response_text.lower()
                        for kw in ("application submitted", "thank you", "submitted", "application received")
                    )
                    if password:
                        record_account(url, profile.get("contact_info", {}).get("email", ""), password)
                    reason = response_text[:512]
                else:
                    with sync_playwright() as p:
                        browser, context = connect_playwright_context(p, cdp_url, profile_dir, chrome_path)
                        page = get_or_create_page(context)
                        page.set_default_navigation_timeout(120000)
                        safe_goto(page, url)
                        email, password = generate_credentials(profile)
                        if "workday" in url.lower() or "myworkdayjobs" in url.lower():
                            result, reason = process_workday_fallback(page, profile, resume_path, email, password)
                        else:
                            result, reason = process_taleo_fallback(page, profile, resume_path, email, password)
                        if result:
                            record_account(url, email, password)
                        try:
                            page.screenshot(path=str(screenshot_path), full_page=True)
                        except Exception:
                            pass
                        close_playwright_session(browser, context, cdp_url)
            else:
                with sync_playwright() as p:
                    browser, context = connect_playwright_context(p, cdp_url, profile_dir, chrome_path)
                    page = get_or_create_page(context)
                    page.set_default_navigation_timeout(120000)
                    safe_goto(page, url)
                    if "linkedin.com/jobs" in url.lower():
                        result, reason = process_linkedin(page, resume_path)
                    else:
                        email, password = generate_credentials(profile)
                        result, reason = process_generic_career_site(page, profile, resume_path, email, password)
                        if result:
                            record_account(url, email, password)
                    try:
                        page.screenshot(path=str(screenshot_path), full_page=True)
                    except Exception:
                        pass
                    close_playwright_session(browser, context, cdp_url)

            if result:
                mark_applied_state(states, url, job_type)
                save_states(states)
                send_photo(str(screenshot_path), caption=f"Applied: {url}")
            else:
                append_failed(url, reason)
                send_message(f"Failed to apply to {url}: {reason}")

        except Exception as e:
            append_failed(url, str(e))
            send_message(f"Executor error for {url}: {e}")

        if time.time() - start_ts > 300:
            append_failed(url, "timeout")
            send_message(f"Executor timed out on {url}")

    write_json(QUEUE_PATH, [])


if __name__ == '__main__':
    run_executor()
