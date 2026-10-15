"""Unit tests for Hudl HTTPX GraphQL client and authentication handling."""

import os
import json
from pathlib import Path
import pytest
import httpx

from hudl_mcp.client import (
    DEFAULT_API_URL,
    HudlAuthError,
    HudlClient,
    HudlError,
    HudlGraphQLError,
    execute_graphql,
    get_browser_headers,
    get_hudl_cookie,
    get_hudl_team_id,
)


def test_get_hudl_cookie(monkeypatch):
    """Verify cookie retrieval and formatting."""
    # When empty
    monkeypatch.setenv("HUDL_COOKIE", "")
    assert get_hudl_cookie() is None

    # When raw token provided
    monkeypatch.setenv("HUDL_COOKIE", "session_token_12345")
    assert get_hudl_cookie() == "ident=session_token_12345;"

    # When full cookie string provided
    monkeypatch.setenv("HUDL_COOKIE", "ident=token1; hudl_session=token2;")
    assert get_hudl_cookie() == "ident=token1; hudl_session=token2;"


def test_get_hudl_cookie_from_auth_state(monkeypatch, tmp_path: Path):
    """Verify get_hudl_cookie loads from auth_state.json when HUDL_COOKIE is not set."""
    import json
    auth_file = tmp_path / "auth_state.json"
    auth_data = {
        "cookies": [
            {"name": "ident", "value": "auth_state_token_999", "domain": ".hudl.com"},
            {"name": "t", "value": "948881", "domain": ".hudl.com"},
        ]
    }
    auth_file.write_text(json.dumps(auth_data), encoding="utf-8")

    monkeypatch.delenv("HUDL_COOKIE", raising=False)
    monkeypatch.setenv("HUDL_AUTH_STATE_PATH", str(auth_file))

    cookie = get_hudl_cookie()
    assert cookie is not None
    assert "ident=auth_state_token_999;" in cookie
    assert "ident=auth_state_token_999;" in cookie
    assert "t=948881;" in cookie


def test_get_hudl_team_id_variants(monkeypatch):
    """Verify team ID extraction from HUDL_TEAM_ID, HUDLE_TEAM_ID, and cookie 't'."""
    # 1. Explicit HUDL_TEAM_ID
    monkeypatch.setenv("HUDL_TEAM_ID", "111222")
    monkeypatch.delenv("HUDLE_TEAM_ID", raising=False)
    assert get_hudl_team_id() == "111222"

    # 2. User typo HUDLE_TEAM_ID
    monkeypatch.delenv("HUDL_TEAM_ID", raising=False)
    monkeypatch.setenv("HUDLE_TEAM_ID", "333444")
    assert get_hudl_team_id() == "333444"

    # 3. Auto-extracted from cookie t
    monkeypatch.delenv("HUDL_TEAM_ID", raising=False)
    monkeypatch.delenv("HUDLE_TEAM_ID", raising=False)
    monkeypatch.setenv("HUDL_COOKIE", "ident=valid_token; p=sport=vb; t=948881; other=1;")
    assert get_hudl_team_id() == "948881"

    # 4. When none present
    monkeypatch.setenv("HUDL_TEAM_ID", "")
    monkeypatch.setenv("HUDLE_TEAM_ID", "")
    monkeypatch.setenv("HUDL_COOKIE", "ident=clean_cookie_no_t;")
    assert get_hudl_team_id() is None


@pytest.mark.asyncio
async def test_get_user_teams_mock(monkeypatch):
    """Verify get_user_teams fetches and parses teams from /api/v2/teams."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=valid_token; t=948881;")
    client = HudlClient()

    mock_teams_data = [
        {
            "teamId": "948881",
            "name": "Basel NLB",
            "role": "Coach",
            "school": {"name": "SV Volley Wyna 1"},
            "seasons": [{"name": "2026-2027 Season", "isCurrentSeason": True}],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if "api/v2/teams" in str(request.url):
            return httpx.Response(status_code=200, json=mock_teams_data)
        return httpx.Response(status_code=404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        teams = await client.get_user_teams(client=http_client)
        assert len(teams) == 1
        assert teams[0].team_id == "948881"
        assert teams[0].name == "Basel NLB"
        assert teams[0].school_name == "SV Volley Wyna 1"
        assert teams[0].role == "Coach"
        assert teams[0].current_season == "2026-2027 Season"
        assert teams[0].is_current is True


def test_get_browser_headers(monkeypatch):
    """Verify realistic browser headers are populated."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=test_token;")
    headers = get_browser_headers()

    assert headers["Origin"] in ("https://www.hudl.com", "https://app.hudl.com")
    assert "hudl.com" in headers["Referer"]
    assert headers["Content-Type"] == "application/json"
    assert "User-Agent" in headers
    assert headers["Cookie"] == "ident=test_token;"


@pytest.mark.asyncio
async def test_execute_graphql_missing_cookie(monkeypatch):
    """Verify execute_graphql raises HudlAuthError when cookie is absent."""
    monkeypatch.setenv("HUDL_COOKIE", "")
    with pytest.raises(HudlAuthError, match="No Hudl session cookie found"):
        await execute_graphql(query="query { test }")


@pytest.mark.asyncio
async def test_execute_graphql_401_unauthorized(monkeypatch):
    """Verify execute_graphql raises HudlAuthError on HTTP 401."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=expired_token;")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=401, text="Unauthorized")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HudlAuthError, match="Hudl authentication failed \\(HTTP 401\\)"):
            await execute_graphql(query="query { test }", client=client)


@pytest.mark.asyncio
async def test_execute_graphql_403_forbidden(monkeypatch):
    """Verify execute_graphql raises HudlAuthError on HTTP 403."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=forbidden_token;")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=403, text="Forbidden")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HudlAuthError, match="Hudl authentication failed \\(HTTP 403\\)"):
            await execute_graphql(query="query { test }", client=client)


@pytest.mark.asyncio
async def test_execute_graphql_graphql_unauthenticated_error(monkeypatch):
    """Verify execute_graphql raises HudlAuthError on GraphQL UNAUTHENTICATED error payload."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=bad_token;")

    error_payload = {
        "errors": [
            {
                "message": "User session has expired",
                "extensions": {"code": "UNAUTHENTICATED"},
            }
        ],
        "data": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=error_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HudlAuthError, match="GraphQL UNAUTHENTICATED error"):
            await execute_graphql(query="query { test }", client=client)


@pytest.mark.asyncio
async def test_execute_graphql_generic_graphql_error(monkeypatch):
    """Verify execute_graphql raises HudlGraphQLError on non-auth GraphQL errors."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=valid_token;")

    error_payload = {
        "errors": [{"message": "Cannot query field 'invalidField' on type 'Query'."}],
        "data": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=error_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HudlGraphQLError, match="Cannot query field 'invalidField'"):
            await execute_graphql(query="query { test }", client=client)


@pytest.mark.asyncio
async def test_execute_graphql_success(monkeypatch):
    """Verify execute_graphql returns data dict on success."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=valid_token;")

    expected_data = {"team": {"id": "123", "name": "Hawks"}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Cookie"] == "ident=valid_token;"
        assert request.headers["Origin"] in ("https://www.hudl.com", "https://app.hudl.com")
        assert "hudl.com" in request.headers["Referer"]
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["query"] == "query GetTeam { team { id } }"
        return httpx.Response(status_code=200, json={"data": expected_data})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        data = await execute_graphql(query="query GetTeam { team { id } }", client=client)
        assert data == expected_data


@pytest.mark.asyncio
async def test_hudl_client_missing_team_id(monkeypatch):
    """Verify HudlClient.get_recent_matches raises HudlError if no team_id is supplied or set."""
    monkeypatch.setenv("HUDL_TEAM_ID", "")
    monkeypatch.setenv("HUDLE_TEAM_ID", "")
    monkeypatch.setenv("HUDL_COOKIE", "ident=valid_cookie_without_t;")
    client = HudlClient(team_id=None)
    with pytest.raises(HudlError, match="No team_id provided and HUDL_TEAM_ID is not configured"):
        await client.get_recent_matches(team_id=None)


@pytest.mark.asyncio
async def test_hudl_client_missing_match_id():
    """Verify HudlClient requires match_id for player stats and rotation stats."""
    client = HudlClient()
    with pytest.raises(HudlError, match="match_id is required"):
        await client.get_match_player_stats(match_id="")
    with pytest.raises(HudlError, match="match_id is required"):
        await client.get_rotation_stats(match_id="")


def test_to_balltime_video_id():
    """Verify conversion of UUID, 24-hex Hudl ID, and base64 GraphQL ID."""
    from hudl_mcp.client import to_balltime_video_id

    uuid_id = "6ace625e-a504-8ba5-18a7-b1a500000001"
    assert to_balltime_video_id(uuid_id) == uuid_id

    hex_id = "6ace625ea5048ba518a7b1a5"
    assert to_balltime_video_id(hex_id) == uuid_id

    b64_id = "VmlkZW82YWNlNjI1ZWE1MDQ4YmE1MThhN2IxYTU="
    assert to_balltime_video_id(b64_id) == uuid_id


def test_get_balltime_token(monkeypatch):
    """Verify extracting token from ident query parameters."""
    from hudl_mcp.client import get_balltime_token

    monkeypatch.setenv("HUDL_COOKIE", "ident=a=mock_jwt_token_123&u=user_id; other=val")
    assert get_balltime_token() == "mock_jwt_token_123"

    monkeypatch.setenv("HUDL_COOKIE", "other=val")
    assert get_balltime_token() is None


@pytest.mark.asyncio
async def test_get_balltime_videos_mock(monkeypatch):
    """Verify get_balltime_videos queries Balltime library and parses matches."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=a=valid_token;")
    client = HudlClient()

    def handler(request: httpx.Request) -> httpx.Response:
        assert "backend.balltime.com/library/videos" in str(request.url)
        assert request.headers["Authorization"] == "Bearer valid_token"
        return httpx.Response(
            status_code=200,
            json={
                "videos": [
                    {
                        "id": "6ace625e-a504-8ba5-18a7-b1a500000001",
                        "title": "LUTRY  VS Voléro Zürich",
                        "video_file_date": "2026-10-13",
                        "stats_status": "stats_available",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        videos = await client.get_balltime_videos(client=http_client)
        assert len(videos) == 1
        assert videos[0].opponent_name == "LUTRY  VS Voléro Zürich"


@pytest.mark.asyncio
async def test_get_game_actions_and_stats_mock(monkeypatch):
    """Verify get_match_player_stats, get_rotation_stats, and get_game_actions with Balltime."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=a=valid_token;")
    client = HudlClient()

    sample_meta = [
        {
            "name": "LUTRY  VS Voléro Zürich",
            "team_a_name_override": "Lutry-Lavaux",
            "team_b_name_override": "Voléro Zürich",
            "player_names": {
                "10": {"team": "a", "jersey_number": 17, "id": "a_17"},
            },
            "video_analysis": [
                {
                    "id": 1,
                    "set_number": 1,
                    "serving_team": "b",
                    "team_won": "a",
                    "actions": [
                        {
                            "id": 501,
                            "skill_type": "attack",
                            "team": "a",
                            "player_id": 10,
                            "quality": "kill",
                            "timestamp": 65.0,
                            "positional": {"src_zone": 4, "dest_zone": 5},
                        }
                    ],
                }
            ],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if "videos-metadata" in str(request.url):
            return httpx.Response(status_code=200, json=sample_meta)
        return httpx.Response(status_code=404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        # Player stats
        players = await client.get_match_player_stats("6ace625e-a504-8ba5-18a7-b1a500000001", client=http_client)
        assert len(players) == 1
        assert players[0].kills == 1

        # Rotation stats
        rotations = await client.get_rotation_stats("6ace625e-a504-8ba5-18a7-b1a500000001", client=http_client)
        assert len(rotations) == 6
        assert rotations[0].rotation_name == "P1"

        # Game actions
        actions = await client.get_game_actions("6ace625e-a504-8ba5-18a7-b1a500000001", client=http_client)
        assert len(actions) == 1
        assert actions[0].action_type == "attack"
        assert actions[0].quality == "kill"
        assert actions[0].timestamp_formatted == "01:05"


@pytest.mark.asyncio
async def test_resolve_schedule_id_to_video_and_stats(monkeypatch):
    """Verify schedule ID 34352342 resolves to video 6ace625e-a504-8ba5-18a7-b1a500000001 via opponent name."""
    monkeypatch.setenv("HUDL_COOKIE", "ident=a=valid_token;")
    monkeypatch.setenv("HUDL_TEAM_ID", "948881")
    client = HudlClient()

    schedule_payload = {
        "season_2026": [
            {
                "teamName": "Lutry-Lavaux Volleyball",
                "games": [{"gameId": 34352342, "localDateTime": "10-18-2026 16:00:00", "hasScore": False}],
            },
            {
                "teamName": "Chênois Genève Volleyball",
                "games": [{"gameId": 34359999, "localDateTime": "10-25-2026 14:00:00", "hasScore": False}],
            },
        ]
    }

    balltime_videos_payload = {
        "videos": [
            {
                "id": "6ace625e-a504-8ba5-18a7-b1a500000001",
                "title": "LUTRY  VS Voléro Zürich",
                "video_file_date": "2026-10-13",
                "stats_status": "stats_available",
            }
        ]
    }

    meta_payload = [
        {
            "name": "LUTRY  VS Voléro Zürich",
            "team_a_name_override": "Lutry-Lavaux",
            "player_names": {"1": {"jersey_number": 17, "team": "a"}},
            "video_analysis": [
                {
                    "id": 1,
                    "set_number": 1,
                    "serving_team": "b",
                    "team_won": "a",
                    "actions": [
                        {"id": 1, "skill_type": "attack", "team": "a", "player_id": 1, "quality": "kill"}
                    ],
                }
            ],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "classicfacade/team" in url_str:
            return httpx.Response(status_code=200, json=schedule_payload)
        elif "library/videos" in url_str:
            return httpx.Response(status_code=200, json=balltime_videos_payload)
        elif "videos-metadata" in url_str:
            return httpx.Response(status_code=200, json=meta_payload)
        return httpx.Response(status_code=404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        # 1. resolve_video_id should resolve schedule ID 34352342 to the video UUID
        resolved_vid = await client.resolve_video_id("34352342", client=http_client)
        assert resolved_vid == "6ace625e-a504-8ba5-18a7-b1a500000001"

        # 2. get_match_player_stats with 34352342 should resolve and return player stats
        players = await client.get_match_player_stats("34352342", client=http_client)
        assert len(players) == 1
        assert players[0].kills == 1

        # 3. get_recent_matches should return both videos and schedule, with 34352342 linked
        matches = await client.get_recent_matches(limit=10, client=http_client)
        assert len(matches) == 3  # 1 video + 2 schedule games
        lutry_sched = next(m for m in matches if m.match_id == "34352342")
        assert lutry_sched.video_id == "6ace625e-a504-8ba5-18a7-b1a500000001"

        chenois_sched = next(m for m in matches if m.match_id == "34359999")
        assert chenois_sched.video_id is None

        # 4. Querying a schedule game that has NO uploaded video should give clear error
        with pytest.raises(HudlError, match="Scheduled match '34359999' \\(vs Chênois Genève Volleyball\\) does not have an uploaded match video"):
            await client.get_match_player_stats("34359999", client=http_client)

