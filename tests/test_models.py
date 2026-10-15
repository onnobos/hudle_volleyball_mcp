"""Unit tests for Pydantic models, derived stats calculations, and formatters."""

import pytest
from hudl_mcp.models import (
    MatchSummary,
    PlayerStats,
    RotationStats,
    format_hit_pct,
    format_matches_markdown,
    format_pct,
    format_player_stats_markdown,
    format_rotation_stats_markdown,
    parse_matches_response,
    parse_player_stats_response,
    parse_rotation_stats_response,
)


def test_player_stats_derived_metrics_calculation():
    """Verify hitting percentage, total blocks, and points are automatically calculated."""
    player = PlayerStats(
        player_name="Sarah Miller",
        jersey_number="12",
        position="OH",
        sets_played=4,
        kills=14,
        attack_errors=4,
        total_attacks=25,
        aces=2,
        block_solos=1,
        block_assists=2,
    )

    # Hitting % = (14 - 4) / 25 = 10 / 25 = 0.400
    assert player.hitting_percentage == 0.400
    # Total blocks = 1 + (0.5 * 2) = 2.0
    assert player.total_blocks == 2.0
    # Points = 14 + 2 + 1 + 1.0 = 18.0
    assert player.points == 18.0


def test_player_stats_zero_attacks():
    """Verify zero attacks yields 0.000 hitting percentage rather than ZeroDivisionError."""
    player = PlayerStats(
        player_name="Jane Doe",
        jersey_number="5",
        position="L",
        sets_played=4,
        kills=0,
        attack_errors=0,
        total_attacks=0,
    )
    assert player.hitting_percentage == 0.000


def test_player_stats_negative_hitting_percentage():
    """Verify negative hitting percentage when errors exceed kills."""
    player = PlayerStats(
        player_name="Sub Hitter",
        kills=1,
        attack_errors=3,
        total_attacks=5,
    )
    # (1 - 3) / 5 = -2 / 5 = -0.400
    assert player.hitting_percentage == -0.400
    assert format_hit_pct(player.hitting_percentage) == "-.400"


def test_format_hit_pct():
    """Verify baseball/volleyball style hitting percentage formatting."""
    assert format_hit_pct(0.350) == ".350"
    assert format_hit_pct(0.0) == ".000"
    assert format_hit_pct(-0.125) == "-.125"
    assert format_hit_pct(1.0) == "1.000"
    assert format_hit_pct(None) == ".000"


def test_parse_matches_response_relay_style():
    """Verify parsing matches formatted with Relay edges and nodes."""
    raw = {
        "data": {
            "team": {
                "id": "team-123",
                "name": "State High Volleyball",
                "matches": {
                    "edges": [
                        {
                            "node": {
                                "id": "match-901",
                                "date": "2026-10-10",
                                "opponent": {"name": "Lions Academy"},
                                "result": {"outcome": "W", "score": "3-1", "setScores": ["25-22", "23-25", "25-18", "25-20"]},
                                "homeAway": "Home",
                            }
                        },
                        {
                            "node": {
                                "id": "match-902",
                                "date": "2026-10-12",
                                "opponent": {"name": "Spartan Prep"},
                                "result": {"outcome": "L", "score": "2-3"},
                                "homeAway": "Away",
                            }
                        },
                    ]
                },
            }
        }
    }

    matches = parse_matches_response(raw)
    assert len(matches) == 2
    assert matches[0].match_id == "match-901"
    assert matches[0].opponent_name == "Lions Academy"
    assert matches[0].result == "W 3-1"
    assert matches[0].set_scores == ["25-22", "23-25", "25-18", "25-20"]
    assert matches[1].match_id == "match-902"
    assert matches[1].opponent_name == "Spartan Prep"
    assert matches[1].result == "L 2-3"


def test_parse_player_stats_response():
    """Verify parsing athlete box scores from GraphQL response."""
    raw = {
        "data": {
            "match": {
                "id": "match-901",
                "volleyballStats": {
                    "athleteStats": [
                        {
                            "athlete": {
                                "id": "ath-1",
                                "name": "Emma Watson",
                                "jerseyNumber": "7",
                                "position": "OH",
                            },
                            "stats": {
                                "setsPlayed": 3,
                                "kills": 12,
                                "attackErrors": 2,
                                "totalAttacks": 20,
                                "serviceAces": 3,
                                "digs": 8,
                                "blockSolos": 1,
                                "blockAssists": 0,
                                "passRating": 2.25,
                            },
                        }
                    ]
                }
            }
        }
    }

    players = parse_player_stats_response(raw)
    assert len(players) == 1
    p = players[0]
    assert p.player_name == "Emma Watson"
    assert p.jersey_number == "7"
    assert p.position == "OH"
    assert p.kills == 12
    assert p.attack_errors == 2
    assert p.total_attacks == 20
    assert p.hitting_percentage == 0.500
    assert p.aces == 3
    assert p.digs == 8
    assert p.pass_rating == 2.25
    assert p.points == 16.0


def test_parse_rotation_stats_response():
    """Verify parsing rotation breakdown metrics (P1 to P6)."""
    raw = {
        "data": {
            "match": {
                "id": "match-901",
                "rotationBreakdown": {
                    "rotations": [
                        {
                            "rotationNumber": 2,
                            "rotationName": "P2",
                            "sideoutPercentage": 65.0,
                            "sideoutsEarned": 13,
                            "sideoutAttempts": 20,
                            "pointScoringPercentage": 42.0,
                            "pointsScoredServing": 8,
                            "serveAttempts": 19,
                            "firstBallSideoutRate": 55.0,
                            "setterTendencies": {"left": 50, "middle": 30, "right": 20},
                        },
                        {
                            "rotationNumber": 1,
                            "rotationName": "P1",
                            "sideoutPercentage": 70.0,
                            "sideoutsEarned": 14,
                            "sideoutAttempts": 20,
                            "pointScoringPercentage": 50.0,
                            "firstBallSideoutRate": 60.0,
                        },
                    ]
                }
            }
        }
    }

    rotations = parse_rotation_stats_response(raw)
    assert len(rotations) == 2
    # Should be sorted by rotation_number (P1 then P2)
    assert rotations[0].rotation_number == 1
    assert rotations[0].rotation_name == "P1"
    assert rotations[0].sideout_percentage == 70.0

    assert rotations[1].rotation_number == 2
    assert rotations[1].rotation_name == "P2"
    assert rotations[1].setter_tendencies == {"left": 50, "middle": 30, "right": 20}


def test_format_markdown_tables():
    """Verify Markdown tables formatting outputs."""
    matches = [
        MatchSummary(
            match_id="m1",
            date="2026-10-14",
            opponent_name="Rivals HS",
            result="W 3-0",
            home_away="Home",
            score="3-0",
        )
    ]
    md_matches = format_matches_markdown(matches, team_id="team-999")
    assert "Recent Volleyball Matches (Team ID: team-999)" in md_matches
    assert "| `m1` | 2026-10-14 | **Rivals HS** | W 3-0 | Home | 3-0 |" in md_matches

    players = [
        PlayerStats(
            player_name="Chloe Bennett",
            jersey_number="10",
            position="MB",
            sets_played=3,
            kills=8,
            attack_errors=1,
            total_attacks=12,
            aces=1,
            block_solos=2,
            block_assists=4,
        )
    ]
    md_players = format_player_stats_markdown(players, match_id="m1")
    assert "Athlete Box Score" in md_players
    assert "Chloe Bennett" in md_players
    assert "TEAM TOTALS" in md_players

    rotations = [
        RotationStats(
            rotation_number=1,
            rotation_name="P1",
            sideout_percentage=60.0,
            sideouts_earned=6,
            sideout_attempts=10,
            point_scoring_percentage=45.0,
            first_ball_sideout_rate=50.0,
            setter_tendencies={"LeftPercent": 50, "MiddlePercent": 30, "RightPercent": 20},
        )
    ]
    md_rot = format_rotation_stats_markdown(rotations, match_id="m1")
    assert "Rotation Efficiency Breakdown (P1 - P6)" in md_rot
    assert "**P1**" in md_rot
    assert "Left: 50%" in md_rot


def test_parse_matches_response_balltime_videos():
    """Verify parsing Balltime library/videos response."""
    raw = {
        "videos": [
            {
                "id": "6ace625e-a504-8ba5-18a7-b1a500000001",
                "title": "LUTRY  VS Voléro Zürich",
                "video_file_date": "2026-10-13T17:17:31.637",
                "video_type": "scouting",
                "stats_status": "stats_available",
                "processing_status": "processed",
                "score": {"sets": [{"a": 25, "b": 20}]},
            }
        ]
    }
    matches = parse_matches_response(raw)
    assert len(matches) == 1
    assert matches[0].match_id == "6ace625e-a504-8ba5-18a7-b1a500000001"
    assert matches[0].opponent_name == "LUTRY  VS Voléro Zürich"
    assert matches[0].result == "stats_available"


def test_format_video_timestamp():
    """Verify video timestamp formatting into MM:SS and H:MM:SS."""
    from hudl_mcp.models import format_video_timestamp
    assert format_video_timestamp(0) == "00:00"
    assert format_video_timestamp(64.5) == "01:04"
    assert format_video_timestamp(2861.0) == "47:41"
    assert format_video_timestamp(3665.0) == "1:01:05"
    assert format_video_timestamp(None) == "-"


def test_parse_video_actions_and_filtering():
    """Verify parse_video_actions extracts touches and respects filters."""
    from hudl_mcp.models import parse_video_actions, format_actions_markdown
    sample_meta = {
        "name": "LUTRY VS Voléro Zürich",
        "team_a_name_override": "Lutry-Lavaux",
        "team_b_name_override": "Voléro Zürich",
        "player_names": {
            "10": {"team": "a", "jersey_number": 17, "id": "a_17"},
            "20": {"team": "b", "jersey_number": 5, "id": "b_5"},
        },
        "video_analysis": [
            {
                "id": 1,
                "set_number": 1,
                "start": 100.0,
                "serving_team": "a",
                "team_won": "a",
                "score": {"setScore": {"a": 1, "b": 0}},
                "actions": [
                    {
                        "id": 101,
                        "skill_type": "serve",
                        "team": "a",
                        "player_id": 10,
                        "quality": "ace",
                        "timestamp": 102.5,
                        "positional": {"src_zone": 1, "dest_zone": 5},
                    },
                    {
                        "id": 102,
                        "skill_type": "receive",
                        "team": "b",
                        "player_id": 20,
                        "quality": "error",
                        "timestamp": 104.0,
                        "positional": {"src_zone": 5},
                    },
                ],
            },
            {
                "id": 2,
                "set_number": 2,
                "start": 200.0,
                "serving_team": "b",
                "team_won": "a",
                "score": {"setScore": {"a": 0, "b": 0}},
                "actions": [
                    {
                        "id": 103,
                        "skill_type": "attack",
                        "team": "a",
                        "player_id": 10,
                        "quality": "kill",
                        "timestamp": 205.0,
                        "attack_type": "pipe",
                        "first_ball_side_out": True,
                        "positional": {"src_zone": 6, "dest_zone": 1},
                    }
                ],
            },
        ],
    }

    # All actions
    all_acts = parse_video_actions(sample_meta)
    assert len(all_acts) == 3

    # Filter by set 1
    set1_acts = parse_video_actions(sample_meta, set_number=1)
    assert len(set1_acts) == 2
    assert set1_acts[0].action_type == "serve"
    assert set1_acts[0].quality == "ace"
    assert set1_acts[0].timestamp_formatted == "01:42"
    assert set1_acts[0].jersey_number == "17"

    # Filter by skill
    attacks = parse_video_actions(sample_meta, action_type="attack")
    assert len(attacks) == 1
    assert attacks[0].attack_type == "pipe"
    assert attacks[0].first_ball_side_out is True

    # Filter by player jersey
    player17 = parse_video_actions(sample_meta, player="17")
    assert len(player17) == 2

    # Filter by team
    team_b_acts = parse_video_actions(sample_meta, team="b")
    assert len(team_b_acts) == 1
    assert team_b_acts[0].player_label == "#5 (Voléro Zürich)"

    # Format markdown
    md = format_actions_markdown(all_acts, match_name="LUTRY VS Voléro Zürich")
    assert "### Tagged Match Actions & Events - **LUTRY VS Voléro Zürich**" in md
    assert "**Kills**: 1" in md
    assert "**Aces**: 1" in md
    assert "**Errors**: 1" in md
    assert "| 1 | 1-0 | `01:42` | **#17 (Lutry-Lavaux)** | Serve | Ace | Z1, -> Z5 |" in md


def test_parse_balltime_player_and_rotation_stats():
    """Verify parse_balltime_player_stats and parse_balltime_rotation_stats."""
    from hudl_mcp.models import parse_balltime_player_stats, parse_balltime_rotation_stats
    sample_meta = {
        "name": "LUTRY VS Voléro Zürich",
        "team_a_name_override": "Lutry-Lavaux",
        "team_b_name_override": "Voléro Zürich",
        "player_names": {
            "10": {"team": "a", "jersey_number": 17, "id": "a_17"},
            "20": {"team": "b", "jersey_number": 5, "id": "b_5"},
        },
        "video_analysis": [
            {
                "id": 1,
                "set_number": 1,
                "serving_team": "b",
                "team_won": "a",
                "actions": [
                    {
                        "skill_type": "attack",
                        "team": "a",
                        "player_id": 10,
                        "quality": "kill",
                        "first_ball_side_out": True,
                        "positional": {"dest_zone": 4},
                    },
                    {
                        "skill_type": "set",
                        "team": "a",
                        "player_id": 10,
                        "quality": "assist",
                        "positional": {"dest_zone": 4},
                    },
                ],
            },
            {
                "id": 2,
                "set_number": 1,
                "serving_team": "a",
                "team_won": "a",
                "actions": [
                    {
                        "skill_type": "serve",
                        "team": "a",
                        "player_id": 10,
                        "quality": "ace",
                    }
                ],
            },
        ],
    }

    players = parse_balltime_player_stats(sample_meta, team="a")
    assert len(players) == 1
    p = players[0]
    assert p.jersey_number == "17"
    assert p.kills == 1
    assert p.aces == 1
    assert p.assists == 1
    assert p.points == 2.0
    assert p.hitting_percentage == 1.0

    rotations = parse_balltime_rotation_stats(sample_meta, team="a")
    assert len(rotations) == 6
    p1 = rotations[0]
    assert p1.rotation_name == "P1"
    assert p1.sideouts_earned == 1
    assert p1.sideout_attempts == 1
    assert p1.sideout_percentage == 100.0
    assert p1.first_ball_sideout_rate == 100.0


def test_find_matching_video_for_opponent():
    """Verify opponent matching finds videos by direct or token substring match."""
    from hudl_mcp.models import find_matching_video_for_opponent, MatchSummary

    videos = [
        MatchSummary(
            match_id="vid-1",
            opponent_name="LUTRY  VS Voléro Zürich",
            match_type="video",
        ),
        MatchSummary(
            match_id="vid-2",
            opponent_name="Voléro Zürich vs Chênois Genève",
            match_type="video",
        ),
    ]

    # Matches "Lutry-Lavaux Volleyball" -> "vid-1"
    assert find_matching_video_for_opponent("Lutry-Lavaux Volleyball", videos) == "vid-1"

    # Matches "Chênois Genève Volleyball" -> "vid-2"
    assert find_matching_video_for_opponent("Chênois Genève Volleyball", videos) == "vid-2"

    # Does not match unknown team
    assert find_matching_video_for_opponent("Lausanne UC", videos) is None


def test_format_matches_markdown_with_both_videos_and_schedule():
    """Verify format_matches_markdown renders two distinct tables with linked video column."""
    from hudl_mcp.models import MatchSummary, format_matches_markdown

    matches = [
        MatchSummary(
            match_id="vid-lutry",
            date="2026-10-13",
            opponent_name="LUTRY  VS Voléro Zürich",
            result="stats_available",
            home_away="scouting",
            score="4 sets",
            match_type="video",
        ),
        MatchSummary(
            match_id="34352342",
            video_id="vid-lutry",
            date="10-18-2026 16:00:00",
            opponent_name="Lutry-Lavaux Volleyball",
            result="Scheduled",
            home_away="Home",
            match_type="schedule",
        ),
    ]

    md = format_matches_markdown(matches, team_id="948881")
    assert "Recent Volleyball Matches (Team ID: 948881)" in md
    assert "#### 📹 Uploaded Match Videos" in md
    assert "`vid-lutry`" in md
    assert "LUTRY  VS Voléro Zürich" in md
    assert "#### 📅 Team Match Schedule" in md
    assert "`34352342`" in md
    assert "Lutry-Lavaux Volleyball" in md
    assert "`vid-lutry` 📹" in md


def test_format_player_stats_markdown_with_passing_and_unassigned():
    """Verify format_player_stats_markdown includes passing distribution and unassigned audit callout."""
    from hudl_mcp.models import PlayerStats, format_player_stats_markdown

    players = [
        PlayerStats(
            player_name="#20 Lino Steinmann",
            jersey_number="20",
            position="OH",
            sets_played=3,
            kills=10,
            attack_errors=0,
            total_attacks=13,
            aces=3,
            serve_errors=1,
            receptions=18,
            perfect_passes=5,
            positive_passes=10,
            medium_passes=3,
            reception_errors=0,
            pass_rating=2.11,
            digs=7,
        ),
        PlayerStats(
            player_name="Team A (Unassigned)",
            jersey_number="",
            position="",
            sets_played=3,
            kills=2,
            attack_errors=1,
            total_attacks=5,
        ),
    ]

    md = format_player_stats_markdown(players, match_id="vid-aeschi", team_name="Lutry-Lavaux")
    assert "Athlete Box Score - Lutry-Lavaux (Match ID: `vid-aeschi`)" in md
    assert "Rec" in md
    assert "Pass Avg" in md
    assert "2.11" in md
    assert "🎯 Serve Reception Quality Distribution" in md
    assert "| 20 | **#20 Lino Steinmann** | 18 | 5 | 10 | 3 | 0 | **2.11** |" in md
    assert "AI Tracking & Unassigned Touches Audit" in md
    assert 'get_game_actions(match_id="vid-aeschi", player="unassigned")' in md


def test_parse_and_format_teams_response():
    """Verify parse_teams_response extracts team details and format_teams_markdown highlights active team."""
    from hudl_mcp.models import parse_teams_response, format_teams_markdown

    raw_teams = [
        {
            "teamId": "948881",
            "name": "Basel NLB",
            "role": "Coach",
            "school": {"name": "SV Volley Wyna 1"},
            "seasons": [
                {"name": "2026-2027 Season", "isCurrentSeason": True},
            ],
        },
        {
            "teamId": "123456",
            "name": "Zurich VC",
            "role": "Assistant",
            "school": {"name": "ZVC Club"},
        },
    ]

    teams = parse_teams_response(raw_teams, active_team_id="948881")
    assert len(teams) == 2
    assert teams[0].team_id == "948881"
    assert teams[0].name == "Basel NLB"
    assert teams[0].school_name == "SV Volley Wyna 1"
    assert teams[0].current_season == "2026-2027 Season"
    assert teams[0].is_current is True
    assert teams[1].is_current is False

    md = format_teams_markdown(teams, active_team_id="948881")
    assert "Your Hudl Volleyball Teams" in md
    assert "`948881`" in md
    assert "Basel NLB" in md
    assert "✅ **Active**" in md
    assert "`123456`" in md
    assert "Zurich VC" in md


