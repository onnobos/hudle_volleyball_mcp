"""Diagnostic script to test Hudl credentials, endpoint connectivity, and MCP tools."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from hudl_mcp.client import (
    HudlAuthError,
    HudlClient,
    HudlConnectionError,
    HudlError,
    HudlGraphQLError,
    get_hudl_api_url,
    get_hudl_cookie,
    get_hudl_team_id,
    load_project_env,
)


def mask(val: str | None) -> str:
    """Mask sensitive string."""
    if not val:
        return "[NOT SET]"
    if len(val) <= 8:
        return "***"
    return f"{val[:4]}...{val[-4:]}"


async def run_diagnostics() -> None:
    """Run step-by-step diagnostic tests."""
    print("=================================================================")
    print("   HUDL VOLLEYBALL MCP - CONNECTION & ENVIRONMENT DIAGNOSTICS   ")
    print("=================================================================\n")

    # 1. Environment Loading
    load_project_env()
    project_root = Path(__file__).resolve().parents[2]
    env_file = project_root / ".env"

    print(f"1. Checking Configuration (.env):")
    print(f"   - Project root: {project_root}")
    print(f"   - .env exists:  {env_file.is_file()} ({env_file})")

    cookie = get_hudl_cookie()
    team_id = get_hudl_team_id()
    api_url = get_hudl_api_url()

    print(f"   - HUDL_COOKIE:  {mask(cookie)}")
    print(f"   - HUDL_TEAM_ID: {team_id or '[Auto-detecting]'}")
    print(f"   - HUDL_API_URL: {api_url}")

    if not cookie:
        print("\n❌ ERROR: Hudl session cookie or auth_state.json is missing.")
        print("   Please run `login_to_hudl` or set HUDL_COOKIE in .env.")
        return

    print("\n2. Initializing client and resolving active team...")
    client = HudlClient()
    if not team_id:
        team_id = await client.resolve_active_team_id()
        print(f"   - Auto-detected Team ID: {team_id or '[None found]'}")

    if not team_id:
        print("\n⚠️ WARNING: Could not auto-detect Team ID from session or Hudl API.")
        print("   Set HUDL_TEAM_ID in .env or pass team_id explicitly.")
        return

    print("\n3. Testing GraphQL Request against Hudl...")

    try:
        matches = await client.get_recent_matches(team_id=team_id, limit=3)
        print("✅ SUCCESS! Connected to Hudl GraphQL API and retrieved matches:")
        for m in matches:
            print(f"   - Match ID: {m.match_id} | Opponent: {m.opponent_name} | Result: {m.result}")
        print("\nYour Hudl Volleyball MCP server is fully operational!")

    except HudlAuthError as exc:
        print(f"\n⚠️ AUTHENTICATION ERROR: {exc}")
        print("\nRemedy:")
        print("   Your Hudl session cookie has expired or is invalid.")
        print("   1. Run 'hudl-auth-refresh' or 'refresh_hudl_cookie' to re-authenticate.")
        print("   2. Or log into hudl.com in Chrome, copy 'ident' from DevTools Network tab, and update HUDL_COOKIE in .env.")

    except HudlGraphQLError as exc:
        print(f"\n❌ GRAPHQL / HTTP ERROR: {exc}")
        if "404" in str(exc):
            print("\nRemedy for 404 Not Found:")
            print(f"   The endpoint '{api_url}' was not found on Hudl.")
            print("   Please open Chrome DevTools (Network tab -> filter 'graphql') while navigating your team on hudl.com,")
            print("   and check the exact Request URL. Then set HUDL_API_URL in .env, e.g.:")
            print("   HUDL_API_URL=https://api.hudl.com/graphql (or your team's endpoint)")

    except HudlConnectionError as exc:
        print(f"\n🌐 NETWORK CONNECTION ERROR: {exc}")
        print("   Check your internet connection.")

    except Exception as exc:
        print(f"\n❌ UNEXPECTED ERROR: {type(exc).__name__}: {exc}")


def main() -> None:
    asyncio.run(run_diagnostics())


if __name__ == "__main__":
    main()
