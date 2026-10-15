"""Async HTTPX GraphQL client and authentication wrapper for Hudl.

This module handles:
1. Loading configuration and credentials from .env
2. Realistic browser header injection and cookie formatting
3. Sending async GraphQL requests to https://www.hudl.com/api/graphql
4. Robust error handling for 401/403 and GraphQL UNAUTHENTICATED codes with actionable AI messages
5. Higher-level domain methods to retrieve volleyball matches, player box scores, and rotation stats.
"""

from __future__ import annotations

import base64
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional
import httpx
from dotenv import load_dotenv

from hudl_mcp.models import (
    MatchSummary,
    PlayerStats,
    RotationStats,
    TeamInfo,
    VolleyballAction,
    find_matching_video_for_opponent,
    parse_balltime_player_stats,
    parse_balltime_rotation_stats,
    parse_matches_response,
    parse_player_stats_response,
    parse_rotation_stats_response,
    parse_teams_response,
    parse_video_actions,
)
from hudl_mcp.queries import (
    GET_RECENT_MATCHES_QUERY,
)

from pathlib import Path

_ENV_LOADED = False


def load_project_env(force: bool = False) -> None:
    """Find and load .env regardless of what working directory the MCP server was launched from."""
    global _ENV_LOADED
    if not force and _ENV_LOADED:
        return
    _ENV_LOADED = True

    # 1. Look in the project root directory
    project_root = Path(__file__).resolve().parents[2]
    project_env = project_root / ".env"
    if project_env.is_file():
        load_dotenv(project_env, override=force)
        return

    # 2. Walk up from current working directory
    curr = Path.cwd()
    for d in [curr, *curr.parents]:
        p = d / ".env"
        if p.is_file():
            load_dotenv(p, override=force)
            return

    load_dotenv(override=force)


from hudl_mcp.auth_refresh import get_cookie_from_auth_state

# Load environment variables on module import
load_project_env()

# Constants
DEFAULT_API_URL = "https://www.hudl.com/api/graphql/query"
DEFAULT_TIMEOUT = 20.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


from hudl_mcp.cache import (
    TTL_HISTORICAL_MATCH,
    TTL_SCHEDULE_TEAM,
    clear_all_cache,
    compute_cache_key,
    get_cached_response,
    set_cached_response,
)
from hudl_mcp.rate_limiter import DEFAULT_RATE_LIMITER, execute_with_retry

class HudlError(Exception):
    """Base exception for all Hudl MCP errors."""


class HudlSecurityError(HudlError):
    """Raised when an operation violates the strict read-only security policy."""


class HudlAuthError(HudlError):
    """Authentication failed due to missing, expired, or invalid session cookies."""


class HudlGraphQLError(HudlError):
    """GraphQL execution or schema error returned by Hudl API."""


class HudlConnectionError(HudlError):
    """Network connection, DNS, or timeout error communicating with Hudl."""


from hudl_mcp.security import get_secure_cookie, get_secure_team_id, save_secure_session


def get_hudl_cookie() -> Optional[str]:
    """Retrieve and format the active HUDL_COOKIE from environment, keyring, auth_state.json, or .env."""
    # 1. Active environment variable
    raw = os.getenv("HUDL_COOKIE")
    if raw and raw.strip():
        cookie = raw.strip().strip('"').strip("'")
        if "=" not in cookie:
            cookie = f"ident={cookie};"
        return cookie

    # 2. Secure OS Keyring
    cookie_from_keyring = get_secure_cookie()
    if cookie_from_keyring:
        os.environ["HUDL_COOKIE"] = cookie_from_keyring
        return cookie_from_keyring

    # 3. Local Playwright auth_state.json (~/.hudl_mcp/auth_state.json)
    cookie_from_state = get_cookie_from_auth_state()
    if cookie_from_state:
        os.environ["HUDL_COOKIE"] = cookie_from_state
        return cookie_from_state

    # 4. Fallback to .env file
    load_project_env()
    raw = os.getenv("HUDL_COOKIE")
    if not raw or not raw.strip():
        return None
    cookie = raw.strip().strip('"').strip("'")
    if "=" not in cookie:
        cookie = f"ident={cookie};"
    return cookie


def get_hudl_team_id() -> Optional[str]:
    """Retrieve default HUDL_TEAM_ID from environment, keyring, cookie t, or .env."""
    if "HUDL_TEAM_ID" not in os.environ and "HUDLE_TEAM_ID" not in os.environ:
        load_project_env()

    # 1. Environment variable (supports both HUDL_TEAM_ID and HUDLE_TEAM_ID)
    raw = os.getenv("HUDL_TEAM_ID") or os.getenv("HUDLE_TEAM_ID")
    if raw and raw.strip():
        return raw.strip().strip('"').strip("'")

    # 2. Secure OS Keyring
    keyring_tid = get_secure_team_id()
    if keyring_tid and keyring_tid.strip():
        return keyring_tid.strip()

    # 3. Extract from active HUDL_COOKIE (t=<team_id> cookie set by Hudl)
    cookie = get_hudl_cookie()
    if cookie:
        match = re.search(r'(?:^|;\s*)t=(\d+)(?:;|$)', cookie)
        if match:
            return match.group(1)

    return None


def get_hudl_api_url() -> str:
    """Retrieve API URL from environment or default."""
    load_project_env()
    return os.getenv("HUDL_API_URL", DEFAULT_API_URL).strip()


def get_hudl_timeout() -> float:
    """Retrieve timeout setting in seconds."""
    raw = os.getenv("HUDL_TIMEOUT")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return DEFAULT_TIMEOUT


def get_browser_headers() -> Dict[str, str]:
    """Construct realistic browser HTTP headers to mimic Chrome requests."""
    cookie = get_hudl_cookie()
    user_agent = os.getenv("HUDL_USER_AGENT", DEFAULT_USER_AGENT).strip()

    headers = {
        "User-Agent": user_agent,
        "Origin": "https://app.hudl.com",
        "Referer": "https://app.hudl.com/",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


DEFAULT_BALLTIME_URL = "https://backend.balltime.com"


def get_balltime_token() -> Optional[str]:
    """Extract Bearer JWT token from the 'ident' cookie in HUDL_COOKIE."""
    cookie = get_hudl_cookie()
    if not cookie:
        return None
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("ident="):
            ident_val = part[len("ident=") :]
            try:
                params = urllib.parse.parse_qs(ident_val)
                token = params.get("a", [None])[0]
                if token:
                    return token
            except Exception:
                pass
    return None


def get_balltime_headers() -> Dict[str, str]:
    """Construct headers with Authorization Bearer token for backend.balltime.com."""
    token = get_balltime_token()
    user_agent = os.getenv("HUDL_USER_AGENT", DEFAULT_USER_AGENT).strip()
    headers = {
        "User-Agent": user_agent,
        "Origin": "https://app.hudl.com",
        "Referer": "https://app.hudl.com/",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def to_balltime_video_id(raw_id: str) -> str:
    """Convert 24-hex Hudl internal video ID or base64 GraphQL ID to Balltime UUID format."""
    raw = str(raw_id).strip()
    if len(raw) == 36 and raw.count("-") == 4:
        return raw.lower()

    # Try base64 decode (e.g. Video6ace625ea5048ba518a7b1a5)
    try:
        decoded = base64.b64decode(raw).decode("utf-8", errors="ignore")
        if decoded.startswith("Video"):
            raw = decoded[len("Video") :]
    except Exception:
        pass

    # Check if 24-character hexadecimal (Hudl internal video ID)
    if len(raw) == 24 and all(c in "0123456789abcdefABCDEF" for c in raw):
        raw = raw.lower()
        return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}00000001"

    return raw


async def execute_graphql(
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
    client: Optional[httpx.AsyncClient] = None,
    _retried: bool = False,
) -> Dict[str, Any]:
    """Execute a GraphQL query against Hudl's internal GraphQL endpoint.

    Args:
        query: The GraphQL query string.
        variables: Optional variables mapping.
        timeout: Request timeout in seconds.
        client: Optional existing httpx.AsyncClient instance (useful for testing or pooling).
        _retried: Internal flag to prevent infinite recursion on authentication refresh attempts.

    Returns:
        The 'data' dictionary from the GraphQL response.

    Raises:
        HudlAuthError: If cookie is missing, expired (401/403), or GraphQL UNAUTHENTICATED error.
        HudlGraphQLError: If query returns GraphQL syntax/field errors or HTTP error status.
        HudlConnectionError: If network connection fails or times out.
    """
    # Enforce strict Read-Only Policy: block GraphQL mutations
    clean_query = query.strip().lower()
    if clean_query.startswith("mutation") or "mutation " in clean_query:
        raise HudlSecurityError(
            "Read-Only Policy Enforced: Data mutating GraphQL operations are strictly prohibited."
        )

    cookie = get_hudl_cookie()
    if not cookie:
        raise HudlAuthError(
            "No Hudl session cookie found. Please call the 'login_to_hudl' tool "
            "(or say 'Log me into Hudl') to log in via an interactive pop-up browser window."
        )

    headers = get_browser_headers()
    api_url = get_hudl_api_url()
    req_timeout = timeout or get_hudl_timeout()
    payload = {"query": query, "variables": variables or {}}

    async def _send_request(c: httpx.AsyncClient) -> httpx.Response:
        return await c.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=req_timeout,
        )

    try:
        if client is not None:
            response = await execute_with_retry(
                lambda: _send_request(client),
                rate_limiter=DEFAULT_RATE_LIMITER,
            )
        else:
            async with httpx.AsyncClient() as new_client:
                response = await execute_with_retry(
                    lambda: _send_request(new_client),
                    rate_limiter=DEFAULT_RATE_LIMITER,
                )
    except httpx.TimeoutException as exc:
        raise HudlConnectionError(
            f"Connection to Hudl GraphQL API timed out after {req_timeout}s: {exc}"
        ) from exc
    except httpx.RequestError as exc:
        raise HudlConnectionError(
            f"Failed to connect to Hudl GraphQL API ({api_url}): {exc}"
        ) from exc

    # 1. Check HTTP Status Codes
    if response.status_code in (401, 403):
        # Attempt auto-refresh if credentials exist and this is the first attempt
        if not _retried and os.getenv("HUDL_EMAIL") and os.getenv("HUDL_PASSWORD"):
            try:
                from hudl_mcp.auth_refresh import refresh_session
                refresh_res = await refresh_session()
                if refresh_res.get("success"):
                    clear_all_cache()
                    return await execute_graphql(
                        query=query,
                        variables=variables,
                        timeout=timeout,
                        client=client,
                        _retried=True,
                    )
            except Exception:
                pass

        raise HudlAuthError(
            f"Hudl authentication failed (HTTP {response.status_code}). "
            "Your session cookie has expired or is invalid. "
            "Please call the 'login_to_hudl' tool (or say 'Log me into Hudl') to log in via an interactive browser."
        )
    elif response.status_code >= 400:
        raise HudlGraphQLError(
            f"Hudl API returned HTTP error {response.status_code}"
        )

    # 2. Parse JSON Response
    try:
        data = response.json()
    except Exception as exc:
        raise HudlGraphQLError(
            f"Failed to parse JSON response from Hudl GraphQL API: {exc}. Body: {response.text[:200]}"
        ) from exc

    # 3. Check for GraphQL errors
    errors = data.get("errors")
    if errors and isinstance(errors, list):
        # Look for authentication errors inside GraphQL payload
        auth_keywords = ["unauthenticated", "unauthorized", "expired", "invalid token", "forbidden", "login required"]
        for err in errors:
            msg = str(err.get("message", "")).lower()
            code = str(err.get("extensions", {}).get("code", "")).upper()

            if code in ("UNAUTHENTICATED", "FORBIDDEN") or any(kw in msg for kw in auth_keywords):
                if not _retried and os.getenv("HUDL_EMAIL") and os.getenv("HUDL_PASSWORD"):
                    try:
                        from hudl_mcp.auth_refresh import refresh_session
                        refresh_res = await refresh_session()
                        if refresh_res.get("success"):
                            clear_all_cache()
                            return await execute_graphql(
                                query=query,
                                variables=variables,
                                timeout=timeout,
                                client=client,
                                _retried=True,
                            )
                    except Exception:
                        pass

                raise HudlAuthError(
                    f"Hudl GraphQL UNAUTHENTICATED error: {err.get('message')}. "
                    "Your session cookie has expired. "
                    "Please call the 'login_to_hudl' tool (or say 'Log me into Hudl') to re-authenticate."
                )

        # Non-auth GraphQL error
        err_messages = "; ".join(str(e.get("message", e)) for e in errors)
        raise HudlGraphQLError(f"GraphQL execution error: {err_messages}")

    return data.get("data") or {}


class HudlClient:
    """High-level client for retrieving and analyzing Hudl volleyball statistics."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        team_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.api_url = api_url or get_hudl_api_url()
        self.team_id = team_id or get_hudl_team_id()
        self.timeout = timeout or get_hudl_timeout()

    async def get_user_teams(
        self, force_refresh: bool = False, client: Optional[httpx.AsyncClient] = None
    ) -> List[TeamInfo]:
        """Fetch all Hudl teams associated with the authenticated user (cached 15m)."""
        active_tid = self.team_id or get_hudl_team_id()
        cookie = get_hudl_cookie()
        cache_key = compute_cache_key("user_teams", cookie or "anonymous")

        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached and isinstance(cached, list):
                return [TeamInfo.model_validate(t) for t in cached]

        headers = get_browser_headers()
        url = "https://www.hudl.com/api/v2/teams"

        async def _fetch(c: httpx.AsyncClient) -> httpx.Response:
            return await c.get(url, headers=headers, timeout=self.timeout)

        try:
            if client is not None:
                resp = await execute_with_retry(lambda: _fetch(client), rate_limiter=DEFAULT_RATE_LIMITER)
            else:
                async with httpx.AsyncClient() as http_client:
                    resp = await execute_with_retry(lambda: _fetch(http_client), rate_limiter=DEFAULT_RATE_LIMITER)

            if resp.status_code in (401, 403):
                raise HudlAuthError(
                    f"Hudl teams authentication failed (HTTP {resp.status_code}). "
                    "Please call login_to_hudl (or say 'Log me into Hudl') to log in via an interactive browser."
                )
            elif resp.status_code == 200:
                teams = parse_teams_response(resp.json(), active_team_id=active_tid)
                if teams and not active_tid:
                    first_tid = teams[0].team_id
                    os.environ["HUDL_TEAM_ID"] = first_tid
                    self.team_id = first_tid
                if teams:
                    set_cached_response(cache_key, [t.model_dump() for t in teams], TTL_SCHEDULE_TEAM)
                return teams
        except HudlAuthError:
            raise
        except (httpx.TimeoutException, httpx.RequestError):
            pass
        return []

    async def resolve_active_team_id(
        self, force_refresh: bool = False, client: Optional[httpx.AsyncClient] = None
    ) -> Optional[str]:
        """Resolve active team ID from environment, cookie t, or Hudl teams API."""
        tid = self.team_id or get_hudl_team_id()
        if tid:
            return tid
        teams = await self.get_user_teams(force_refresh=force_refresh, client=client)
        if teams:
            first_tid = teams[0].team_id
            os.environ["HUDL_TEAM_ID"] = first_tid
            self.team_id = first_tid
            return first_tid
        return None

    async def get_balltime_videos(
        self, force_refresh: bool = False, client: Optional[httpx.AsyncClient] = None
    ) -> List[MatchSummary]:
        """Fetch analyzed volleyball video games from Balltime video library (cached 15m)."""
        token = get_balltime_token()
        cache_key = compute_cache_key("balltime_videos", token or "anonymous")
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached and isinstance(cached, list):
                return [MatchSummary.model_validate(m) for m in cached]

        headers = get_balltime_headers()
        url = f"{DEFAULT_BALLTIME_URL}/library/videos?"

        async def _fetch(c: httpx.AsyncClient) -> httpx.Response:
            return await c.get(url, headers=headers, timeout=self.timeout)

        try:
            if client is not None:
                resp = await execute_with_retry(lambda: _fetch(client), rate_limiter=DEFAULT_RATE_LIMITER)
            else:
                async with httpx.AsyncClient() as http_client:
                    resp = await execute_with_retry(lambda: _fetch(http_client), rate_limiter=DEFAULT_RATE_LIMITER)

            if resp.status_code in (401, 403):
                raise HudlAuthError(
                    f"Balltime session authentication failed (HTTP {resp.status_code}). "
                    "Please call login_to_hudl (or say 'Log me into Hudl') to log in via an interactive browser."
                )
            elif resp.status_code == 200:
                videos = parse_matches_response(resp.json())
                if videos:
                    set_cached_response(cache_key, [v.model_dump() for v in videos], TTL_SCHEDULE_TEAM)
                return videos
        except HudlAuthError:
            raise
        except (httpx.TimeoutException, httpx.RequestError):
            pass
        return []

    async def get_video_metadata(
        self, video_id: str, force_refresh: bool = False, client: Optional[httpx.AsyncClient] = None
    ) -> Dict[str, Any]:
        """Fetch full video analysis and breakdown metadata for a Balltime video (cached 7 days)."""
        resolved_id = to_balltime_video_id(video_id)
        cache_key = compute_cache_key("video_metadata", resolved_id)
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached and isinstance(cached, dict):
                return cached

        headers = get_balltime_headers()
        url = f"{DEFAULT_BALLTIME_URL}/videos-metadata?"
        payload = {"video_ids": [resolved_id]}

        async def _post(c: httpx.AsyncClient) -> httpx.Response:
            return await c.post(url, json=payload, headers=headers, timeout=self.timeout)

        try:
            if client is not None:
                resp = await execute_with_retry(lambda: _post(client), rate_limiter=DEFAULT_RATE_LIMITER)
            else:
                async with httpx.AsyncClient() as http_client:
                    resp = await execute_with_retry(lambda: _post(http_client), rate_limiter=DEFAULT_RATE_LIMITER)

            if resp.status_code in (401, 403):
                raise HudlAuthError(
                    f"Balltime session authentication failed (HTTP {resp.status_code}). "
                    "Please call login_to_hudl (or say 'Log me into Hudl') to log in via an interactive browser."
                )
            elif resp.status_code == 200:
                data = resp.json()
                meta = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
                if meta:
                    set_cached_response(cache_key, meta, TTL_HISTORICAL_MATCH)
                return meta
            elif resp.status_code >= 400:
                raise HudlError(f"Balltime API returned HTTP {resp.status_code}")
        except HudlAuthError:
            raise
        except httpx.TimeoutException as exc:
            raise HudlConnectionError(f"Connection to Balltime timed out after {self.timeout}s: {exc}") from exc
        except httpx.RequestError as exc:
            raise HudlConnectionError(f"Failed to connect to Balltime API: {exc}") from exc

        return {}

    async def get_team_schedule(
        self, team_id: Optional[str] = None, force_refresh: bool = False, client: Optional[httpx.AsyncClient] = None
    ) -> List[MatchSummary]:
        """Fetch schedule fixtures for a team from Hudl classic facade endpoint (cached 15m)."""
        resolved_team_id = team_id or self.team_id
        if not resolved_team_id:
            return []

        cache_key = compute_cache_key("team_schedule", resolved_team_id)
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached and isinstance(cached, list):
                return [MatchSummary.model_validate(m) for m in cached]

        headers = get_browser_headers()
        schedule_url = f"https://www.hudl.com/api/v2/classicfacade/team/{resolved_team_id}/schedule"
        try:
            async def _fetch_sched(c: httpx.AsyncClient) -> httpx.Response:
                return await c.get(schedule_url, headers=headers, timeout=self.timeout)

            if client is not None:
                resp = await execute_with_retry(lambda: _fetch_sched(client), rate_limiter=DEFAULT_RATE_LIMITER)
            else:
                async with httpx.AsyncClient() as http_client:
                    resp = await execute_with_retry(lambda: _fetch_sched(http_client), rate_limiter=DEFAULT_RATE_LIMITER)

            if resp.status_code == 200:
                sched_matches = parse_matches_response(resp.json())
                for m in sched_matches:
                    m.match_type = "schedule"
                if sched_matches:
                    set_cached_response(cache_key, [m.model_dump() for m in sched_matches], TTL_SCHEDULE_TEAM)
                return sched_matches
            elif resp.status_code in (401, 403):
                raise HudlAuthError(
                    f"Hudl schedule authentication failed (HTTP {resp.status_code}). "
                    "Please call login_to_hudl (or say 'Log me into Hudl') to log in via an interactive browser."
                )
        except HudlAuthError:
            raise
        except (httpx.TimeoutException, httpx.RequestError):
            pass
        return []

    async def resolve_video_id(
        self, match_or_video_id: str, client: Optional[httpx.AsyncClient] = None
    ) -> Optional[str]:
        """Resolve an input ID, schedule ID, or match title to a Balltime video UUID."""
        cleaned = str(match_or_video_id).strip()
        converted = to_balltime_video_id(cleaned)
        # If it matches UUID format directly (e.g. 6ace625e-a504-8ba5-18a7-b1a500000001)
        if len(converted) == 36 and converted.count("-") == 4:
            return converted

        videos: List[MatchSummary] = []
        try:
            videos = await self.get_balltime_videos(client=client)
            cleaned_lower = cleaned.lower()
            for v in videos:
                if cleaned == v.match_id:
                    return v.match_id
                if cleaned_lower in v.opponent_name.lower():
                    return v.match_id
        except Exception:
            pass

        # If it looks like a numeric schedule ID (e.g. 34352342), check schedule to find opponent
        if cleaned.isdigit() or (len(cleaned) < 20 and "-" not in cleaned):
            try:
                schedule = await self.get_team_schedule(client=client)
                for s in schedule:
                    if s.match_id == cleaned:
                        matched_vid = find_matching_video_for_opponent(s.opponent_name, videos)
                        if matched_vid:
                            return matched_vid
            except Exception:
                pass

        # Try token/fuzzy match on video titles
        for v in videos:
            matched_vid = find_matching_video_for_opponent(cleaned, [v])
            if matched_vid:
                return matched_vid

        return None

    async def get_recent_matches(
        self,
        team_id: Optional[str] = None,
        limit: int = 10,
        force_refresh: bool = False,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[MatchSummary]:
        """Fetch both uploaded video matches and scheduled fixtures for a team, linking them together (cached 15m)."""
        resolved_team_id = team_id or self.team_id
        if not resolved_team_id:
            resolved_team_id = await self.resolve_active_team_id(force_refresh=force_refresh, client=client)
        if not resolved_team_id:
            raise HudlError(
                "No team_id provided and HUDL_TEAM_ID is not configured in .env. "
                "Please provide a team_id parameter or set HUDL_TEAM_ID."
            )

        cache_key = compute_cache_key("recent_matches", {"team_id": resolved_team_id, "limit": limit})
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached and isinstance(cached, list):
                return [MatchSummary.model_validate(m) for m in cached]

        video_matches: List[MatchSummary] = []
        schedule_matches: List[MatchSummary] = []
        seen_sched_ids = set()

        # 1. Fetch Balltime analyzed video matches (contains LUTRY VS Voléro Zürich, etc.)
        try:
            bt_matches = await self.get_balltime_videos(force_refresh=force_refresh, client=client)
            for m in bt_matches:
                m.match_type = "video"
                video_matches.append(m)
        except Exception:
            pass

        # 2. Try GraphQL if team_id available
        if resolved_team_id:
            try:
                variables = {"teamId": str(resolved_team_id), "limit": limit}
                raw_data = await execute_graphql(
                    query=GET_RECENT_MATCHES_QUERY,
                    variables=variables,
                    timeout=self.timeout,
                    client=client,
                )
                gql_matches = parse_matches_response(raw_data)
                for m in gql_matches:
                    if m.match_id not in seen_sched_ids:
                        seen_sched_ids.add(m.match_id)
                        m.match_type = "schedule"
                        schedule_matches.append(m)
            except (HudlGraphQLError, HudlConnectionError, HudlAuthError, HudlSecurityError):
                pass

        # 3. Fetch Hudl internal team schedule endpoint
        if resolved_team_id:
            try:
                sched_matches = await self.get_team_schedule(
                    team_id=resolved_team_id, force_refresh=force_refresh, client=client
                )
                for m in sched_matches:
                    if m.match_id not in seen_sched_ids:
                        seen_sched_ids.add(m.match_id)
                        m.match_type = "schedule"
                        schedule_matches.append(m)
            except (HudlConnectionError, HudlAuthError):
                raise
            except Exception:
                pass

        # 4. Link schedule matches to matching uploaded video matches!
        for s in schedule_matches:
            matched_vid = find_matching_video_for_opponent(s.opponent_name, video_matches, match_date=s.date)
            if matched_vid:
                s.video_id = matched_vid

        combined = video_matches[:limit] + schedule_matches[:limit]
        if combined:
            set_cached_response(cache_key, [m.model_dump() for m in combined], TTL_SCHEDULE_TEAM)
        return combined

    async def get_match_player_stats(
        self,
        match_id: str,
        team_id: Optional[str] = None,
        force_refresh: bool = False,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[PlayerStats]:
        """Fetch athlete box score statistics for a volleyball match (cached 7 days)."""
        if not match_id:
            raise HudlError("match_id is required to fetch player box score statistics.")

        cache_key = compute_cache_key("player_stats", {"match_id": match_id.strip(), "team_id": team_id})
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached and isinstance(cached, list):
                return [PlayerStats.model_validate(p) for p in cached]

        # 1. Resolve to Balltime video ID (handles UUIDs, titles, and scheduled match IDs)
        vid = await self.resolve_video_id(match_id, client=client)

        if vid:
            meta = await self.get_video_metadata(vid, force_refresh=force_refresh, client=client)
            if meta and "video_analysis" in meta:
                players = parse_balltime_player_stats(meta, team=team_id)
                if players:
                    set_cached_response(cache_key, [p.model_dump() for p in players], TTL_HISTORICAL_MATCH)
                    return players
            raise HudlError(
                f"No video analysis statistics found for video ID '{vid}'. "
                "Ensure the video has finished AI processing and stats are enabled in Balltime."
            )

        # 2. If not resolved to a video, check if it's a scheduled match without an uploaded video
        try:
            sched_matches = await self.get_team_schedule(team_id=team_id, client=client)
            matched_sched = next((m for m in sched_matches if m.match_id == str(match_id).strip()), None)
            if matched_sched:
                raise HudlError(
                    f"Scheduled match '{match_id}' (vs {matched_sched.opponent_name}) does not have an uploaded match video. "
                    "Individual athlete box scores and advanced stats are generated from uploaded video recordings. "
                    "Use 'list_volleyball_matches' to see available video matches."
                )
        except HudlError:
            raise
        except Exception:
            pass

        raise HudlError(
            f"Could not find match or video '{match_id}'. "
            "Please call 'list_volleyball_matches' to find available match and video IDs."
        )

    async def get_rotation_stats(
        self,
        match_id: str,
        team_id: Optional[str] = None,
        force_refresh: bool = False,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[RotationStats]:
        """Fetch rotation breakdown (P1 - P6) metrics for a volleyball match (cached 7 days)."""
        if not match_id:
            raise HudlError("match_id is required to fetch rotation statistics.")

        cache_key = compute_cache_key("rotation_stats", {"match_id": match_id.strip(), "team_id": team_id})
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached and isinstance(cached, list):
                return [RotationStats.model_validate(r) for r in cached]

        # 1. Resolve to Balltime video ID (handles UUIDs, titles, and scheduled match IDs)
        vid = await self.resolve_video_id(match_id, client=client)

        if vid:
            meta = await self.get_video_metadata(vid, force_refresh=force_refresh, client=client)
            if meta and "video_analysis" in meta:
                rotations = parse_balltime_rotation_stats(meta, team=team_id or "a")
                if rotations:
                    set_cached_response(cache_key, [r.model_dump() for r in rotations], TTL_HISTORICAL_MATCH)
                    return rotations
            raise HudlError(
                f"No rotation breakdown data found for video ID '{vid}'. "
                "Ensure the video has finished AI processing and stats are enabled in Balltime."
            )

        # 2. If not resolved to a video, check if it's a scheduled match without an uploaded video
        try:
            sched_matches = await self.get_team_schedule(team_id=team_id, client=client)
            matched_sched = next((m for m in sched_matches if m.match_id == str(match_id).strip()), None)
            if matched_sched:
                raise HudlError(
                    f"Scheduled match '{match_id}' (vs {matched_sched.opponent_name}) does not have an uploaded match video. "
                    "Rotation breakdown statistics are generated from analyzed video recordings. "
                    "Use 'list_volleyball_matches' to see available video matches."
                )
        except HudlError:
            raise
        except Exception:
            pass

        raise HudlError(
            f"Could not find match or video '{match_id}'. "
            "Please call 'list_volleyball_matches' to find available match and video IDs."
        )

    async def get_game_actions(
        self,
        match_id: str,
        set_number: Optional[int] = None,
        action_type: Optional[str] = None,
        player: Optional[str] = None,
        team: Optional[str] = None,
        quality: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        force_refresh: bool = False,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[VolleyballAction]:
        """Retrieve all tagged actions and touch events from a volleyball match video (cached 7 days)."""
        if not match_id:
            raise HudlError("match_id is required to fetch game actions.")

        cache_key = compute_cache_key(
            "game_actions",
            {
                "match_id": match_id.strip(),
                "set": set_number,
                "action": action_type,
                "player": player,
                "team": team,
                "quality": quality,
                "limit": limit,
                "offset": offset,
            },
        )
        if not force_refresh:
            cached = get_cached_response(cache_key)
            if cached and isinstance(cached, list):
                return [VolleyballAction.model_validate(a) for a in cached]

        vid = await self.resolve_video_id(match_id, client=client)
        if not vid:
            try:
                sched_matches = await self.get_team_schedule(team_id=team, client=client)
                matched_sched = next((m for m in sched_matches if m.match_id == str(match_id).strip()), None)
                if matched_sched:
                    raise HudlError(
                        f"Scheduled match '{match_id}' (vs {matched_sched.opponent_name}) does not have an uploaded match video. "
                        "Action feeds are generated from analyzed video recordings. "
                        "Use 'list_volleyball_matches' to see available video matches."
                    )
            except HudlError:
                raise
            except Exception:
                pass

            raise HudlError(
                f"Could not resolve match or video identifier '{match_id}'. "
                "Please use 'list_volleyball_matches' to find available match and video IDs."
            )

        meta = await self.get_video_metadata(vid, force_refresh=force_refresh, client=client)
        if not meta or "video_analysis" not in meta:
            raise HudlError(
                f"No video analysis breakdown data found for match '{match_id}' (ID: {vid})."
            )

        actions = parse_video_actions(
            meta,
            set_number=set_number,
            action_type=action_type,
            player=player,
            team=team,
            quality=quality,
            limit=limit,
            offset=offset,
        )
        if actions:
            set_cached_response(cache_key, [a.model_dump() for a in actions], TTL_HISTORICAL_MATCH)
        return actions
