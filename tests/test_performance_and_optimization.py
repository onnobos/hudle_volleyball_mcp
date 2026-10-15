"""Unit tests for Step 1 Context-Window Optimization & Step 2 Rate Limiting / Caching."""

import asyncio
import json
import pytest
import httpx

from hudl_mcp.cache import (
    TTL_HISTORICAL_MATCH,
    TTL_SCHEDULE_TEAM,
    clear_all_cache,
    compute_cache_key,
    get_cached_response,
    set_cached_response,
)
from hudl_mcp.client import HudlSecurityError, execute_graphql
from hudl_mcp.models import (
    MatchSummary,
    PlayerStats,
    RotationStats,
    TeamInfo,
    VolleyballAction,
    render_actions_output,
    render_matches_output,
    render_player_stats_output,
    render_rotation_stats_output,
    render_teams_output,
)
from hudl_mcp.rate_limiter import AsyncTokenBucket, execute_with_retry


def test_models_to_compact_dict():
    """Verify all models produce token-efficient dictionaries without UI metadata."""
    match = MatchSummary(
        match_id="m-123",
        opponent_name="Voléro Zürich",
        date="2026-10-18",
        result="W 3-1",
        score="3-1",
        set_scores=["25-21", "25-23", "20-25", "25-18"],
        video_id="v-uuid-456",
        match_type="video",
    )
    m_dict = match.to_compact_dict()
    assert m_dict["id"] == "m-123"
    assert m_dict["opponent"] == "Voléro Zürich"
    assert m_dict["video_id"] == "v-uuid-456"
    assert "status" not in m_dict

    player = PlayerStats(
        player_name="Lino S.",
        jersey_number="20",
        position="OH",
        sets_played=4,
        kills=10,
        attack_errors=0,
        total_attacks=13,
        aces=3,
        serve_errors=1,
        total_serves=13,
        digs=5,
        receptions=18,
        perfect_passes=5,
        positive_passes=10,
        medium_passes=3,
    )
    p_dict = player.to_compact_dict()
    assert p_dict["num"] == "20"
    assert p_dict["name"] == "Lino S."
    assert p_dict["k"] == 10
    assert p_dict["hit_pct"] == 0.769
    assert p_dict["pass_avg"] == 2.11
    assert "player_id" not in p_dict

    rot = RotationStats(
        rotation_number=1,
        rotation_name="P1",
        sideout_percentage=0.667,
        sideouts_earned=4,
        sideout_attempts=6,
        point_scoring_percentage=0.500,
        points_scored_serving=3,
        serve_attempts=6,
        first_ball_sideout_rate=0.500,
        setter_tendencies={"Left (P4)": 60.0, "Middle (P3)": 40.0},
    )
    r_dict = rot.to_compact_dict()
    assert r_dict["rotation"] == "P1"
    assert r_dict["sideout_pct"] == "66.7%"
    assert r_dict["sideouts"] == "4/6"
    assert r_dict["setter_distribution"]["Left (P4)"] == 60.0

    action = VolleyballAction(
        set_number=2,
        score="14-12",
        timestamp_formatted="22:15",
        timestamp_seconds=1335.0,
        team="a",
        player_label="#20 Lino S.",
        action_type="attack",
        quality="kill",
        attack_type="pipe",
        source_zone=6,
        dest_zone=5,
        first_ball_side_out=True,
    )
    a_dict = action.to_compact_dict()
    assert a_dict["set"] == 2
    assert a_dict["score"] == "14-12"
    assert a_dict["action"] == "attack"
    assert a_dict["quality"] == "kill"
    assert a_dict["route"] == "pipe"
    assert a_dict["zones"] == "Z6->Z5"
    assert a_dict["fbso"] is True


def test_dual_mode_renderers():
    """Verify render_*_output produces Markdown or token-efficient compact JSON."""
    players = [
        PlayerStats(
            player_name="Lino S.",
            jersey_number="20",
            kills=10,
            attack_errors=0,
            total_attacks=13,
        )
    ]

    # 1. Default markdown
    md = render_player_stats_output(players, match_id="test-match", output_format="markdown")
    assert "| # | Player | Pos | SP | K | E | TA | Hit % |" in md
    assert "Lino S." in md

    # 2. Compact JSON
    compact = render_player_stats_output(players, match_id="test-match", output_format="compact")
    parsed = json.loads(compact)
    assert isinstance(parsed, list)
    assert parsed[0]["name"] == "Lino S."
    assert parsed[0]["k"] == 10
    assert " " not in compact.split('"name":')[0]  # token-optimized with no extra whitespace


@pytest.mark.asyncio
async def test_strict_read_only_policy(monkeypatch):
    """Verify that GraphQL mutations are strictly rejected with HudlSecurityError."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=dummy;")
    mutation_query = """
    mutation UpdateRoster($teamId: ID!) {
        deletePlayer(id: "123") { success }
    }
    """
    with pytest.raises(HudlSecurityError, match="Read-Only Policy Enforced"):
        await execute_graphql(query=mutation_query)


def test_persistent_disk_cache():
    """Verify disk cache set, get, TTL, and clear operations."""
    clear_all_cache()
    key = compute_cache_key("test_match", {"id": "123"})
    data = {"match_id": "123", "stats": [1, 2, 3]}

    set_cached_response(key, data, expire_seconds=TTL_HISTORICAL_MATCH)
    cached = get_cached_response(key)
    assert cached == data

    clear_all_cache()
    assert get_cached_response(key) is None


@pytest.mark.asyncio
async def test_rate_limiter_token_bucket():
    """Verify token bucket rate limiter properly limits throughput."""
    limiter = AsyncTokenBucket(rate=10.0, capacity=2.0)
    # First 2 should be immediate (burst)
    start = asyncio.get_event_loop().time()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_execute_with_retry_on_429():
    """Verify execute_with_retry retries on HTTP 429 and succeeds."""
    calls = 0

    async def mock_request():
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(429, headers={"Retry-After": "0.01"})
        return httpx.Response(200, json={"status": "ok"})

    resp = await execute_with_retry(mock_request, initial_backoff=0.01)
    assert resp.status_code == 200
    assert calls == 3


@pytest.mark.asyncio
async def test_mcp_prompts_registered():
    """Verify all 5 coaching and scouting prompts are registered on FastMCP and render correctly."""
    from hudl_mcp.server import mcp

    prompts = await mcp.list_prompts()
    prompt_names = {p.name for p in prompts}
    expected_prompts = {
        "scout_opponent",
        "analyze_rotation_weaknesses",
        "match_mvp_breakdown",
        "datavolley_export",
        "serve_receive_audit",
    }
    assert expected_prompts.issubset(prompt_names)

    # 1. Test scout_opponent prompt render
    p1 = await mcp.get_prompt("scout_opponent", {"opponent_name": "Tigers"})
    assert "Tigers" in p1.messages[0].content.text
    assert "list_volleyball_matches" in p1.messages[0].content.text
    assert "get_rotation_breakdown" in p1.messages[0].content.text

    # 2. Test analyze_rotation_weaknesses prompt render
    p2 = await mcp.get_prompt("analyze_rotation_weaknesses", {"match_id": "match-999"})
    assert "match-999" in p2.messages[0].content.text
    assert "P1, P2, P3, P4, P5, and P6" in p2.messages[0].content.text

    # 3. Test match_mvp_breakdown prompt render
    p3 = await mcp.get_prompt("match_mvp_breakdown", {"match_id": "match-999"})
    assert "match-999" in p3.messages[0].content.text
    assert "True Points" in p3.messages[0].content.text
    assert "Match MVP" in p3.messages[0].content.text

    # 4. Test datavolley_export prompt render
    p4 = await mcp.get_prompt("datavolley_export", {"match_id": "match-999"})
    assert "match-999" in p4.messages[0].content.text
    assert ".dvw" in p4.messages[0].content.text
    assert "DataVolley" in p4.messages[0].content.text

    # 5. Test serve_receive_audit prompt render
    p5 = await mcp.get_prompt("serve_receive_audit", {"match_id": "match-999"})
    assert "match-999" in p5.messages[0].content.text
    assert "Passer Efficiency Ratings" in p5.messages[0].content.text


@pytest.mark.asyncio
async def test_auto_refresh_on_401(monkeypatch):
    """Verify execute_graphql auto-refreshes session and retries when credentials are present."""
    from unittest.mock import AsyncMock, patch
    from hudl_mcp.client import execute_graphql

    monkeypatch.setenv("HUDL_COOKIE", "ident=old_expired_cookie;")
    monkeypatch.setenv("HUDL_EMAIL", "coach@volleyball.com")
    monkeypatch.setenv("HUDL_PASSWORD", "secret123")

    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call returns 401 Unauthorized
            return httpx.Response(401, json={"error": "Unauthorized"})
        # Second call returns success
        return httpx.Response(200, json={"data": {"team": {"id": "team-123"}}})

    transport = httpx.MockTransport(mock_handler)
    mock_client = httpx.AsyncClient(transport=transport)

    with patch("hudl_mcp.auth_refresh.refresh_session", new_callable=AsyncMock) as mock_refresh:
        mock_refresh.return_value = {"success": True, "masked_cookie": "ident=new_cookie..."}
        res = await execute_graphql(
            query="query GetTeam { team { id } }",
            client=mock_client,
        )
        assert res == {"team": {"id": "team-123"}}
        assert mock_refresh.called
        assert call_count == 2


@pytest.mark.asyncio
async def test_auto_refresh_failure_returns_actionable_error(monkeypatch):
    """Verify execute_graphql raises HudlAuthError with instructions if refresh fails or no credentials."""
    from unittest.mock import AsyncMock, patch
    from hudl_mcp.client import HudlAuthError, execute_graphql

    monkeypatch.setenv("HUDL_COOKIE", "ident=old_expired_cookie;")
    monkeypatch.delenv("HUDL_EMAIL", raising=False)
    monkeypatch.delenv("HUDL_PASSWORD", raising=False)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized"})

    transport = httpx.MockTransport(mock_handler)
    mock_client = httpx.AsyncClient(transport=transport)

    with pytest.raises(HudlAuthError) as exc_info:
        await execute_graphql(
            query="query GetTeam { team { id } }",
            client=mock_client,
        )
    assert "login_to_hudl" in str(exc_info.value)


def test_secure_keyring_storage(monkeypatch):
    """Verify keyring storage saves, retrieves, and handles errors with graceful fallback."""
    from hudl_mcp.security import (
        delete_secure_session,
        get_secure_cookie,
        get_secure_team_id,
        save_secure_session,
    )
    import keyring.backend

    # In-memory keyring backend for test isolation
    class MemoryKeyring(keyring.backend.KeyringBackend):
        priority = 1
        def __init__(self):
            self._vault = {}
        def set_password(self, service, username, password):
            self._vault[(service, username)] = password
        def get_password(self, service, username):
            return self._vault.get((service, username))
        def delete_password(self, service, username):
            self._vault.pop((service, username), None)

    mem_kr = MemoryKeyring()
    monkeypatch.setattr("keyring.get_keyring", lambda: mem_kr)
    monkeypatch.setattr("keyring.set_password", mem_kr.set_password)
    monkeypatch.setattr("keyring.get_password", mem_kr.get_password)
    monkeypatch.setattr("keyring.delete_password", mem_kr.delete_password)

    # Test saving session
    assert save_secure_session("ident=session_token_abc;", team_id="team_456") is True
    assert get_secure_cookie() == "ident=session_token_abc;"
    assert get_secure_team_id() == "team_456"

    # Test deleting session
    assert delete_secure_session() is True
    assert get_secure_cookie() is None
    assert get_secure_team_id() is None
