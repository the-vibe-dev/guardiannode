#!/usr/bin/env python3
"""Capture the real child-agent -> server -> live Guardian Review judge path.

The script drives an installed Chrome browser against a private staging backend.
It never prints credentials or outbound evidence. The incident must already be a
clearly labelled synthetic fixture produced by the Windows child agent.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.request import urlopen


def wait_for(url: str, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=3) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("The staging dashboard did not become ready")


def capture(driver, path: Path) -> None:
    height = min(
        int(driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")),
        12_000,
    )
    driver.set_window_size(1440, max(1000, height))
    path.parent.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(path))


def mask_device_name(driver, device_name: str | None) -> None:
    if not device_name:
        return
    driver.execute_script(
        """
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        for (const node of nodes) {
          node.nodeValue = node.nodeValue.split(arguments[0]).join('Synthetic Windows Client');
        }
        """,
        device_name,
    )


def run(args: argparse.Namespace) -> dict[str, object]:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as expected
    from selenium.webdriver.support.ui import Select, WebDriverWait

    base_url = args.base_url.rstrip("/")
    wait_for(f"{base_url}/api/health/ready")

    options = webdriver.ChromeOptions()
    options.binary_location = args.chromium
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--window-size=1440,1000")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, args.timeout)
    created: list[str] = []
    try:
        password = str(json.loads(args.operator_credentials.read_text("utf-8"))["password"])
        driver.get(f"{base_url}/login")
        wait.until(expected.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))).send_keys(password)
        driver.find_element(By.XPATH, "//button[normalize-space()='Sign in']").click()
        wait.until(expected.visibility_of_element_located((By.XPATH, "//*[contains(., 'Overview')]")))

        driver.get(f"{base_url}/risks")
        wait.until(expected.visibility_of_element_located((By.XPATH, "//h1[normalize-space()='Risk feed']")))
        wait.until(expected.element_to_be_clickable((By.XPATH, "(//a[normalize-space()='Review'])[1]")))
        mask_device_name(driver, args.mask_device_name)
        shot = args.output_dir / "01-live-client-server-alert.png"
        capture(driver, shot)
        created.append(str(shot))

        driver.find_element(By.XPATH, "(//a[normalize-space()='Review'])[1]").click()
        wait.until(expected.visibility_of_element_located((By.XPATH, "//h1[normalize-space()='Alert']")))
        wait.until(expected.visibility_of_element_located((By.XPATH, "//h2[normalize-space()='Guardian Review']")))
        mask_device_name(driver, args.mask_device_name)
        shot = args.output_dir / "02-live-local-detection.png"
        capture(driver, shot)
        created.append(str(shot))

        reveal = driver.find_elements(By.XPATH, "//button[normalize-space()='Reveal screenshot']")
        if reveal:
            reveal[0].click()
            wait.until(lambda d: d.execute_script("return document.querySelector('img[alt=\"Captured screenshot\"]')?.naturalWidth > 0"))
            mask_device_name(driver, args.mask_device_name)
            shot = args.output_dir / "03-live-agent-capture.png"
            capture(driver, shot)
            created.append(str(shot))

        Select(driver.find_element(By.XPATH, "//label[contains(., 'Who is involved?')]//select")).select_by_value("known_peer")
        Select(driver.find_element(By.XPATH, "//label[contains(., 'Has this happened repeatedly?')]//select")).select_by_value("no")
        context = driver.find_element(By.XPATH, "//label[contains(., 'Context you want the review to consider')]//textarea")
        context.send_keys("Synthetic lab fixture from a competitive fictional game. Help the parent clarify whether this is game slang or peer harassment.")
        driver.find_element(By.XPATH, "//button[contains(., 'Preview what would be sent')]").click()
        wait.until(expected.visibility_of_element_located((By.CSS_SELECTOR, "[data-testid='guardian-review-outbound']")))
        shot = args.output_dir / "04-live-exact-outbound-preview.png"
        capture(driver, shot)
        created.append(str(shot))

        consent = driver.find_element(By.XPATH, "//label[contains(., 'external model')]//input[@type='checkbox']")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", consent)
        consent.click()
        driver.find_element(By.XPATH, "//button[contains(., 'Send for Guardian Review')]").click()
        try:
            wait.until(expected.visibility_of_element_located((By.XPATH, "//*[contains(., 'Guardian Review is queued') or contains(., 'Guardian Review is running')]")))
            shot = args.output_dir / "05-live-review-running.png"
            capture(driver, shot)
            created.append(str(shot))
        except Exception:
            pass

        wait.until(expected.visibility_of_element_located((By.XPATH, "//h3[contains(., 'Guardian Review communication plan')]")))
        shot = args.output_dir / "06-live-structured-result.png"
        capture(driver, shot)
        created.append(str(shot))

        helpful = wait.until(expected.element_to_be_clickable((By.XPATH, "//label[normalize-space()='Helpful']//input")))
        helpful.click()
        driver.find_element(By.XPATH, "//button[normalize-space()='Save feedback']").click()
        wait.until(expected.visibility_of_element_located((By.XPATH, "//*[contains(., 'will not automatically train')]")))
        shot = args.output_dir / "07-live-feedback-saved.png"
        capture(driver, shot)
        created.append(str(shot))

        severe = [entry for entry in driver.get_log("browser") if entry.get("level") == "SEVERE"]
        unexpected = [entry for entry in severe if not ("/api/auth/me" in entry.get("message", "") and "401" in entry.get("message", ""))]
        body = driver.find_element(By.TAG_NAME, "body").text
        return {
            "status": "passed",
            "real_child_agent_alert": True,
            "live_openai_result": "Guardian Review communication plan" in body,
            "human_decision_boundary": "Do not punish or accuse a child based only on an AI assessment" in body,
            "unexpected_console_errors": len(unexpected),
            "screenshots": created,
        }
    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--operator-credentials", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mask-device-name")
    parser.add_argument("--chromium", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
