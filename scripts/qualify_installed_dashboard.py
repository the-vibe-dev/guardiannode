#!/usr/bin/env python3
"""Qualify the synthetic Guardian Review flow against an installed backend.

This maintainer utility is intentionally separate from the disposable screenshot
capture helper. It drives the real dashboard served by a release installation,
uses only GuardianNode's namespaced synthetic scenario, and emits a concise JSON
result suitable for release evidence. Secrets are accepted through environment
variables and are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import time
from pathlib import Path
from urllib.request import urlopen


def _wait_for(url: str, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Backend did not become reachable at {url}")


def _capture(driver, path: Path) -> None:
    height = min(
        int(driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")),
        12_000,
    )
    driver.set_window_size(1440, max(1000, height))
    path.parent.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(path))


def _write_operator_credentials(path: Path, base_url: str, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "base_url": base_url,
                "display_name": "Synthetic Demo Parent",
                "password": password,
                "scope": "private Windows qualification/demo environment only",
                "warning": "Do not publish or reuse this credential.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        # Windows operators must additionally apply an owner-only ACL.
        pass


def _write_pairing_code(path: Path, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"code": code}, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _load_password(path: Path | None) -> str | None:
    supplied = os.environ.get("GUARDIANNODE_PARENT_PASSWORD")
    if supplied:
        return supplied
    if path and path.exists():
        return str(json.loads(path.read_text("utf-8"))["password"])
    return None


def _sanitize_console_message(message: str, base_url: str) -> str:
    message = message.replace(base_url, "<dashboard>")
    return re.sub(r"https?://[^\s\"]+", "<url>", message)[:500]


def qualify(args: argparse.Namespace) -> dict[str, object]:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as expected
    from selenium.webdriver.support.ui import WebDriverWait

    base_url = args.base_url.rstrip("/")
    _wait_for(f"{base_url}/api/health/ready")

    if args.browser == "firefox":
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service

        options = Options()
        options.binary_location = args.firefox
        options.add_argument("-headless")
        driver = (
            webdriver.Firefox(options=options)
            if args.geckodriver == "auto"
            else webdriver.Firefox(service=Service(args.geckodriver), options=options)
        )
    else:
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        options = Options()
        options.binary_location = args.chromium
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--window-size=1440,1000")
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        driver = (
            webdriver.Chrome(options=options)
            if args.chromedriver == "auto"
            else webdriver.Chrome(service=Service(args.chromedriver), options=options)
        )
    wait = WebDriverWait(driver, args.timeout)
    created: list[str] = []
    canceled_without_submission = False
    feedback_saved = False
    try:
        driver.get(f"{base_url}/")
        wait.until(
            lambda current: (
                current.find_elements(By.XPATH, "//h1[contains(., 'GuardianNode Setup')]")
                or current.find_elements(By.XPATH, "//button[normalize-space()='Sign in']")
                or current.find_elements(By.XPATH, "//*[contains(., 'Overview')]")
            )
        )
        if driver.find_elements(By.XPATH, "//h1[contains(., 'GuardianNode Setup')]"):
            setup_token = os.environ.get("GUARDIANNODE_SETUP_TOKEN")
            if not setup_token and args.setup_token_file:
                setup_token = str(json.loads(args.setup_token_file.read_text("utf-8"))["token"])
            if not setup_token:
                raise RuntimeError("GUARDIANNODE_SETUP_TOKEN is required for first-run qualification")
            password = secrets.token_urlsafe(24)
            fields = driver.find_elements(By.CSS_SELECTOR, "input")
            fields[0].clear()
            fields[0].send_keys("Synthetic Demo Parent")
            fields[1].send_keys(setup_token)
            driver.find_element(By.XPATH, "//button[normalize-space()='Next']").click()
            wait.until(expected.visibility_of_element_located((By.XPATH, "//span[contains(., 'Password (min 10 characters)')]")))
            for field in driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
                field.send_keys(password)
            driver.find_element(By.XPATH, "//button[normalize-space()='Next']").click()
            wait.until(expected.element_to_be_clickable((By.CSS_SELECTOR, "input[type='checkbox']"))).click()
            driver.find_element(By.XPATH, "//button[normalize-space()='Next']").click()
            wait.until(expected.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Finish']"))).click()
            wait.until(expected.visibility_of_element_located((By.XPATH, "//*[contains(., 'Overview')]")))
            if args.operator_credentials:
                _write_operator_credentials(args.operator_credentials, base_url, password)
        elif driver.find_elements(By.XPATH, "//button[normalize-space()='Sign in']"):
            password = _load_password(args.operator_credentials)
            if not password:
                raise RuntimeError("GUARDIANNODE_PARENT_PASSWORD or --operator-credentials is required to sign in")
            driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(password)
            driver.find_element(By.XPATH, "//button[normalize-space()='Sign in']").click()
            wait.until(expected.visibility_of_element_located((By.XPATH, "//*[contains(., 'Overview')]")))

        if args.pairing_code_output:
            driver.get(f"{base_url}/devices")
            wait.until(expected.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Add device']"))).click()
            code_element = wait.until(expected.visibility_of_element_located((By.CSS_SELECTOR, ".text-4xl.font-mono")))
            code = code_element.text.strip()
            if not re.fullmatch(r"\d{6}", code):
                raise RuntimeError("Dashboard returned an invalid pairing code shape")
            _write_pairing_code(args.pairing_code_output, code)
            return {"status": "passed", "pairing_code_issued": True, "pairing_code_disclosed": False}

        driver.get(f"{base_url}/demo")
        wait.until(expected.visibility_of_element_located((By.XPATH, "//h1[contains(., 'Guardian Review synthetic demo')]")))
        wait.until(expected.visibility_of_element_located((By.XPATH, "//*[contains(., 'Demo device')]/following::*[contains(., 'Ready')][1]")))
        if args.scenario_title:
            scenario = wait.until(
                expected.element_to_be_clickable(
                    (By.XPATH, f"//label[.//*[normalize-space()={json.dumps(args.scenario_title)}]]")
                )
            )
            scenario.click()
        shot = args.output_dir / "01-installed-demo-ready.png"
        _capture(driver, shot)
        created.append(str(shot))

        wait.until(expected.element_to_be_clickable((By.XPATH, "//button[contains(., 'Trigger synthetic incident')]"))).click()
        wait.until(expected.visibility_of_element_located((By.XPATH, "//h2[contains(., 'Synthetic incident created')]")))
        shot = args.output_dir / "02-installed-local-detection.png"
        _capture(driver, shot)
        created.append(str(shot))
        driver.find_element(By.XPATH, "//a[contains(., 'Open incident and continue')]").click()
        wait.until(expected.visibility_of_element_located((By.XPATH, "//h2[normalize-space()='Guardian Review']")))

        age = wait.until(expected.element_to_be_clickable((By.XPATH, "//label[contains(., 'Include approximate age group')]//input")))
        if age.is_selected():
            age.click()
        evidence = driver.find_element(By.XPATH, "//label[contains(., 'Include selected minimized evidence')]//input")
        if evidence.is_selected():
            evidence.click()
        driver.find_element(By.XPATH, "//button[contains(., 'Preview what would be sent')]").click()
        wait.until(expected.visibility_of_element_located((By.CSS_SELECTOR, "[data-testid='guardian-review-outbound']")))
        shot = args.output_dir / "03-installed-exact-outbound-preview.png"
        _capture(driver, shot)
        created.append(str(shot))
        driver.find_element(By.XPATH, "//button[contains(., 'Cancel') and contains(., 'send nothing')]").click()
        wait.until(expected.visibility_of_element_located((By.XPATH, "//button[contains(., 'Preview what would be sent')]")))
        canceled_without_submission = True

        driver.find_element(By.XPATH, "//button[contains(., 'Preview what would be sent')]").click()
        wait.until(expected.visibility_of_element_located((By.CSS_SELECTOR, "[data-testid='guardian-review-outbound']")))
        consent = driver.find_element(By.XPATH, "//label[contains(., 'local mock Guardian Review')]//input[@type='checkbox']")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", consent)
        consent.click()
        driver.find_element(By.XPATH, "//button[contains(., 'Run mock Guardian Review')]").click()
        wait.until(expected.visibility_of_element_located((By.XPATH, "//h3[contains(., 'Guardian Review communication plan')]")))
        shot = args.output_dir / "04-installed-communication-plan.png"
        _capture(driver, shot)
        created.append(str(shot))

        driver.refresh()
        wait.until(expected.visibility_of_element_located((By.XPATH, "//*[contains(., 'Review history for this alert')]")))
        wait.until(
            expected.element_to_be_clickable(
                (By.XPATH, "//button[.//span[contains(translate(normalize-space(.), 'COMPLETED', 'completed'), 'completed')]]")
            )
        ).click()
        wait.until(expected.visibility_of_element_located((By.XPATH, "//h3[contains(., 'Guardian Review communication plan')]")))
        wait.until(expected.element_to_be_clickable((By.XPATH, "//label[normalize-space()='Helpful']//input"))).click()
        driver.find_element(By.XPATH, "//button[normalize-space()='Save feedback']").click()
        wait.until(expected.visibility_of_element_located((By.XPATH, "//*[contains(., 'will not automatically train')]")))
        feedback_saved = True
        shot = args.output_dir / "05-installed-feedback-saved.png"
        _capture(driver, shot)
        created.append(str(shot))

        try:
            console = driver.get_log("browser")
            console_log_supported = True
        except Exception:
            console = []
            console_log_supported = False
        severe = [entry for entry in console if entry.get("level") == "SEVERE"]
        expected_auth_probe = [
            entry
            for entry in severe
            if "/api/auth/me" in str(entry.get("message", "")) and "401 (Unauthorized)" in str(entry.get("message", ""))
        ]
        unexpected_severe = [entry for entry in severe if entry not in expected_auth_probe]
        body = driver.find_element(By.TAG_NAME, "body").text
        return {
            "status": "passed",
            "title": driver.title,
            "page_nonblank": bool(body.strip()),
            "communication_plan_visible": "Guardian Review communication plan" in body,
            "human_decision_boundary_visible": "Do not punish or accuse a child based only on an AI assessment" in body,
            "canceled_without_submission": canceled_without_submission,
            "refresh_recovery": True,
            "feedback_saved": feedback_saved,
            "scenario_title": args.scenario_title or "default scenario",
            "browser_console_severe": len(severe),
            "browser_console_unexpected_severe": len(unexpected_severe),
            "browser_console_severe_messages": [
                _sanitize_console_message(str(entry.get("message", "")), base_url) for entry in severe[:5]
            ],
            "browser_console_log_supported": console_log_supported,
            "screenshots": created,
        }
    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Installed GuardianNode dashboard URL")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--operator-credentials", type=Path, help="Private mode-0600 handoff file; never commit")
    parser.add_argument("--setup-token-file", type=Path, help="Protected setup_token.json on the installed server")
    parser.add_argument("--pairing-code-output", type=Path, help="Private one-use code file; skips the demo flow")
    parser.add_argument("--browser", choices=("chromium", "firefox"), default="chromium")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--chromedriver", default="/usr/bin/chromedriver")
    parser.add_argument("--firefox", default="/usr/bin/firefox")
    parser.add_argument("--geckodriver", default="/usr/bin/geckodriver")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument(
        "--scenario-title",
        help="Exact synthetic scenario title to select before triggering the incident",
    )
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    if args.operator_credentials:
        args.operator_credentials = args.operator_credentials.resolve()
    if args.setup_token_file:
        args.setup_token_file = args.setup_token_file.resolve()
    if args.pairing_code_output:
        args.pairing_code_output = args.pairing_code_output.resolve()
    print(json.dumps(qualify(args), indent=2))


if __name__ == "__main__":
    main()
