"""Unit tests for FastMCP server tool handlers and error formatting."""

from unittest.mock import AsyncMock, patch
import pytest

from hudl_mcp.client import HudlAuthError, HudlGraphQLError
from hudl_mcp.models import MatchSummary, PlayerStats, RotationStats
from hudl_mcp.server import (
    get_game_actions,
    get_match_player_stats,
    get_rotation_breakdown,
    get_user_teams,
    list_volleyball_matches,
    login_to_hudl,
    refresh_hudl_cookie,
)


@pytest.mark.asyncio
async def test_list_volleyball_matches_success():
    """Verify list_volleyball_matches returns formatted markdown table on success."""
    mock_matches = [
        MatchSummary(
            match_id="match-101",
            date="2026-10-10",
            opponent_name="Tigers",
            result="W 3-1",
            home_away="Home",
            score="3-1",
            set_scores=["25-20", "22-25", "25-18", "25-19"],
        )
    ]
    with patch("hudl_mcp.client.HudlClient.get_recent_matches", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_matches
        result = await list_volleyball_matches(team_id="team-999", limit=5)
        assert "Recent Volleyball Matches" in result
        assert "match-101" in result
        assert "Tigers" in result
        assert "W 3-1" in result


@pytest.mark.asyncio
async def test_list_volleyball_matches_auth_error():
    """Verify list_volleyball_matches returns clear action instructions on auth error."""
    with patch("hudl_mcp.client.HudlClient.get_recent_matches", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = HudlAuthError("Session expired")
        result = await list_volleyball_matches(team_id="team-999")
        assert "⚠️ Authentication Error" in result
        assert "login_to_hudl" in result


@pytest.mark.asyncio
async def test_list_volleyball_matches_graphql_error():
    """Verify list_volleyball_matches returns GraphQL schema troubleshooting tip."""
    with patch("hudl_mcp.client.HudlClient.get_recent_matches", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = HudlGraphQLError("Cannot query field 'foo'")
        result = await list_volleyball_matches(team_id="team-999")
        assert "❌ GraphQL Query Error" in result
        assert "queries.py" in result


@pytest.mark.asyncio
async def test_get_match_player_stats_empty_id():
    """Verify get_match_player_stats requires match_id."""
    result = await get_match_player_stats(match_id="")
    assert "Error: 'match_id' parameter is required" in result


@pytest.mark.asyncio
async def test_get_match_player_stats_success():
    """Verify get_match_player_stats returns formatted box score."""
    mock_players = [
        PlayerStats(
            player_name="Alex Morgan",
            jersey_number="4",
            position="OH",
            sets_played=4,
            kills=15,
            attack_errors=3,
            total_attacks=30,
            aces=2,
            digs=10,
            block_solos=1,
            block_assists=2,
        )
    ]
    with patch("hudl_mcp.client.HudlClient.get_match_player_stats", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_players
        result = await get_match_player_stats(match_id="match-101")
        assert "Athlete Box Score" in result
        assert "Alex Morgan" in result
        assert ".400" in result  # (15 - 3) / 30 = 0.400
        assert "TEAM TOTALS" in result


@pytest.mark.asyncio
async def test_get_rotation_breakdown_empty_id():
    """Verify get_rotation_breakdown requires match_id."""
    result = await get_rotation_breakdown(match_id="   ")
    assert "Error: 'match_id' parameter is required" in result


@pytest.mark.asyncio
async def test_get_rotation_breakdown_success():
    """Verify get_rotation_breakdown returns formatted rotation breakdown table."""
    mock_rotations = [
        RotationStats(
            rotation_number=1,
            rotation_name="P1",
            sideout_percentage=65.0,
            sideouts_earned=13,
            sideout_attempts=20,
            point_scoring_percentage=40.0,
            first_ball_sideout_rate=50.0,
            setter_tendencies={"Left": "45%", "Middle": "35%", "Right": "20%"},
        )
    ]
    with patch("hudl_mcp.client.HudlClient.get_rotation_stats", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_rotations
        result = await get_rotation_breakdown(match_id="match-101")
        assert "Rotation Efficiency Breakdown (P1 - P6)" in result
        assert "**P1**" in result
        assert "65.0% (13/20)" in result
        assert "Left: 45%" in result


@pytest.mark.asyncio
async def test_get_game_actions_empty_id():
    """Verify get_game_actions requires match_id."""
    result = await get_game_actions(match_id="")
    assert "Error: 'match_id' parameter is required" in result


@pytest.mark.asyncio
async def test_get_game_actions_success():
    """Verify get_game_actions returns formatted event table."""
    from hudl_mcp.models import VolleyballAction
    mock_actions = [
        VolleyballAction(
            action_id=1,
            rally_id=10,
            set_number=1,
            score="5-4",
            timestamp_seconds=120.0,
            timestamp_formatted="02:00",
            team="a",
            team_name="Lutry-Lavaux",
            player_id="a_17",
            jersey_number="17",
            player_label="#17 (Lutry-Lavaux)",
            action_type="attack",
            quality="kill",
            attack_type="quick",
            first_ball_side_out=True,
            source_zone=3,
            dest_zone=5,
            details="Type: quick, FBSO, Z3, -> Z5",
        )
    ]
    with patch("hudl_mcp.client.HudlClient.get_game_actions", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_actions
        result = await get_game_actions(match_id="vid-123")
        assert "Tagged Match Actions & Events" in result
        assert "#17 (Lutry-Lavaux)" in result
        assert "Attack" in result
        assert "Kill" in result
        assert "02:00" in result


@pytest.mark.asyncio
async def test_get_game_actions_auth_error():
    """Verify get_game_actions handles auth error."""
    with patch("hudl_mcp.client.HudlClient.get_game_actions", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = HudlAuthError("Cookie expired")
        result = await get_game_actions(match_id="vid-123")
        assert "⚠️ Authentication Error" in result
        assert "login_to_hudl" in result


@pytest.mark.asyncio
async def test_login_to_hudl_tool_success():
    """Verify login_to_hudl returns success status and storage state path."""
    with patch("hudl_mcp.server.interactive_login", new_callable=AsyncMock) as mock_login:
        mock_login.return_value = {
            "success": True,
            "masked_cookie": "ident=xyz...123;",
            "storage_state_file": "/Users/user/.hudl_mcp/auth_state.json",
            "message": "Logged in successfully",
        }
        result = await login_to_hudl()
        assert "✅ **Hudl Login Successful!**" in result
        assert "auth_state.json" in result
        assert "ident=xyz...123;" in result


@pytest.mark.asyncio
async def test_login_to_hudl_tool_failure():
    """Verify login_to_hudl returns error diagnostics when user closes browser."""
    with patch("hudl_mcp.server.interactive_login", new_callable=AsyncMock) as mock_login:
        mock_login.return_value = {
            "success": False,
            "error": "The browser window was closed before reaching hudl.com/home.",
        }
        result = await login_to_hudl()
        assert "❌ **Hudl Login Failed**" in result
        assert "browser window was closed" in result


@pytest.mark.asyncio
async def test_refresh_hudl_cookie_no_credentials():
    """Verify refresh_hudl_cookie recommends login_to_hudl when credentials are not in .env."""
    with patch.dict("os.environ", {"HUDL_EMAIL": "", "HUDL_PASSWORD": ""}, clear=False):
        result = await refresh_hudl_cookie()
        assert "Interactive Login Recommended" in result
        assert "login_to_hudl" in result


@pytest.mark.asyncio
async def test_refresh_hudl_cookie_tool_success():
    """Verify refresh_hudl_cookie returns success status when credentials are provided."""
    with patch.dict("os.environ", {"HUDL_EMAIL": "a@b.com", "HUDL_PASSWORD": "secret"}, clear=False):
        with patch("hudl_mcp.server.refresh_session", new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = {
                "success": True,
                "masked_cookie": "ident=xyz...123;",
                "env_file": "/path/to/.env",
                "message": "Logged in successfully",
            }
            result = await refresh_hudl_cookie()
            assert "✅ Hudl Session Refreshed Successfully!" in result
            assert "ident=xyz...123;" in result


@pytest.mark.asyncio
async def test_refresh_hudl_cookie_tool_failure():
    """Verify refresh_hudl_cookie returns diagnostic help on failure when credentials fail."""
    with patch.dict("os.environ", {"HUDL_EMAIL": "a@b.com", "HUDL_PASSWORD": "bad"}, clear=False):
        with patch("hudl_mcp.server.refresh_session", new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = {
                "success": False,
                "error": "Invalid email or password",
            }
            result = await refresh_hudl_cookie()
            assert "❌ Failed to refresh Hudl session: Invalid email or password" in result
            assert "login_to_hudl" in result


@pytest.mark.asyncio
async def test_get_user_teams_tool_success():
    """Verify get_user_teams returns formatted markdown table of user teams."""
    from hudl_mcp.models import TeamInfo
    mock_teams = [
        TeamInfo(
            team_id="948881",
            name="Basel NLB",
            school_name="SV Volley Wyna 1",
            role="Coach",
            current_season="2026-2027 Season",
            is_current=True,
        )
    ]
    with patch("hudl_mcp.client.HudlClient.get_user_teams", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_teams
        result = await get_user_teams()
        assert "Your Hudl Volleyball Teams" in result
        assert "Basel NLB" in result
        assert "`948881`" in result
        assert "SV Volley Wyna 1" in result
        assert "Coach" in result


@pytest.mark.asyncio
async def test_get_user_teams_tool_auth_error():
    """Verify get_user_teams returns auth error instructions."""
    with patch("hudl_mcp.client.HudlClient.get_user_teams", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = HudlAuthError("Session expired")
        result = await get_user_teams()
        assert "⚠️ Authentication Error" in result
        assert "login_to_hudl" in result


