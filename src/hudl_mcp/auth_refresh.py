"""Playwright-based automated authentication refresh for Hudl.

This module automates logging into https://www.hudl.com/login using headless Playwright,
extracting the new session ("ident") cookie, and updating both the active process
environment and the .env file on disk.
"""

from __future__ import annotations

import asyncio
import os
import json
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

AUTH_STATE_DIR = Path.home() / ".hudl_mcp"
AUTH_STATE_FILE = AUTH_STATE_DIR / "auth_state.json"


def get_auth_state_path() -> Path:
    """Return the path to auth_state.json, respecting HUDL_AUTH_STATE_PATH or defaulting to ~/.hudl_mcp/auth_state.json."""
    custom = os.getenv("HUDL_AUTH_STATE_PATH")
    if custom:
        return Path(custom).expanduser().resolve()
    return AUTH_STATE_FILE


def get_cookie_from_auth_state(auth_state_path: Optional[Path] = None) -> Optional[str]:
    """Extract Cookie header string from Playwright auth_state.json file."""
    path = auth_state_path or get_auth_state_path()
    if not path.is_file():
        # Fallback to project root .hudl_mcp/auth_state.json if ~/.hudl_mcp is not present
        project_fallback = Path(__file__).resolve().parents[2] / ".hudl_mcp" / "auth_state.json"
        if project_fallback.is_file():
            path = project_fallback
        else:
            return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
        hudl_cookies = [c for c in cookies if "hudl.com" in c.get("domain", "")]
        ident_cookie = next((c for c in cookies if c.get("name") == "ident"), None)
        if not ident_cookie and not hudl_cookies:
            return None

        cookie_dict = {}
        if ident_cookie:
            cookie_dict["ident"] = ident_cookie["value"]
        for c in hudl_cookies:
            name = c.get("name")
            val = c.get("value")
            if name and val and name not in cookie_dict:
                cookie_dict[name] = val

        if cookie_dict:
            return "; ".join(f"{k}={v}" for k, v in cookie_dict.items()) + ";"
    except Exception:
        pass

    return None


def save_cookie_to_auth_state(cookie_str: str, auth_state_path: Optional[Path] = None) -> Path:
    """Convert a raw cookie string into Playwright auth_state.json format and save to disk."""
    target_path = auth_state_path or get_auth_state_path()
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        project_root = Path(__file__).resolve().parents[2]
        target_path = project_root / ".hudl_mcp" / "auth_state.json"
        target_path.parent.mkdir(parents=True, exist_ok=True)

    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, val = part.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": val.strip(),
                "domain": ".hudl.com",
                "path": "/",
                "expires": -1,
                "httpOnly": (name.strip() == "ident"),
                "secure": True,
                "sameSite": "Lax",
            })

    storage_data = {
        "cookies": cookies,
        "origins": [],
    }

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(storage_data, f, indent=2)

    return target_path


def find_env_file() -> Path:
    """Locate the .env file in project root or current/parent directories."""
    project_root = Path(__file__).resolve().parents[2]
    project_env = project_root / ".env"
    if project_env.is_file():
        return project_env

    current = Path.cwd()
    for directory in [current, *current.parents]:
        env_file = directory / ".env"
        if env_file.is_file():
            return env_file
    return project_env


def update_env_file(key: str, value: str, env_path: Optional[Path] = None) -> Path:
    """Update or append an environment variable in the .env file preserving existing contents."""
    target_path = env_path or find_env_file()
    lines = []
    found = False

    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f'export {key}='):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    with open(target_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return target_path


async def interactive_login(
    auth_state_path: Optional[Path] = None,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """Open an interactive pop-up browser to hudl.com/login for user authentication.

    Opens a visible Chromium window. The user logs in via password manager, SSO, or 2FA.
    Once navigation to https://www.hudl.com/home is detected, the session state is
    saved to ~/.hudl_mcp/auth_state.json, the browser closes, and process memory & .env are updated.

    Args:
        auth_state_path: Optional custom path to save auth_state.json (defaults to ~/.hudl_mcp/auth_state.json).
        timeout_seconds: Maximum seconds to wait for user to complete login (default: 300 = 5 mins).

    Returns:
        Dict with success status, storage_state_file path, masked cookie, and message.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "error": (
                "Playwright is not installed. Please run:\n"
                "pip install playwright && playwright install chromium"
            ),
        }

    target_path = auth_state_path or get_auth_state_path()
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        target_path = Path(__file__).resolve().parents[2] / ".hudl_mcp" / "auth_state.json"
        target_path.parent.mkdir(parents=True, exist_ok=True)

    user_agent = os.getenv(
        "HUDL_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        try:
            # 1. Navigate to login
            await page.goto("https://www.hudl.com/login", wait_until="domcontentloaded")

            # 2. Wait until navigation reaches hudl.com/home
            try:
                await page.wait_for_url(
                    lambda u: "hudl.com/home" in u.lower(),
                    timeout=timeout_seconds * 1000,
                )
            except Exception as nav_err:
                if "hudl.com/home" not in page.url.lower():
                    raise nav_err

            # 3. Allow post-login token exchange and cookies to settle
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                await page.wait_for_timeout(2000)
            except Exception:
                await page.wait_for_timeout(2000)

            # 4. Save storage state to auth_state.json
            await context.storage_state(path=str(target_path))

            # 5. Extract cookies and update active environment
            cookies = await context.cookies()
            hudl_cookies = [c for c in cookies if "hudl.com" in c.get("domain", "")]
            ident_cookie = next((c for c in cookies if c.get("name") == "ident"), None)

            cookie_dict = {}
            if ident_cookie:
                cookie_dict["ident"] = ident_cookie["value"]
            for c in hudl_cookies:
                name = c.get("name")
                val = c.get("value")
                if name and val and name not in cookie_dict:
                    cookie_dict[name] = val

            primary_value = "; ".join(f"{k}={v}" for k, v in cookie_dict.items()) + ";"

            if not primary_value or primary_value == ";":
                return {
                    "success": False,
                    "error": "Reached hudl.com/home, but no session cookie was captured.",
                }

            os.environ["HUDL_COOKIE"] = primary_value
            env_file = find_env_file()
            if env_file.is_file():
                env_text = env_file.read_text(encoding="utf-8")
                if "HUDL_COOKIE=" in env_text:
                    update_env_file("HUDL_COOKIE", primary_value, env_path=env_file)

            # 6. Extract team ID from cookies (the 't' cookie)
            t_cookie = next(
                (c.get("value") for c in cookies if c.get("name") == "t" and str(c.get("value", "")).isdigit()),
                None,
            )
            if t_cookie:
                os.environ["HUDL_TEAM_ID"] = str(t_cookie)
                # Team ID is auto-detected from session state; keep .env clean.

            # 7. Securely cache session in OS Keyring
            try:
                from hudl_mcp.security import save_secure_session
                save_secure_session(primary_value, team_id=str(t_cookie) if t_cookie else None)
            except Exception:
                pass

            masked_token = (
                primary_value[:15] + "..." + primary_value[-8:]
                if len(primary_value) > 25
                else "***"
            )

            team_info_str = f"- **Detected Team ID**: `{t_cookie}`\n" if t_cookie else ""

            return {
                "success": True,
                "storage_state_file": str(target_path),
                "cookie_header": primary_value,
                "team_id": t_cookie,
                "masked_cookie": masked_token,
                "message": (
                    f"Successfully logged into Hudl!\n\n"
                    f"- **Browser Window Closed**: Login completed.\n"
                    f"- **Session State Saved**: `{target_path}`\n"
                    f"{team_info_str}"
                    f"- **Active Session Cookie**: `{masked_token}`"
                ),
            }

        except Exception as exc:
            err_str = str(exc)
            if "Target closed" in err_str or "Page closed" in err_str or "closed" in err_str.lower():
                return {
                    "success": False,
                    "error": "The browser window was closed before reaching hudl.com/home. Login was not completed.",
                }
            if "Timeout" in err_str or "timed out" in err_str.lower():
                return {
                    "success": False,
                    "error": f"Login timed out after {timeout_seconds} seconds before reaching hudl.com/home. Please try again.",
                }
            return {
                "success": False,
                "error": f"Interactive login failed: {type(exc).__name__}: {exc}",
            }
        finally:
            try:
                await browser.close()
            except Exception:
                pass


async def refresh_session(
    email: Optional[str] = None,
    password: Optional[str] = None,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> Dict[str, Any]:
    """Automate login via headless Playwright, extract 'ident' cookie, and update .env.

    Args:
        email: Hudl account email (defaults to HUDL_EMAIL env var).
        password: Hudl account password (defaults to HUDL_PASSWORD env var).
        headless: Whether to run Chromium headlessly (default: True).
        timeout_ms: Timeout in milliseconds for browser operations.

    Returns:
        Dict with status, message, masked cookie, and env file path.
    """
    if not (os.getenv("HUDL_EMAIL") and os.getenv("HUDL_PASSWORD")):
        load_dotenv(find_env_file(), override=False)
    resolved_email = email or os.getenv("HUDL_EMAIL")
    resolved_password = password or os.getenv("HUDL_PASSWORD")

    if not resolved_email or not resolved_password:
        return {
            "success": False,
            "error": (
                "HUDL_EMAIL and HUDL_PASSWORD must be configured in your .env file "
                "to enable automated headless session refresh. Alternatively, use the `login_to_hudl` tool."
            ),
        }

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "error": (
                "Playwright is not installed. Please run:\n"
                "pip install playwright && playwright install chromium"
            ),
        }

    user_agent = os.getenv(
        "HUDL_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            # 1. Navigate to login
            await page.goto("https://www.hudl.com/login", wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

            # 2. Fill Email
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                '#email',
                'input[name="username"]',
                '#username',
            ]
            email_field = None
            for sel in email_selectors:
                if await page.locator(sel).first.is_visible():
                    email_field = page.locator(sel).first
                    break

            if not email_field:
                # Wait for any selector to appear
                await page.wait_for_selector(
                    'input[type="email"], input[name="email"], #email', timeout=10000
                )
                email_field = page.locator('input[type="email"], input[name="email"], #email').first

            await email_field.fill(resolved_email)
            await page.wait_for_timeout(500)

            # Check if password field is visible; if not, click next/continue
            pwd_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                '#password',
            ]
            pwd_visible = False
            for psel in pwd_selectors:
                if await page.locator(psel).first.is_visible():
                    pwd_visible = True
                    break

            if not pwd_visible:
                # Step 1 continue button
                btn_selectors = [
                    'button[type="submit"]',
                    'button:has-text("Continue")',
                    'button:has-text("Next")',
                    'button:has-text("Log In")',
                ]
                for bsel in btn_selectors:
                    btn = page.locator(bsel).first
                    if await btn.is_visible():
                        await btn.click()
                        break
                await page.wait_for_timeout(1500)

            # 3. Fill Password
            await page.wait_for_selector('input[type="password"], #password', timeout=10000)
            pwd_field = page.locator('input[type="password"], #password').first
            await pwd_field.fill(resolved_password)
            await page.wait_for_timeout(500)

            # 4. Submit login
            login_btn = page.locator('button[type="submit"], button:has-text("Log In"), button:has-text("Sign In")').first
            if await login_btn.is_visible():
                await login_btn.click()
            else:
                await pwd_field.press("Enter")

            # 5. Wait for login redirect and complete identity exchange
            try:
                await page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
            except Exception:
                pass

            # Navigate to hudl.com/home to ensure identity exchange sets 'ident' cookie
            try:
                await page.goto("https://www.hudl.com/home", wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2500)
            except Exception:
                await page.wait_for_timeout(3000)

            # 6. Extract Cookies
            cookies = await context.cookies()
            hudl_cookies = [c for c in cookies if "hudl.com" in c.get("domain", "")]
            ident_cookie = next((c for c in cookies if c["name"] == "ident"), None)

            # Build comprehensive cookie header string
            cookie_dict = {}
            if ident_cookie:
                cookie_dict["ident"] = ident_cookie["value"]
            for c in hudl_cookies:
                if c["name"] not in cookie_dict:
                    cookie_dict[c["name"]] = c["value"]

            primary_value = "; ".join(f"{k}={v}" for k, v in cookie_dict.items()) + ";"

            if not primary_value or primary_value == ";":
                return {
                    "success": False,
                    "error": (
                        "Login completed, but no session cookie was captured. "
                        "Please verify your credentials or check if 2FA/MFA is enabled on your Hudl account."
                    ),
                }

            # 7. Update active process environment and disk .env file
            os.environ["HUDL_COOKIE"] = primary_value
            env_file_path = update_env_file("HUDL_COOKIE", primary_value)

            masked_token = (
                primary_value[:15] + "..." + primary_value[-8:]
                if len(primary_value) > 25
                else "***"
            )

            return {
                "success": True,
                "cookie_header": primary_value,
                "masked_cookie": masked_token,
                "env_file": str(env_file_path),
                "message": (
                    f"Successfully logged into Hudl and refreshed session cookie ({masked_token}). "
                    f"Updated in-memory environment and {env_file_path}."
                ),
            }

        except Exception as exc:
            return {
                "success": False,
                "error": f"Automated Playwright login failed: {type(exc).__name__}: {exc}",
            }
        finally:
            await browser.close()


def main() -> None:
    """CLI entry point for running auth refresh."""
    print("Starting automated Hudl authentication refresh via Playwright...")
    result = asyncio.run(refresh_session())
    if result.get("success"):
        print(f"SUCCESS: {result.get('message')}")
    else:
        print(f"FAILED: {result.get('error')}")
        exit(1)


if __name__ == "__main__":
    main()
