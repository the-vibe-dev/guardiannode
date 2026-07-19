#!/usr/bin/env python3
"""Capture submission screenshots from the real synthetic-only dashboard flow.

This maintainer helper uses a disposable backend data directory, mock Guardian
Review provider, and Chromium. It never loads an existing GuardianNode database.
Install Selenium in a throwaway environment before running it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def _display_path(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def _wait_for(url: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"Disposable backend did not start at {url}")


def _capture(driver, path: Path) -> None:
    height = min(
        int(driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")),
        12_000,
    )
    driver.set_window_size(1440, max(1000, height))
    path.parent.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(path))


def capture(output_dir: Path, port: int) -> list[Path]:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as expected
    from selenium.webdriver.support.ui import WebDriverWait

    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="guardiannode-build-week-screenshots-") as temp:
        data_dir = Path(temp)
        env = os.environ.copy()
        env.update(
            {
                "GUARDIANNODE_DATA_DIR": str(data_dir),
                "GUARDIANNODE_BIND_HOST": "127.0.0.1",
                "GUARDIANNODE_PORT": str(port),
                "GUARDIANNODE_GUARDIAN_REVIEW_ENABLED": "true",
                "GUARDIANNODE_GUARDIAN_REVIEW_PROVIDER": "mock",
                "GUARDIANNODE_DEMO_MODE_ENABLED": "true",
                "GUARDIANNODE_MDNS_ENABLED": "false",
                "GUARDIANNODE_RETENTION_CLEANUP_ENABLED": "false",
                "GUARDIANNODE_DEVICE_OFFLINE_ALERT_ENABLED": "false",
                "GUARDIANNODE_NOTIFICATION_WORKER_ENABLED": "false",
                "GUARDIANNODE_DATABASE_BACKUP_ENABLED": "false",
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            }
        )
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=BACKEND,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        driver = None
        try:
            _wait_for(f"{base_url}/api/health")
            setup_path = data_dir / "keys" / "setup_token.json"
            deadline = time.monotonic() + 10
            while not setup_path.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            setup_token = json.loads(setup_path.read_text("utf-8"))["token"]

            options = Options()
            options.binary_location = "/usr/bin/chromium"
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--hide-scrollbars")
            options.add_argument("--window-size=1440,1000")
            driver = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
            wait = WebDriverWait(driver, 30)

            driver.get(f"{base_url}/setup")
            wait.until(expected.visibility_of_element_located((By.XPATH, "//h1[contains(., 'GuardianNode Setup')]")))
            fields = driver.find_elements(By.CSS_SELECTOR, "input")
            fields[0].clear()
            fields[0].send_keys("Synthetic Demo Parent")
            fields[1].send_keys(setup_token)
            driver.find_element(By.XPATH, "//button[normalize-space()='Next']").click()
            wait.until(expected.visibility_of_element_located((By.XPATH, "//span[contains(., 'Password (min 10 characters)')]")))
            password_fields = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
            for field in password_fields:
                field.send_keys("synthetic demo password")
            driver.find_element(By.XPATH, "//button[normalize-space()='Next']").click()
            wait.until(expected.element_to_be_clickable((By.CSS_SELECTOR, "input[type='checkbox']"))).click()
            driver.find_element(By.XPATH, "//button[normalize-space()='Next']").click()
            wait.until(expected.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Finish']"))).click()
            wait.until(expected.visibility_of_element_located((By.XPATH, "//*[contains(., 'Overview')]")))

            created: list[Path] = []
            driver.get(f"{base_url}/demo")
            wait.until(expected.visibility_of_element_located((By.XPATH, "//h1[contains(., 'Guardian Review synthetic demo')]")))
            trigger_button = wait.until(
                expected.element_to_be_clickable(
                    (By.XPATH, "//button[contains(., 'Trigger synthetic incident')]")
                )
            )
            target = output_dir / "01-synthetic-scenario-picker.png"
            _capture(driver, target)
            created.append(target)

            trigger_button.click()
            wait.until(expected.visibility_of_element_located((By.XPATH, "//h2[contains(., 'Synthetic incident created')]")))
            target = output_dir / "02-local-detection-created.png"
            _capture(driver, target)
            created.append(target)
            driver.find_element(By.XPATH, "//a[contains(., 'Open incident and continue')]").click()
            wait.until(expected.visibility_of_element_located((By.XPATH, "//h2[normalize-space()='Guardian Review']")))
            target = output_dir / "03-synthetic-incident.png"
            _capture(driver, target)
            created.append(target)

            preview_button = wait.until(
                expected.element_to_be_clickable(
                    (By.XPATH, "//button[contains(., 'Preview what would be sent')]")
                )
            )
            preview_button.click()
            wait.until(expected.visibility_of_element_located((By.CSS_SELECTOR, "[data-testid='guardian-review-outbound']")))
            target = output_dir / "04-exact-outbound-preview.png"
            _capture(driver, target)
            created.append(target)

            consent = driver.find_element(By.XPATH, "//label[contains(., 'local mock Guardian Review')]//input[@type='checkbox']")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", consent)
            consent.click()
            driver.find_element(By.XPATH, "//button[contains(., 'Run mock Guardian Review')]").click()
            wait.until(expected.visibility_of_element_located((By.XPATH, "//h3[contains(., 'Guardian Review communication plan')]")))
            target = output_dir / "05-communication-plan-and-feedback.png"
            _capture(driver, target)
            created.append(target)
            return created
        finally:
            if driver is not None:
                driver.quit()
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "build-week" / "screenshots",
    )
    parser.add_argument("--port", type=int, default=8879)
    args = parser.parse_args()
    for path in capture(args.output_dir.resolve(), args.port):
        print(_display_path(path))


if __name__ == "__main__":
    main()
