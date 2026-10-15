"""Unit tests for Playwright auth refresh and .env updater."""

import pytest
from pathlib import Path

from hudl_mcp.auth_refresh import refresh_session, update_env_file


def test_update_env_file_replaces_existing(tmp_path: Path):
    """Verify update_env_file replaces an existing key while preserving other lines and comments."""
    env_file = tmp_path / ".env"
    initial_content = (
        "# Configuration File\n"
        "HUDL_TEAM_ID=123456\n"
        "HUDL_COOKIE=ident=old_expired_cookie;\n"
        "HUDL_EMAIL=coach@example.com\n"
    )
    env_file.write_text(initial_content, encoding="utf-8")

    update_env_file("HUDL_COOKIE", "ident=new_fresh_cookie;", env_path=env_file)

    updated_content = env_file.read_text(encoding="utf-8")
    assert "HUDL_COOKIE=ident=new_fresh_cookie;\n" in updated_content
    assert "HUDL_TEAM_ID=123456\n" in updated_content
    assert "HUDL_EMAIL=coach@example.com\n" in updated_content
    assert "# Configuration File\n" in updated_content
    assert "old_expired_cookie" not in updated_content


def test_update_env_file_appends_new_key(tmp_path: Path):
    """Verify update_env_file appends a key if not previously in .env."""
    env_file = tmp_path / ".env"
    env_file.write_text("HUDL_TEAM_ID=123456\n", encoding="utf-8")

    update_env_file("HUDL_COOKIE", "ident=brand_new_token;", env_path=env_file)

    updated_content = env_file.read_text(encoding="utf-8")
    assert "HUDL_TEAM_ID=123456\n" in updated_content
    assert "HUDL_COOKIE=ident=brand_new_token;\n" in updated_content


def test_update_env_file_creates_file_if_missing(tmp_path: Path):
    """Verify update_env_file creates a new .env file if it does not exist."""
    env_file = tmp_path / ".env"
    assert not env_file.exists()

    update_env_file("HUDL_COOKIE", "ident=created_token;", env_path=env_file)

    assert env_file.exists()
    assert env_file.read_text(encoding="utf-8") == "HUDL_COOKIE=ident=created_token;\n"


@pytest.mark.asyncio
async def test_refresh_session_missing_credentials(monkeypatch):
    """Verify refresh_session returns helpful error when credentials are not configured."""
    monkeypatch.setenv("HUDL_EMAIL", "")
    monkeypatch.setenv("HUDL_PASSWORD", "")

    result = await refresh_session(email=None, password=None)
    assert result["success"] is False
    assert "login_to_hudl" in result["error"]


def test_get_cookie_from_auth_state(tmp_path: Path):
    """Verify get_cookie_from_auth_state extracts cookies from Playwright storage state format."""
    import json
    from hudl_mcp.auth_refresh import get_cookie_from_auth_state

    auth_file = tmp_path / "auth_state.json"
    data = {
        "cookies": [
            {"name": "ident", "value": "my_jwt_token", "domain": ".hudl.com"},
            {"name": "t", "value": "948881", "domain": ".hudl.com"},
            {"name": "ignored", "value": "123", "domain": "other.com"},
        ]
    }
    auth_file.write_text(json.dumps(data), encoding="utf-8")

    cookie_header = get_cookie_from_auth_state(auth_file)
    assert cookie_header is not None
    assert "ident=my_jwt_token;" in cookie_header
    assert "t=948881;" in cookie_header
    assert "ignored" not in cookie_header


def test_save_and_load_cookie_auth_state(tmp_path: Path):
    """Verify save_cookie_to_auth_state writes valid JSON that get_cookie_from_auth_state can parse."""
    from hudl_mcp.auth_refresh import get_cookie_from_auth_state, save_cookie_to_auth_state

    auth_file = tmp_path / "saved_state.json"
    raw_cookie = "ident=token_abc_123; t=948881; app=Hudl;"
    save_cookie_to_auth_state(raw_cookie, auth_state_path=auth_file)

    assert auth_file.exists()
    loaded = get_cookie_from_auth_state(auth_file)
    assert loaded is not None
    assert "ident=token_abc_123" in loaded
    assert "t=948881" in loaded


@pytest.mark.asyncio
async def test_interactive_login_closed_window(monkeypatch, tmp_path: Path):
    """Verify interactive_login handles window closure before completion."""
    from unittest.mock import AsyncMock, MagicMock
    from hudl_mcp.auth_refresh import interactive_login

    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_url = AsyncMock(side_effect=Exception("Target closed"))
    mock_page.url = "https://www.hudl.com/login"

    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_playwright = MagicMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw_context = MagicMock()
    mock_pw_context.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_pw_context.__aexit__ = AsyncMock()

    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: mock_pw_context)

    res = await interactive_login(auth_state_path=tmp_path / "auth.json", timeout_seconds=10)
    assert res["success"] is False
    assert "The browser window was closed" in res["error"]
