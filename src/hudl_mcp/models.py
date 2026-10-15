"""Pydantic models and data parsing for Hudl Volleyball MCP.

This module strips unnecessary UI metadata from raw GraphQL responses, cleanses
and normalizes stats, calculates missing derived volleyball metrics (e.g. Hitting
Percentage = (Kills - Errors) / Attacks), and outputs compact analytical representations
(Markdown tables and JSON).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class MatchSummary(BaseModel):
    """Cleaned representation of a volleyball match summary."""

    match_id: str = Field(..., description="Unique match identifier")
    video_id: Optional[str] = Field(None, description="Linked Balltime video ID (for schedule matches with uploaded video)")
    date: Optional[str] = Field(None, description="Date or timestamp of the match")
    opponent_name: str = Field("Unknown Opponent", description="Opponent team name")
    result: Optional[str] = Field(None, description="Match result, e.g. 'W 3-1', 'L 0-3'")
    home_away: Optional[str] = Field(None, description="'Home', 'Away', or 'Neutral'")
    score: Optional[str] = Field(None, description="Overall match set score, e.g. '3-1'")
    set_scores: Optional[List[str]] = Field(default_factory=list, description="Scores per set")
    status: Optional[str] = Field(None, description="Match status, e.g. 'Final'")
    season: Optional[str] = Field(None, description="Season name or year")
    match_type: str = Field("schedule", description="'video' for uploaded match videos, 'schedule' for calendar fixtures")

    model_config = {"populate_by_name": True}

    def to_compact_dict(self) -> Dict[str, Any]:
        """Convert to compact high-signal dictionary stripping UI bloat."""
        res: Dict[str, Any] = {
            "id": self.match_id,
            "opponent": self.opponent_name,
            "date": self.date,
            "result": self.result or self.score,
            "type": self.match_type,
        }
        if self.video_id:
            res["video_id"] = self.video_id
        if self.set_scores:
            res["set_scores"] = self.set_scores
        return res


class TeamInfo(BaseModel):
    """Cleaned representation of a Hudl Team."""

    team_id: str = Field(..., description="Hudl Team ID")
    name: str = Field(..., description="Team Name")
    school_name: Optional[str] = Field(None, description="Club or School organization name")
    role: Optional[str] = Field(None, description="User role on the team (e.g. Coach, Athlete)")
    current_season: Optional[str] = Field(None, description="Active season name")
    gender: Optional[str] = Field(None, description="Team gender / category")
    is_current: bool = Field(False, description="Whether this is the currently active/selected team")

    model_config = {"populate_by_name": True}

    def to_compact_dict(self) -> Dict[str, Any]:
        """Convert to compact high-signal dictionary stripping UI bloat."""
        return {
            "team_id": self.team_id,
            "name": self.name,
            "school": self.school_name,
            "role": self.role,
            "season": self.current_season,
        }


class PlayerStats(BaseModel):
    """Cleaned individual athlete volleyball statistics with derived metrics."""

    player_id: Optional[str] = Field(None, description="Athlete ID")
    jersey_number: str = Field("", description="Jersey number")
    player_name: str = Field(..., description="Athlete full name")
    position: str = Field("", description="Position (OH, MB, RS, S, L, DS)")
    sets_played: int = Field(0, description="Sets played in the match")

    # Attacking
    kills: int = Field(0, description="Total kills (winning attacks)")
    attack_errors: int = Field(0, description="Attack errors")
    total_attacks: int = Field(0, description="Total attack attempts")
    hitting_percentage: Optional[float] = Field(
        None, description="Hitting %: (Kills - Errors) / Total Attacks"
    )

    # Setting
    assists: int = Field(0, description="Setting assists")
    ball_handling_errors: int = Field(0, description="Ball handling errors (BHE)")

    # Serving
    aces: int = Field(0, description="Service aces")
    serve_errors: int = Field(0, description="Service errors")
    total_serves: int = Field(0, description="Total serves")

    # Defense & Passing
    digs: int = Field(0, description="Digs")
    receptions: int = Field(0, description="Total serve receptions")
    perfect_passes: int = Field(0, description="Quality 3 (perfect) passes")
    positive_passes: int = Field(0, description="Quality 2 (positive) passes")
    medium_passes: int = Field(0, description="Quality 1 (medium) passes")
    reception_errors: int = Field(0, description="Serve reception errors (0s)")
    pass_rating: Optional[float] = Field(
        None, description="Serve receive passing rating (e.g. 0-3 scale)"
    )

    # Blocking
    block_solos: int = Field(0, description="Solo blocks (BS)")
    block_assists: int = Field(0, description="Block assists (BA)")
    total_blocks: Optional[float] = Field(
        None, description="Total blocks (BS + 0.5 * BA)"
    )
    block_errors: int = Field(0, description="Blocking errors (BE)")

    # Overall Scoring
    points: Optional[float] = Field(
        None, description="Total points scored (Kills + Aces + BS + 0.5 * BA)"
    )

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def calculate_derived_metrics(self) -> PlayerStats:
        """Calculate missing derived volleyball statistics."""
        # 1. Hitting Percentage: (Kills - Errors) / Total Attacks
        if self.hitting_percentage is None:
            if self.total_attacks > 0:
                self.hitting_percentage = round(
                    (self.kills - self.attack_errors) / self.total_attacks, 3
                )
            else:
                self.hitting_percentage = 0.000

        # 2. Total Blocks: Solos + 0.5 * Assists
        if self.total_blocks is None:
            self.total_blocks = round(self.block_solos + (0.5 * self.block_assists), 1)

        # 3. Total Points: Kills + Aces + Solo Blocks + (0.5 * Block Assists)
        if self.points is None:
            self.points = round(
                self.kills + self.aces + self.block_solos + (0.5 * self.block_assists), 1
            )

        # 4. Pass Rating: (3 * Perfect + 2 * Positive + 1 * Medium) / Total Receptions
        if self.pass_rating is None and self.receptions > 0:
            total_points = (3 * self.perfect_passes) + (2 * self.positive_passes) + (1 * self.medium_passes)
            self.pass_rating = round(total_points / self.receptions, 2)

        return self

    def to_compact_dict(self) -> Dict[str, Any]:
        """Convert to compact high-signal box score dictionary stripping UI bloat."""
        return {
            "num": self.jersey_number,
            "name": self.player_name,
            "pos": self.position or None,
            "sets": self.sets_played,
            "k": self.kills,
            "e": self.attack_errors,
            "ta": self.total_attacks,
            "hit_pct": self.hitting_percentage,
            "ast": self.assists,
            "ace": self.aces,
            "se": self.serve_errors,
            "dig": self.digs,
            "blk": self.total_blocks,
            "pts": self.points,
            "rec": self.receptions,
            "pass_avg": self.pass_rating,
        }


class RotationStats(BaseModel):
    """Cleaned rotation performance metrics for P1 through P6."""

    rotation_number: int = Field(..., ge=1, le=6, description="Rotation number (1-6)")
    rotation_name: str = Field("P1", description="Rotation label, e.g. 'P1', 'P2', etc.")
    sideout_percentage: Optional[float] = Field(
        None, description="Sideout % when receiving serve in this rotation"
    )
    sideouts_earned: Optional[int] = Field(None, description="Successful sideouts")
    sideout_attempts: Optional[int] = Field(None, description="Receiving opportunities")
    point_scoring_percentage: Optional[float] = Field(
        None, description="Point scoring % when serving in this rotation"
    )
    points_scored_serving: Optional[int] = Field(None, description="Points scored on serve")
    serve_attempts: Optional[int] = Field(None, description="Serving opportunities")
    first_ball_sideout_rate: Optional[float] = Field(
        None, description="First-Ball Sideout (FBSO) % on in-system / first pass"
    )
    setter_tendencies: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Setter set distribution (Left, Middle, Right, Pipe)"
    )
    notes: Optional[str] = Field(None, description="Tactical notes or observations")

    model_config = {"populate_by_name": True}

    def to_compact_dict(self) -> Dict[str, Any]:
        """Convert to compact high-signal rotation dictionary stripping UI bloat."""
        return {
            "rotation": f"P{self.rotation_number}" if self.rotation_number else self.rotation_name,
            "sideout_pct": f"{round(self.sideout_percentage * 100, 1)}%" if self.sideout_percentage is not None else None,
            "sideouts": f"{self.sideouts_earned or 0}/{self.sideout_attempts or 0}",
            "point_scoring_pct": f"{round(self.point_scoring_percentage * 100, 1)}%" if self.point_scoring_percentage is not None else None,
            "points_served": f"{self.points_scored_serving or 0}/{self.serve_attempts or 0}",
            "fbso_pct": f"{round(self.first_ball_sideout_rate * 100, 1)}%" if self.first_ball_sideout_rate is not None else None,
            "setter_distribution": self.setter_tendencies or {},
        }


class VolleyballAction(BaseModel):
    """Detailed volleyball action / touch event from video breakdown."""

    action_id: Optional[int] = Field(None, description="Action or touch event ID")
    rally_id: Optional[int] = Field(None, description="Rally ID")
    set_number: int = Field(1, description="Set number (1-5)")
    score: Optional[str] = Field(None, description="Score at time of action, e.g. '12-7'")
    timestamp_seconds: Optional[float] = Field(None, description="Timestamp in seconds from video start")
    timestamp_formatted: Optional[str] = Field(None, description="Formatted video timestamp (MM:SS or H:MM:SS)")
    team: str = Field(..., description="Team code ('a', 'b') or team name")
    team_name: Optional[str] = Field(None, description="Full team name")
    player_id: Optional[str] = Field(None, description="Player cluster ID or internal ID")
    jersey_number: Optional[str] = Field(None, description="Jersey number, e.g. '17'")
    player_label: str = Field(..., description="Display label, e.g. '#17 (Lutry-Lavaux)'")
    action_type: str = Field(..., description="Action skill (serve, receive, set, attack, dig, block, free_ball)")
    touch_type: Optional[str] = Field(None, description="Touch type (e.g. hand, bump)")
    quality: Optional[str] = Field(None, description="Result/quality (kill, error, ace, assist, in_play, rating 1-3)")
    attack_type: Optional[str] = Field(None, description="Attack set route / type (e.g. quick, pipe, high)")
    first_ball_side_out: bool = Field(False, description="Whether this action was during a first-ball sideout")
    source_zone: Optional[int] = Field(None, description="Origin court zone (1-6)")
    dest_zone: Optional[int] = Field(None, description="Destination court zone (1-6)")
    speed_kmh: Optional[float] = Field(None, description="Attack or serve ball speed in km/h")
    touch_height_m: Optional[float] = Field(None, description="Vertical touch / contact height in meters")
    is_verified: bool = Field(False, description="Whether this action was coach-verified / overridden in Balltime")
    details: Optional[str] = Field(None, description="Extra tactical details (e.g. blockers, routes, deflection)")

    model_config = {"populate_by_name": True}

    @property
    def dvw_skill(self) -> str:
        """Map action type to standard DataVolley skill code (S, R, E, A, B, D, F)."""
        act = (self.action_type or "").lower().strip()
        if "serve" in act:
            return "S"
        elif "receive" in act or "pass" in act:
            return "R"
        elif "set" in act:
            return "E"
        elif "attack" in act or "spike" in act:
            return "A"
        elif "block" in act:
            return "B"
        elif "dig" in act:
            return "D"
        elif "free" in act:
            return "F"
        return "A"

    @property
    def dvw_evaluation(self) -> str:
        """Map touch quality to standard DataVolley evaluation symbol (#, +, !, -, =)."""
        qual = (self.quality or "").lower().strip()
        if qual in ("kill", "ace", "perfect", "3", "assist", "point", "win"):
            return "#"
        elif qual in ("positive", "2", "in_play", "in-play", "good"):
            return "+"
        elif qual in ("medium", "1", "special"):
            return "!"
        elif qual in ("poor", "negative"):
            return "-"
        elif qual in ("error", "0", "out", "net", "fault"):
            return "="
        return "+"

    def to_datavolley_code(self) -> str:
        """Generate a standard DataVolley (.dvw) scouting code string."""
        team_char = "*" if self.team.lower() == "a" else "a"
        num_str = f"{int(self.jersey_number):02d}" if (self.jersey_number and self.jersey_number.isdigit()) else "00"
        return f"{team_char}{num_str}{self.dvw_skill}{self.dvw_evaluation}"

    def to_compact_dict(self) -> Dict[str, Any]:
        """Convert to compact high-signal touch event dictionary stripping raw coordinates/UUIDs."""
        res: Dict[str, Any] = {
            "set": self.set_number,
            "score": self.score or "-",
            "time": self.timestamp_formatted or (f"{int(self.timestamp_seconds)}s" if self.timestamp_seconds is not None else "-"),
            "player": self.player_label,
            "action": self.action_type,
            "quality": self.quality,
            "dvw": self.to_datavolley_code(),
        }
        if self.attack_type:
            res["route"] = self.attack_type
        if self.source_zone or self.dest_zone:
            res["zones"] = f"Z{self.source_zone or '?'}->Z{self.dest_zone or '?'}"
        if self.speed_kmh:
            res["speed_kmh"] = round(self.speed_kmh, 1)
        if self.first_ball_side_out:
            res["fbso"] = True
        if self.details:
            res["details"] = self.details
        return res


# ==============================================================================
# RAW GRAPHQL PARSING HELPERS
# ==============================================================================

def _safe_int(val: Any, default: int = 0) -> int:
    """Safely convert value to integer."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely convert value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def parse_matches_response(raw_data: Dict[str, Any]) -> List[MatchSummary]:
    """Parse raw GraphQL or Hudl schedule data into a list of MatchSummary models.

    Supports Relay style (edges -> node), direct list (items), flat lists,
    or Hudl Schedule API structure.
    """
    matches_list: List[MatchSummary] = []

    # 1. Check if raw_data is Hudl Schedule API structure: {season_id: [ {teamName, games: [...]}, ... ]}
    if isinstance(raw_data, dict):
        has_schedule_structure = any(
            isinstance(v, list) and v and isinstance(v[0], dict) and "games" in v[0]
            for v in raw_data.values()
        )
        if has_schedule_structure:
            for season_id, opponents in raw_data.items():
                if not isinstance(opponents, list):
                    continue
                for opp in opponents:
                    if not isinstance(opp, dict):
                        continue
                    opp_name = opp.get("teamName") or opp.get("schoolName") or "Unknown Opponent"
                    for g in opp.get("games", []):
                        if not isinstance(g, dict):
                            continue
                        g_id = str(g.get("gameId") or "")
                        if not g_id:
                            continue
                        is_home = g.get("isHome")
                        home_away = "Home" if is_home is True else ("Away" if is_home is False else None)
                        is_win = g.get("isWin")
                        s1 = g.get("score1")
                        s2 = g.get("score2")
                        score_str = f"{s1}-{s2}" if s1 is not None and s2 is not None else None
                        res_str = None
                        if is_win is True:
                            res_str = f"W {score_str}" if score_str else "W"
                        elif is_win is False:
                            res_str = f"L {score_str}" if score_str else "L"
                        elif g.get("hasScore") is False:
                            res_str = "Scheduled"

                        matches_list.append(
                            MatchSummary(
                                match_id=g_id,
                                date=g.get("localDateTime"),
                                opponent_name=opp_name,
                                result=res_str,
                                home_away=home_away,
                                score=score_str,
                                season=str(season_id),
                                status="Scheduled" if g.get("hasScore") is False else "Final",
                                match_type="schedule",
                            )
                        )
            return matches_list

    # 2. Check for Balltime library videos: {"videos": [...]} or {"data": {"videos": [...]}}
    lib_data = raw_data.get("data", raw_data) if isinstance(raw_data, dict) else raw_data
    if isinstance(lib_data, dict):
        videos_list = lib_data.get("videos")
        if isinstance(videos_list, list):
            for v in videos_list:
                if not isinstance(v, dict):
                    continue
                v_id = str(v.get("id") or "")
                if not v_id:
                    continue
                title = v.get("title") or v.get("name") or "Volleyball Match"
                date = v.get("video_file_date") or v.get("date") or v.get("created_at")
                v_type = v.get("video_type") or "scouting"
                stat_status = v.get("stats_status")
                proc_status = v.get("processing_status")
                score_dict = v.get("score")
                score_str = None
                if isinstance(score_dict, dict):
                    sets = score_dict.get("sets")
                    if isinstance(sets, list) and sets:
                        score_str = f"{len(sets)} sets"
                matches_list.append(
                    MatchSummary(
                        match_id=v_id,
                        video_id=v_id,
                        date=date,
                        opponent_name=title,
                        result=stat_status or proc_status,
                        home_away=v_type,
                        score=score_str,
                        status=proc_status or "processed",
                        match_type="video",
                    )
                )
            if matches_list:
                return matches_list

        # Check for Hudl GraphQL LibraryContentSearchConnection: {"library": {"edges": [...]}}
        if "library" in lib_data and isinstance(lib_data["library"], dict):
            edges = lib_data["library"].get("edges", [])
            if isinstance(edges, list):
                for e in edges:
                    node = e.get("node", {}) if isinstance(e, dict) else {}
                    n_id = str(node.get("id") or "")
                    if not n_id:
                        continue
                    matches_list.append(
                        MatchSummary(
                            match_id=n_id,
                            video_id=n_id,
                            date=node.get("date"),
                            opponent_name=node.get("title") or "Volleyball Video Match",
                            status="Processed",
                            match_type="video",
                        )
                    )
                if matches_list:
                    return matches_list

    # 3. Find the matches container in nested GraphQL dictionary
    matches_node = None
    if "data" in raw_data and isinstance(raw_data["data"], dict):
        raw_data = raw_data["data"]

    team_data = raw_data.get("team") or raw_data.get("teamMatches") or raw_data
    if isinstance(team_data, dict):
        matches_node = team_data.get("matches") or team_data.get("schedule")

    if matches_node is None:
        matches_node = raw_data.get("matches")

    raw_items: List[Dict[str, Any]] = []
    if isinstance(matches_node, dict):
        if "edges" in matches_node and isinstance(matches_node["edges"], list):
            raw_items = [
                edge.get("node", {})
                for edge in matches_node["edges"]
                if isinstance(edge, dict)
            ]
        elif "items" in matches_node and isinstance(matches_node["items"], list):
            raw_items = matches_node["items"]
    elif isinstance(matches_node, list):
        raw_items = matches_node
    elif isinstance(team_data, list):
        raw_items = team_data

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        match_id = str(item.get("id") or item.get("matchId") or item.get("uuid") or "")
        if not match_id:
            continue

        # Opponent extraction
        opp = item.get("opponent")
        opponent_name = "Unknown Opponent"
        if isinstance(opp, dict):
            opponent_name = opp.get("name") or opp.get("shortName") or "Unknown Opponent"
        elif isinstance(opp, str):
            opponent_name = opp
        elif "opponentName" in item:
            opponent_name = str(item["opponentName"])

        # Result / Score extraction
        result_node = item.get("result")
        outcome = None
        score = None
        set_scores: List[str] = []

        if isinstance(result_node, dict):
            outcome = result_node.get("outcome")
            score = result_node.get("score")
            raw_set_scores = result_node.get("setScores")
            if isinstance(raw_set_scores, list):
                set_scores = [str(s) for s in raw_set_scores]
        elif isinstance(result_node, str):
            outcome = result_node

        if not score and "score" in item:
            score = str(item["score"])

        result_str = None
        if outcome and score:
            result_str = f"{outcome} {score}"
        elif outcome:
            result_str = str(outcome)
        elif score:
            result_str = str(score)

        season_name = None
        season_node = item.get("season")
        if isinstance(season_node, dict):
            season_name = season_node.get("name")
        elif isinstance(season_node, str):
            season_name = season_node

        matches_list.append(
            MatchSummary(
                match_id=match_id,
                date=item.get("date") or item.get("scheduledTime"),
                opponent_name=opponent_name,
                result=result_str,
                home_away=item.get("homeAway") or item.get("homeOrAway"),
                score=score,
                set_scores=set_scores,
                status=item.get("status"),
                season=season_name,
                match_type="schedule",
            )
        )

    return matches_list


def parse_player_stats_response(raw_data: Dict[str, Any]) -> List[PlayerStats]:
    """Parse raw GraphQL data into a list of PlayerStats models."""
    if "data" in raw_data and isinstance(raw_data["data"], dict):
        raw_data = raw_data["data"]

    match_node = raw_data.get("match") or raw_data.get("matchStats") or raw_data
    if not isinstance(match_node, dict):
        return []

    # Check various container formats: volleyballStats -> athleteStats, boxScore -> players, etc.
    vb_stats = match_node.get("volleyballStats") or match_node.get("boxScore") or match_node
    athlete_stats_list = []

    if isinstance(vb_stats, dict):
        athlete_stats_list = (
            vb_stats.get("athleteStats")
            or vb_stats.get("playerStats")
            or vb_stats.get("athletes")
            or vb_stats.get("players")
            or []
        )
    elif isinstance(vb_stats, list):
        athlete_stats_list = vb_stats

    if not isinstance(athlete_stats_list, list):
        return []

    player_stats_list: List[PlayerStats] = []

    for item in athlete_stats_list:
        if not isinstance(item, dict):
            continue

        # Extract athlete info
        athlete_info = item.get("athlete") or item.get("player") or item
        player_name = (
            athlete_info.get("name")
            or athlete_info.get("fullName")
            or f"{athlete_info.get('firstName', '')} {athlete_info.get('lastName', '')}".strip()
            or "Unknown Player"
        )
        player_id = str(athlete_info.get("id") or athlete_info.get("athleteId") or "")
        jersey = str(athlete_info.get("jerseyNumber") or athlete_info.get("number") or "")
        position = str(athlete_info.get("position") or "")

        # Extract stats dictionary
        s = item.get("stats") or item

        kills = _safe_int(s.get("kills"))
        errors = _safe_int(s.get("attackErrors") or s.get("errors"))
        attacks = _safe_int(s.get("totalAttacks") or s.get("attempts") or s.get("attacks"))
        hit_pct = _safe_float(s.get("hittingPercentage") or s.get("hitPct"))

        player = PlayerStats(
            player_id=player_id or None,
            jersey_number=jersey,
            player_name=player_name,
            position=position,
            sets_played=_safe_int(s.get("setsPlayed") or s.get("sp")),
            kills=kills,
            attack_errors=errors,
            total_attacks=attacks,
            hitting_percentage=hit_pct,
            assists=_safe_int(s.get("assists") or s.get("ast")),
            ball_handling_errors=_safe_int(s.get("ballHandlingErrors") or s.get("bhe")),
            aces=_safe_int(s.get("serviceAces") or s.get("aces") or s.get("sa")),
            serve_errors=_safe_int(s.get("serviceErrors") or s.get("serveErrors") or s.get("se")),
            total_serves=_safe_int(s.get("totalServes") or s.get("serves")),
            digs=_safe_int(s.get("digs") or s.get("dig")),
            pass_rating=_safe_float(s.get("passRating") or s.get("rating")),
            reception_errors=_safe_int(s.get("receptionErrors") or s.get("re")),
            block_solos=_safe_int(s.get("blockSolos") or s.get("bs")),
            block_assists=_safe_int(s.get("blockAssists") or s.get("ba")),
            total_blocks=_safe_float(s.get("totalBlocks") or s.get("tb")),
            block_errors=_safe_int(s.get("blockingErrors") or s.get("blockErrors") or s.get("be")),
            points=_safe_float(s.get("points") or s.get("pts")),
        )
        player_stats_list.append(player)

    return player_stats_list


def parse_rotation_stats_response(raw_data: Dict[str, Any]) -> List[RotationStats]:
    """Parse raw GraphQL data into a list of RotationStats models (P1 to P6)."""
    if "data" in raw_data and isinstance(raw_data["data"], dict):
        raw_data = raw_data["data"]

    match_node = raw_data.get("match") or raw_data
    if not isinstance(match_node, dict):
        return []

    breakdown = match_node.get("rotationBreakdown") or match_node.get("rotations") or match_node
    rot_list = []
    if isinstance(breakdown, dict):
        rot_list = breakdown.get("rotations") or breakdown.get("items") or []
    elif isinstance(breakdown, list):
        rot_list = breakdown

    if not isinstance(rot_list, list):
        return []

    rotation_stats_list: List[RotationStats] = []

    for idx, item in enumerate(rot_list, start=1):
        if not isinstance(item, dict):
            continue

        rot_num = _safe_int(item.get("rotationNumber") or item.get("rotation") or idx)
        # Ensure between 1 and 6
        if rot_num < 1 or rot_num > 6:
            rot_num = ((rot_num - 1) % 6) + 1

        rot_name = item.get("rotationName") or f"P{rot_num}"

        so_pct = _safe_float(item.get("sideoutPercentage") or item.get("sideoutRate") or item.get("soPct"))
        pt_pct = _safe_float(item.get("pointScoringPercentage") or item.get("pointScoringRate") or item.get("ptPct"))
        fbso_pct = _safe_float(item.get("firstBallSideoutRate") or item.get("fbso") or item.get("fbsoRate"))

        tendencies = item.get("setterTendencies")
        if not isinstance(tendencies, dict):
            tendencies = {}

        rot_stat = RotationStats(
            rotation_number=rot_num,
            rotation_name=rot_name,
            sideout_percentage=so_pct,
            sideouts_earned=_safe_int(item.get("sideoutsEarned")),
            sideout_attempts=_safe_int(item.get("sideoutAttempts") or item.get("receivingAttempts")),
            point_scoring_percentage=pt_pct,
            points_scored_serving=_safe_int(item.get("pointsScoredServing")),
            serve_attempts=_safe_int(item.get("serveAttempts") or item.get("servingAttempts")),
            first_ball_sideout_rate=fbso_pct,
            setter_tendencies=tendencies,
            notes=item.get("notes"),
        )
        rotation_stats_list.append(rot_stat)

    # Sort rotations by rotation number 1 to 6
    rotation_stats_list.sort(key=lambda r: r.rotation_number)
    return rotation_stats_list


# ==============================================================================
# FORMATTING OUTPUT HELPERS (MARKDOWN & COMPACT JSON)
# ==============================================================================

def format_pct(val: Any, decimals: int = 1) -> str:
    """Format a percentage value nicely (e.g. 0.625 -> 62.5%, 62.5 -> 62.5%, or '45%' -> '45%')."""
    if val is None:
        return "-"
    if isinstance(val, str):
        val_str = val.strip()
        if val_str.endswith("%"):
            return val_str
        try:
            val = float(val_str)
        except ValueError:
            return val_str
    if isinstance(val, int):
        return f"{val}%"
    if isinstance(val, float):
        # If provided as fraction 0.0 - 1.0, convert to 0 - 100%
        if -1.0 <= val <= 1.0 and val != 0.0:
            val = val * 100.0
        return f"{val:.{decimals}f}%"
    return str(val)



def format_hit_pct(val: Optional[float]) -> str:
    """Format hitting percentage in standard volleyball baseball-style format (.350, -.050)."""
    if val is None:
        return ".000"
    if val < 0:
        return f"-{abs(val):.3f}".replace("-0.", "-.")
    return f"{val:.3f}".replace("0.", ".")


def find_matching_video_for_opponent(
    opponent_name: str,
    videos: List[MatchSummary],
    match_date: Optional[str] = None,
) -> Optional[str]:
    """Find a matching Balltime video ID for a scheduled match opponent."""
    if not opponent_name or not videos:
        return None

    import re
    cleaned_opp = re.sub(r"[^a-zA-Z0-9\s]", " ", opponent_name.lower())
    stop_words = {
        "volleyball", "vb", "vbc", "club", "team", "vs", "the", "and",
        "de", "le", "la", "men", "women", "mens", "womens", "hs", "academy",
    }
    opp_tokens = [t for t in cleaned_opp.split() if t not in stop_words and len(t) >= 3]

    for v in videos:
        v_title_lower = v.opponent_name.lower()
        # Direct substring match
        if opponent_name.lower() in v_title_lower or v_title_lower in opponent_name.lower():
            return v.match_id
        # Token match
        for token in opp_tokens:
            if token in v_title_lower:
                return v.match_id

    return None


def parse_teams_response(raw_data: Any, active_team_id: Optional[str] = None) -> List[TeamInfo]:
    """Parse raw Hudl /api/v2/teams response into a list of TeamInfo models."""
    if isinstance(raw_data, dict):
        team_list = raw_data.get("teams") or raw_data.get("items") or [raw_data]
    elif isinstance(raw_data, list):
        team_list = raw_data
    else:
        return []

    teams: List[TeamInfo] = []
    for item in team_list:
        if not isinstance(item, dict):
            continue
        tid = str(item.get("teamId") or item.get("sqlId") or item.get("id") or "")
        if not tid:
            continue
        name = str(item.get("name") or "Unnamed Team").strip()
        school_obj = item.get("school") or {}
        school_name = school_obj.get("name") if isinstance(school_obj, dict) else str(school_obj)

        current_season = None
        seasons = item.get("seasons", [])
        if isinstance(seasons, list):
            curr_s = next((s for s in seasons if isinstance(s, dict) and s.get("isCurrentSeason")), None)
            if curr_s:
                current_season = curr_s.get("name")
            elif seasons and isinstance(seasons[0], dict):
                current_season = seasons[0].get("name")

        teams.append(
            TeamInfo(
                team_id=tid,
                name=name,
                school_name=school_name or None,
                role=item.get("role"),
                current_season=current_season,
                gender=item.get("gender"),
                is_current=(active_team_id is not None and str(tid) == str(active_team_id)),
            )
        )
    return teams


def format_teams_markdown(teams: List[TeamInfo], active_team_id: Optional[str] = None) -> str:
    """Format list of user teams into a clean Markdown table."""
    if not teams:
        return "No Hudl teams found for the authenticated user."

    lines = [
        "### 🏐 Your Hudl Volleyball Teams",
        "",
        "| Team ID | Team Name | Club / Organization | Role | Current Season | Status |",
        "|---|---|---|---|---|:---:|",
    ]
    for t in teams:
        is_active = "✅ **Active**" if (active_team_id and str(t.team_id) == str(active_team_id)) else "-"
        lines.append(
            f"| `{t.team_id}` | **{t.name}** | {t.school_name or '-'} | {t.role or '-'} | {t.current_season or '-'} | {is_active} |"
        )

    lines.extend([
        "",
        "> 💡 **Tip**: Use any **Team ID** above in `list_volleyball_matches(team_id=\"...\")` to view schedule fixtures, or set `HUDL_TEAM_ID` in `.env`.",
    ])
    return "\n".join(lines)


def format_matches_markdown(matches: List[MatchSummary], team_id: Optional[str] = None) -> str:
    """Format list of matches into clean Markdown tables separating videos and schedule fixtures."""
    if not matches:
        return "No matches found."

    header = f"### Recent Volleyball Matches"
    if team_id:
        header += f" (Team ID: {team_id})"

    videos = [m for m in matches if getattr(m, "match_type", None) == "video"]
    schedule = [m for m in matches if getattr(m, "match_type", None) == "schedule"]

    # If no videos are present or single legacy source, keep simple unified table
    if not videos:
        lines = [
            header,
            "",
            "| Match ID | Date | Opponent | Result | Location | Set Scores |",
            "|---|---|---|---|---|---|",
        ]
        for m in matches:
            date_str = m.date or "N/A"
            res_str = m.result or "N/A"
            loc_str = m.home_away or "-"
            set_scores_str = ", ".join(m.set_scores) if m.set_scores else (m.score or "-")
            lines.append(
                f"| `{m.match_id}` | {date_str} | **{m.opponent_name}** | {res_str} | {loc_str} | {set_scores_str} |"
            )
        return "\n".join(lines)

    lines = [header, ""]

    if videos:
        lines.extend([
            "#### 📹 Uploaded Match Videos (Detailed Box Scores, Rotations & Action Feed Available)",
            "",
            "| Video ID | Date | Video Title / Opponent | Status | Type | Sets |",
            "|---|---|---|---|---|---|",
        ])
        for v in videos:
            v_date = v.date or "N/A"
            v_status = v.result or v.status or "Processed"
            v_type = (v.home_away or "scouting").capitalize()
            v_score = v.score or "-"
            lines.append(
                f"| `{v.match_id}` | {v_date} | **{v.opponent_name}** | {v_status} | {v_type} | {v_score} |"
            )
        lines.extend([
            "",
            "> 💡 **Tip**: Use the **Video ID** above with `get_match_player_stats`, `get_rotation_breakdown`, or `get_game_actions` for full box scores, rotation efficiencies, and touch-by-touch feeds.",
            "",
        ])

    if schedule:
        has_video_links = any(bool(s.video_id) for s in schedule)
        lines.append("#### 📅 Team Match Schedule (Calendar Fixtures)")
        lines.append("")
        if has_video_links:
            lines.append("| Match ID | Date | Opponent | Result | Location | Set Scores | Linked Video ID |")
            lines.append("|---|---|---|---|---|---|---|")
        else:
            lines.append("| Match ID | Date | Opponent | Result | Location | Set Scores |")
            lines.append("|---|---|---|---|---|---|")

        for s in schedule:
            s_date = s.date or "N/A"
            s_res = s.result or "Scheduled"
            s_loc = s.home_away or "-"
            s_scores = ", ".join(s.set_scores) if s.set_scores else (s.score or "-")
            if has_video_links:
                vid_link = f"`{s.video_id}` 📹" if s.video_id else "None"
                lines.append(
                    f"| `{s.match_id}` | {s_date} | **{s.opponent_name}** | {s_res} | {s_loc} | {s_scores} | {vid_link} |"
                )
            else:
                lines.append(
                    f"| `{s.match_id}` | {s_date} | **{s.opponent_name}** | {s_res} | {s_loc} | {s_scores} |"
                )

    return "\n".join(lines).strip()


def format_player_stats_markdown(
    players: List[PlayerStats],
    match_id: Optional[str] = None,
    team_name: Optional[str] = None,
) -> str:
    """Format athlete statistics into a clean, standard volleyball box score Markdown table."""
    if not players:
        return f"No player box score statistics found for match `{match_id}`."

    header = "### Athlete Box Score"
    if team_name:
        header += f" - {team_name}"
    if match_id:
        header += f" (Match ID: `{match_id}`)"

    lines = [
        header,
        "",
        "| # | Player | Pos | SP | K | E | TA | Hit % | Ast | SA | SE | Rec | RE | Pass Avg | Dig | BS | BA | TB | Pts |",
        "|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|---:|---:|---:|---:|---:|",
    ]

    total_k = total_e = total_ta = total_ast = total_sa = total_se = total_rec = total_re = total_dig = 0
    total_bs = total_ba = 0
    total_tb = total_pts = 0.0
    total_perfect = total_positive = total_medium = 0

    has_unassigned = False

    for p in players:
        jersey = p.jersey_number or "-"
        pos = p.position or "-"
        hit_str = format_hit_pct(p.hitting_percentage)
        pass_str = f"{p.pass_rating:.2f}" if p.pass_rating is not None else "-"
        tb_str = f"{p.total_blocks:.1f}" if p.total_blocks is not None else "0.0"
        pts_str = f"{p.points:.1f}" if p.points is not None else "0.0"

        if "unassigned" in p.player_name.lower() or not p.jersey_number:
            has_unassigned = True

        total_k += p.kills
        total_e += p.attack_errors
        total_ta += p.total_attacks
        total_ast += p.assists
        total_sa += p.aces
        total_se += p.serve_errors
        total_rec += p.receptions
        total_re += p.reception_errors
        total_perfect += p.perfect_passes
        total_positive += p.positive_passes
        total_medium += p.medium_passes
        total_dig += p.digs
        total_bs += p.block_solos
        total_ba += p.block_assists
        total_tb += p.total_blocks or 0.0
        total_pts += p.points or 0.0

        lines.append(
            f"| {jersey} | **{p.player_name}** | {pos} | {p.sets_played} | "
            f"{p.kills} | {p.attack_errors} | {p.total_attacks} | **{hit_str}** | "
            f"{p.assists} | {p.aces} | {p.serve_errors} | {p.receptions} | {p.reception_errors} | "
            f"{pass_str} | {p.digs} | {p.block_solos} | {p.block_assists} | {tb_str} | {pts_str} |"
        )

    # Team totals row
    team_hit_pct = (
        round((total_k - total_e) / total_ta, 3) if total_ta > 0 else 0.0
    )
    team_pass_avg_str = (
        f"{round((3 * total_perfect + 2 * total_positive + 1 * total_medium) / total_rec, 2):.2f}"
        if total_rec > 0
        else "-"
    )
    lines.append(
        f"| | **TEAM TOTALS** | | | **{total_k}** | **{total_e}** | **{total_ta}** | "
        f"**{format_hit_pct(team_hit_pct)}** | **{total_ast}** | **{total_sa}** | "
        f"**{total_se}** | **{total_rec}** | **{total_re}** | **{team_pass_avg_str}** | "
        f"**{total_dig}** | **{total_bs}** | **{total_ba}** | **{total_tb:.1f}** | **{total_pts:.1f}** |"
    )

    # Add passing quality breakdown if reception data is present
    passers = [p for p in players if p.receptions > 0]
    if passers:
        lines.extend([
            "",
            "#### 🎯 Serve Reception Quality Distribution",
            "",
            "| # | Player | Receptions | Perfect (3) | Positive (2) | Medium (1) | Error (0) | Pass Rating |",
            "|---:|---|---:|---:|---:|---:|---:|:---:|",
        ])
        for p in passers:
            jersey = p.jersey_number or "-"
            p_rating = f"{p.pass_rating:.2f}" if p.pass_rating is not None else "-"
            lines.append(
                f"| {jersey} | **{p.player_name}** | {p.receptions} | "
                f"{p.perfect_passes} | {p.positive_passes} | {p.medium_passes} | {p.reception_errors} | **{p_rating}** |"
            )

    if has_unassigned:
        lines.extend([
            "",
            "> ℹ️ **AI Tracking & Unassigned Touches Audit**:",
            "> Some touches could not be automatically linked to a specific jersey number by Balltime's computer vision and are grouped under `(Unassigned)`.",
            f"> To inspect or filter these specific touches and timestamps, use `get_game_actions(match_id=\"{match_id or ''}\", player=\"unassigned\")`.",
        ])

    return "\n".join(lines)


def format_rotation_stats_markdown(
    rotations: List[RotationStats],
    match_id: Optional[str] = None,
) -> str:
    """Format rotation statistics into a clean Markdown table with setter tendencies."""
    if not rotations:
        return f"No rotation breakdown found for match `{match_id}`."

    header = "### Rotation Efficiency Breakdown (P1 - P6)"
    if match_id:
        header += f" (Match ID: `{match_id}`)"

    lines = [
        header,
        "",
        "| Rotation | Sideout % (Earned/Att) | Point Scoring % (Earned/Att) | FBSO % | Setter Tendencies / Distribution | Notes |",
        "|:---:|:---:|:---:|:---:|---|---|",
    ]

    for r in rotations:
        so_str = format_pct(r.sideout_percentage)
        if r.sideouts_earned is not None and r.sideout_attempts is not None:
            so_str += f" ({r.sideouts_earned}/{r.sideout_attempts})"

        pt_str = format_pct(r.point_scoring_percentage)
        if r.points_scored_serving is not None and r.serve_attempts is not None:
            pt_str += f" ({r.points_scored_serving}/{r.serve_attempts})"

        fbso_str = format_pct(r.first_ball_sideout_rate)

        tendency_parts = []
        if r.setter_tendencies:
            for k, v in r.setter_tendencies.items():
                label = k.replace("Percent", "").replace("Pct", "").capitalize()
                val_display = format_pct(v)
                tendency_parts.append(f"{label}: {val_display}")
        tendency_str = ", ".join(tendency_parts) if tendency_parts else "Default distribution"

        notes_str = r.notes or "-"

        lines.append(
            f"| **{r.rotation_name}** | {so_str} | {pt_str} | {fbso_str} | {tendency_str} | {notes_str} |"
        )

    return "\n".join(lines)


# ==============================================================================
# BALLTIME VIDEO BREAKDOWN & ACTION PARSERS
# ==============================================================================

def format_video_timestamp(seconds: Optional[float]) -> str:
    """Format seconds into MM:SS or H:MM:SS format."""
    if seconds is None or seconds < 0:
        return "-"
    total_sec = int(seconds)
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    sec = total_sec % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def parse_video_actions(
    video_metadata: Any,
    set_number: Optional[int] = None,
    action_type: Optional[str] = None,
    player: Optional[str] = None,
    team: Optional[str] = None,
    quality: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[VolleyballAction]:
    """Parse raw video analysis actions/touches from Balltime breakdown metadata."""
    if isinstance(video_metadata, list) and video_metadata:
        video_metadata = video_metadata[0]
    if not isinstance(video_metadata, dict):
        return []

    player_names = video_metadata.get("player_names", {})
    team_a_name = video_metadata.get("team_a_name_override") or "Team A"
    team_b_name = video_metadata.get("team_b_name_override") or "Team B"
    rallies = video_metadata.get("video_analysis", [])

    def _resolve_player_info(act: Dict[str, Any], action_team: str) -> tuple[str, str, str]:
        p_list = act.get("player")
        player_obj = p_list[0] if (isinstance(p_list, list) and p_list and isinstance(p_list[0], dict)) else {}

        pid = act.get("player_id")
        pdata = player_names.get(str(pid), {}) if pid is not None else {}

        jersey = (
            player_obj.get("jersey_number")
            or pdata.get("jersey_number")
            or pdata.get("predicted_jersey_number")
            or player_obj.get("predicted_jersey_number")
        )
        t = player_obj.get("team") or pdata.get("team") or action_team or "?"
        t_name = team_a_name if t == "a" else (team_b_name if t == "b" else "Team")
        name = player_obj.get("name") or pdata.get("name")
        cluster_id = player_obj.get("id") or pdata.get("id") or (str(pid) if pid is not None else "unassigned")

        jersey_str = str(jersey) if jersey else ""
        if name and jersey_str:
            label = f"#{jersey_str} {name} ({t_name})"
        elif name:
            label = f"{name} ({t_name})"
        elif jersey_str:
            label = f"#{jersey_str} ({t_name})"
        elif pid is not None:
            label = f"Player {pid} ({t_name})"
        else:
            label = f"{t_name} (Unassigned)"
        return str(cluster_id), jersey_str, label

    actions_list: List[VolleyballAction] = []
    norm_action_type = action_type.strip().lower() if action_type else None
    if norm_action_type == "pass":
        norm_action_type = "receive"

    norm_player = player.strip().lower() if player else None
    norm_team = team.strip().lower() if team else None
    norm_quality = quality.strip().lower() if quality else None

    for rally in rallies:
        if not isinstance(rally, dict):
            continue

        r_set = _safe_int(rally.get("set_number"), default=1)
        if set_number is not None and r_set != set_number:
            continue

        r_score = rally.get("score")
        score_str = "-"
        if isinstance(r_score, dict):
            set_score = r_score.get("setScore", {})
            if isinstance(set_score, dict) and "a" in set_score and "b" in set_score:
                score_str = f"{set_score.get('a')}-{set_score.get('b')}"

        rally_actions = rally.get("actions", [])
        for act in rally_actions:
            if not isinstance(act, dict):
                continue

            a_skill = str(act.get("skill_type") or "").strip().lower()
            if not a_skill:
                continue

            # Filter: action_type
            if norm_action_type and norm_action_type not in a_skill:
                continue

            a_team = str(act.get("team") or "").strip().lower()
            a_team_name = team_a_name if a_team == "a" else (team_b_name if a_team == "b" else a_team)

            # Filter: team
            if norm_team:
                if norm_team in ("a", "team_a", "teama") and a_team != "a":
                    continue
                elif norm_team in ("b", "team_b", "teamb") and a_team != "b":
                    continue
                elif norm_team not in ("a", "b", "team_a", "team_b", "teama", "teamb") and norm_team not in a_team_name.lower():
                    continue

            cluster_id, jersey_num, player_lbl = _resolve_player_info(act, a_team)

            # Filter: player
            if norm_player:
                norm_clean = norm_player.lstrip("#")
                if norm_player in ("unassigned", "none", "unknown", "unverified"):
                    if jersey_num or ("unassigned" not in player_lbl.lower() and "unknown" not in player_lbl.lower()):
                        continue
                else:
                    if norm_clean != jersey_num and norm_clean not in player_lbl.lower():
                        continue

            a_quality = str(act.get("quality") or "").strip().lower()
            if a_quality == "none":
                a_quality = ""

            # Filter: quality
            if norm_quality and norm_quality not in a_quality:
                continue

            # Timestamp
            t_sec = _safe_float(act.get("timestamp")) or _safe_float(rally.get("start"))
            time_formatted = format_video_timestamp(t_sec)

            # Extra tactical details
            details_list = []
            att_type = act.get("attack_type")
            if att_type:
                details_list.append(f"Type: {att_type}")

            fbso = bool(act.get("first_ball_side_out"))
            if fbso:
                details_list.append("FBSO")

            pos = act.get("positional") or {}
            src_z = pos.get("src_zone")
            dest_z = pos.get("dest_zone")
            if src_z:
                details_list.append(f"Z{src_z}")
            if dest_z:
                details_list.append(f"-> Z{dest_z}")

            speed_raw = _safe_float(pos.get("speed"))
            speed_kmh = round(speed_raw * 3.6, 1) if speed_raw is not None else None
            if speed_kmh:
                details_list.append(f"{speed_kmh} km/h")

            v_height = _safe_float(pos.get("vertical_touch_height"))
            touch_height_m = round(v_height, 2) if v_height is not None else None
            if touch_height_m:
                details_list.append(f"{touch_height_m}m")

            is_override = bool(act.get("player_override"))
            if is_override:
                details_list.append("[Verified]")

            n_blockers = act.get("num_of_blockers")
            if n_blockers:
                details_list.append(f"{n_blockers} Blk")

            if act.get("was_deflected_in_block"):
                details_list.append("Deflected")

            detail_str = ", ".join(details_list) if details_list else None

            actions_list.append(
                VolleyballAction(
                    action_id=act.get("id"),
                    rally_id=rally.get("id"),
                    set_number=r_set,
                    score=score_str if score_str != "-" else None,
                    timestamp_seconds=t_sec,
                    timestamp_formatted=time_formatted,
                    team=a_team,
                    team_name=a_team_name,
                    player_id=cluster_id,
                    jersey_number=jersey_num or None,
                    player_label=player_lbl,
                    action_type=a_skill,
                    touch_type=act.get("touch_type"),
                    quality=a_quality or None,
                    attack_type=att_type,
                    first_ball_side_out=fbso,
                    source_zone=src_z,
                    dest_zone=dest_z,
                    speed_kmh=speed_kmh,
                    touch_height_m=touch_height_m,
                    is_verified=is_override,
                    details=detail_str,
                )
            )

    return actions_list[offset : offset + limit]


def format_actions_markdown(
    actions: List[VolleyballAction],
    match_name: Optional[str] = None,
    total_count: Optional[int] = None,
) -> str:
    """Format a list of volleyball actions into a clean, searchable Markdown event feed."""
    if not actions:
        return f"No actions found matching the specified criteria for match `{match_name or 'specified'}`."

    header = "### Tagged Match Actions & Events"
    if match_name:
        header += f" - **{match_name}**"

    lines = [header, ""]

    # Summary metrics for current page/filtered actions
    k_count = sum(1 for a in actions if a.action_type == "attack" and a.quality == "kill")
    e_count = sum(1 for a in actions if a.quality == "error")
    ace_count = sum(1 for a in actions if a.action_type == "serve" and a.quality == "ace")
    ast_count = sum(1 for a in actions if a.action_type == "set" and a.quality == "assist")
    dig_count = sum(1 for a in actions if a.action_type == "dig")
    blk_count = sum(1 for a in actions if a.action_type == "block")

    summary_parts = [
        f"**Showing**: {len(actions)} actions" + (f" (out of {total_count})" if total_count else ""),
        f"**Kills**: {k_count}",
        f"**Errors**: {e_count}",
        f"**Aces**: {ace_count}",
        f"**Assists**: {ast_count}",
        f"**Digs**: {dig_count}",
        f"**Blocks**: {blk_count}",
    ]
    lines.append(" | ".join(summary_parts))
    lines.append("")

    lines.append("| Set | Score | Video Time | Player / Team | Action | Result / Quality | Tactical Details |")
    lines.append("|:---:|:---:|:---:|:---|:---|:---|:---|")

    for a in actions:
        set_str = str(a.set_number)
        score_str = a.score or "-"
        time_str = a.timestamp_formatted or "-"
        player_str = a.player_label
        action_str = a.action_type.replace("_", " ").capitalize()
        quality_str = a.quality.replace("_", " ").capitalize() if a.quality else "-"
        detail_str = a.details or "-"

        lines.append(
            f"| {set_str} | {score_str} | `{time_str}` | **{player_str}** | {action_str} | {quality_str} | {detail_str} |"
        )

    return "\n".join(lines)


def parse_balltime_player_stats(
    video_metadata: Any,
    team: Optional[str] = None,
) -> List[PlayerStats]:
    """Parse Balltime video analysis actions into aggregated PlayerStats box score models."""
    if isinstance(video_metadata, list) and video_metadata:
        video_metadata = video_metadata[0]
    if not isinstance(video_metadata, dict):
        return []

    player_names = video_metadata.get("player_names", {})
    team_a_name = video_metadata.get("team_a_name_override") or "Team A"
    team_b_name = video_metadata.get("team_b_name_override") or "Team B"
    rallies = video_metadata.get("video_analysis", [])

    def _get_cluster_info(act: Dict[str, Any], action_team: str) -> tuple[str, str, str, str]:
        p_list = act.get("player")
        player_obj = p_list[0] if (isinstance(p_list, list) and p_list and isinstance(p_list[0], dict)) else {}

        pid = act.get("player_id")
        pdata = player_names.get(str(pid), {}) if pid is not None else {}

        jersey = (
            player_obj.get("jersey_number")
            or pdata.get("jersey_number")
            or pdata.get("predicted_jersey_number")
            or player_obj.get("predicted_jersey_number")
        )
        t = player_obj.get("team") or pdata.get("team") or action_team or "?"
        t_name = team_a_name if t == "a" else (team_b_name if t == "b" else t)
        name = player_obj.get("name") or pdata.get("name")
        cluster_id = player_obj.get("id") or pdata.get("id")

        jersey_str = str(jersey) if jersey else ""
        if cluster_id:
            key = str(cluster_id)
        elif jersey_str:
            key = f"{t}_{jersey_str}"
        else:
            key = f"{t}_unassigned"

        if name and jersey_str:
            display_name = f"#{jersey_str} {name}"
        elif name:
            display_name = name
        elif jersey_str:
            display_name = f"#{jersey_str}"
        else:
            display_name = f"{t_name} (Unassigned)" if t in ("a", "b") else "Unassigned"

        return key, t, jersey_str, display_name

    from collections import defaultdict
    stats_map = defaultdict(lambda: {
        "kills": 0, "attack_errors": 0, "attacks": 0,
        "assists": 0, "aces": 0, "serve_errors": 0, "serves": 0,
        "digs": 0, "block_solos": 0, "block_assists": 0, "block_errors": 0,
        "receptions": 0, "pass_3s": 0, "pass_2s": 0, "pass_1s": 0, "reception_errors": 0,
        "pass_ratings": [],
        "sets_played": set(), "team": "?", "jersey": "", "name": "", "team_name": ""
    })

    norm_team = team.strip().lower() if team else None

    for rally in rallies:
        if not isinstance(rally, dict):
            continue
        s_num = _safe_int(rally.get("set_number"), default=1)

        for act in rally.get("actions", []):
            if not isinstance(act, dict):
                continue
            skill = str(act.get("skill_type") or "").strip().lower()
            if not skill:
                continue

            a_team = str(act.get("team") or "").strip().lower()
            key, t_code, jersey_str, display_name = _get_cluster_info(act, a_team)

            # Filter by team if requested
            if norm_team:
                if norm_team in ("a", "team_a", "teama") and t_code != "a":
                    continue
                elif norm_team in ("b", "team_b", "teamb") and t_code != "b":
                    continue
                elif norm_team not in ("a", "b", "team_a", "team_b", "teama", "teamb"):
                    t_full = team_a_name if t_code == "a" else team_b_name
                    if norm_team not in t_full.lower():
                        continue

            rec = stats_map[key]
            rec["team"] = t_code
            rec["team_name"] = team_a_name if t_code == "a" else team_b_name
            rec["jersey"] = jersey_str
            if not rec["name"] or len(display_name) > len(rec["name"]):
                rec["name"] = display_name
            rec["sets_played"].add(s_num)

            qual = str(act.get("quality") or "").strip().lower()

            if skill == "attack":
                rec["attacks"] += 1
                if qual == "kill":
                    rec["kills"] += 1
                elif qual == "error":
                    rec["attack_errors"] += 1
            elif skill == "serve":
                rec["serves"] += 1
                if qual == "ace":
                    rec["aces"] += 1
                elif qual in ("error", "fault"):
                    rec["serve_errors"] += 1
            elif skill == "set":
                if qual == "assist":
                    rec["assists"] += 1
            elif skill == "dig":
                rec["digs"] += 1
            elif skill == "block":
                if qual in ("block_solo", "solo"):
                    rec["block_solos"] += 1
                elif qual in ("block_assist", "assist"):
                    rec["block_assists"] += 1
                elif qual in ("kill", "success"):
                    rec["block_solos"] += 1
                elif qual == "error":
                    rec["block_errors"] += 1
                else:
                    rec["block_assists"] += 1
            elif skill in ("receive", "free_ball_received"):
                rec["receptions"] += 1
                if qual == "3":
                    rec["pass_3s"] += 1
                    rec["pass_ratings"].append(3)
                elif qual == "2":
                    rec["pass_2s"] += 1
                    rec["pass_ratings"].append(2)
                elif qual == "1":
                    rec["pass_1s"] += 1
                    rec["pass_ratings"].append(1)
                elif qual in ("0", "error"):
                    rec["reception_errors"] += 1
                    rec["pass_ratings"].append(0)

    players_list: List[PlayerStats] = []
    for key, s in stats_map.items():
        # Include if active in any skill
        if not (s["attacks"] > 0 or s["serves"] > 0 or s["digs"] > 0 or s["assists"] > 0 or s["receptions"] > 0 or s["block_solos"] > 0 or s["block_assists"] > 0):
            continue

        avg_pass = round(sum(s["pass_ratings"]) / len(s["pass_ratings"]), 2) if s["pass_ratings"] else None
        p_name = f"{s['name']} ({s['team_name']})"
        total_blk = s["block_solos"] + (0.5 * s["block_assists"])

        players_list.append(
            PlayerStats(
                player_id=key,
                jersey_number=s["jersey"],
                player_name=p_name,
                position="",
                sets_played=len(s["sets_played"]) or 1,
                kills=s["kills"],
                attack_errors=s["attack_errors"],
                total_attacks=s["attacks"],
                assists=s["assists"],
                aces=s["aces"],
                serve_errors=s["serve_errors"],
                total_serves=s["serves"],
                digs=s["digs"],
                receptions=s["receptions"],
                perfect_passes=s["pass_3s"],
                positive_passes=s["pass_2s"],
                medium_passes=s["pass_1s"],
                reception_errors=s["reception_errors"],
                pass_rating=avg_pass,
                block_solos=s["block_solos"],
                block_assists=s["block_assists"],
                total_blocks=total_blk,
                block_errors=s["block_errors"],
            )
        )

    # Sort players: named jersey first, then highest points descending
    players_list.sort(key=lambda p: (not bool(p.jersey_number), -(p.points or 0.0), -(p.kills or 0)))
    return players_list


def parse_balltime_rotation_stats(
    video_metadata: Any,
    team: Optional[str] = "a",
) -> List[RotationStats]:
    """Calculate tactical rotation metrics (P1 through P6) from Balltime video analysis."""
    if isinstance(video_metadata, list) and video_metadata:
        video_metadata = video_metadata[0]
    if not isinstance(video_metadata, dict):
        return []

    rallies = video_metadata.get("video_analysis", [])
    target_team = "a"
    if team:
        t_clean = team.strip().lower()
        if t_clean in ("b", "team_b", "teamb"):
            target_team = "b"
        elif "volero" in t_clean or "zurich" in t_clean or "zürich" in t_clean:
            target_team = "b"

    opp_team = "b" if target_team == "a" else "a"

    from collections import defaultdict
    rot_data = {
        p: {
            "sideout_attempts": 0, "sideouts_won": 0, "fbso_count": 0,
            "serve_attempts": 0, "serve_points_won": 0,
            "kills": 0, "attacks": 0, "attack_errors": 0,
            "aces": 0, "serve_errors": 0,
            "setter_dists": defaultdict(int),
        }
        for p in range(1, 7)
    }

    curr_set = None
    curr_rot = 1

    for r in rallies:
        if not isinstance(r, dict):
            continue

        s_num = _safe_int(r.get("set_number"), default=1)
        if s_num != curr_set:
            curr_set = s_num
            curr_rot = 1  # Reset rotation to P1 at start of each set

        srv_team = str(r.get("serving_team") or "").strip().lower()
        won_team = str(r.get("team_won") or "").strip().lower()

        # Receiving sideout evaluation
        if srv_team == opp_team:
            rot_data[curr_rot]["sideout_attempts"] += 1
            if won_team == target_team:
                rot_data[curr_rot]["sideouts_won"] += 1
                if any(bool(a.get("first_ball_side_out")) and a.get("team") == target_team for a in r.get("actions", [])):
                    rot_data[curr_rot]["fbso_count"] += 1
                # Sideout won: advances upcoming serving rotation
                curr_rot = (curr_rot % 6) + 1
        elif srv_team == target_team:
            rot_data[curr_rot]["serve_attempts"] += 1
            if won_team == target_team:
                rot_data[curr_rot]["serve_points_won"] += 1

        # Track skill events in this rotation
        for a in r.get("actions", []):
            if not isinstance(a, dict):
                continue
            if str(a.get("team") or "").strip().lower() == target_team:
                skill = str(a.get("skill_type") or "").strip().lower()
                qual = str(a.get("quality") or "").strip().lower()

                if skill == "attack":
                    rot_data[curr_rot]["attacks"] += 1
                    if qual == "kill":
                        rot_data[curr_rot]["kills"] += 1
                    elif qual == "error":
                        rot_data[curr_rot]["attack_errors"] += 1
                elif skill == "serve":
                    if qual == "ace":
                        rot_data[curr_rot]["aces"] += 1
                    elif qual == "error":
                        rot_data[curr_rot]["serve_errors"] += 1
                elif skill == "set":
                    dest = a.get("positional", {}).get("dest_zone")
                    if dest in (4, 7):
                        rot_data[curr_rot]["setter_dists"]["Left (P4)"] += 1
                    elif dest in (3,):
                        rot_data[curr_rot]["setter_dists"]["Middle (P3)"] += 1
                    elif dest in (2, 1):
                        rot_data[curr_rot]["setter_dists"]["Right (P2)"] += 1
                    elif dest in (5, 6, 8):
                        rot_data[curr_rot]["setter_dists"]["Pipe / Back"] += 1

    rotations_list: List[RotationStats] = []
    for p in range(1, 7):
        rec = rot_data[p]
        so_pct = (rec["sideouts_won"] / rec["sideout_attempts"] * 100) if rec["sideout_attempts"] > 0 else 0.0
        pt_pct = (rec["serve_points_won"] / rec["serve_attempts"] * 100) if rec["serve_attempts"] > 0 else 0.0
        fbso_pct = (rec["fbso_count"] / rec["sideout_attempts"] * 100) if rec["sideout_attempts"] > 0 else 0.0
        hit_pct = ((rec["kills"] - rec["attack_errors"]) / rec["attacks"]) if rec["attacks"] > 0 else 0.0

        total_sets = sum(rec["setter_dists"].values())
        tendencies = {}
        if total_sets > 0:
            for k, count in rec["setter_dists"].items():
                tendencies[k] = round((count / total_sets) * 100, 1)

        notes = f"Hitting: {hit_pct:+.3f} ({rec['kills']} K, {rec['attack_errors']} E, {rec['attacks']} Att), {rec['aces']} Aces"

        rotations_list.append(
            RotationStats(
                rotation_number=p,
                rotation_name=f"P{p}",
                sideout_percentage=round(so_pct, 1),
                sideouts_earned=rec["sideouts_won"],
                sideout_attempts=rec["sideout_attempts"],
                point_scoring_percentage=round(pt_pct, 1),
                points_scored_serving=rec["serve_points_won"],
                serve_attempts=rec["serve_attempts"],
                first_ball_sideout_rate=round(fbso_pct, 1),
                setter_tendencies=tendencies,
                notes=notes,
            )
        )
    return rotations_list


# ==============================================================================
# DUAL-MODE OUTPUT RENDERERS (Context-Window Optimization)
# ==============================================================================

def render_matches_output(
    matches: List[MatchSummary],
    team_id: Optional[str] = None,
    output_format: str = "markdown",
) -> str:
    """Render matches as either a clean Markdown table or compact high-signal JSON."""
    fmt = (output_format or "markdown").lower().strip()
    if fmt in ("compact", "json"):
        compact_list = [m.to_compact_dict() for m in matches]
        return json.dumps(compact_list, separators=(",", ":"))
    return format_matches_markdown(matches, team_id=team_id)


def render_player_stats_output(
    players: List[PlayerStats],
    match_id: str,
    output_format: str = "markdown",
) -> str:
    """Render box scores as either a clean Markdown table or compact high-signal JSON."""
    fmt = (output_format or "markdown").lower().strip()
    if fmt in ("compact", "json"):
        compact_list = [p.to_compact_dict() for p in players]
        return json.dumps(compact_list, separators=(",", ":"))
    return format_player_stats_markdown(players, match_id=match_id)


def render_rotation_stats_output(
    rotations: List[RotationStats],
    match_id: str,
    output_format: str = "markdown",
) -> str:
    """Render rotations as either a clean Markdown table or compact high-signal JSON."""
    fmt = (output_format or "markdown").lower().strip()
    if fmt in ("compact", "json"):
        compact_list = [r.to_compact_dict() for r in rotations]
        return json.dumps(compact_list, separators=(",", ":"))
    return format_rotation_stats_markdown(rotations, match_id=match_id)


def render_actions_output(
    actions: List[VolleyballAction],
    match_name: str = "",
    output_format: str = "markdown",
) -> str:
    """Render event actions as either a clean Markdown table or compact high-signal JSON."""
    fmt = (output_format or "markdown").lower().strip()
    if fmt in ("compact", "json"):
        compact_list = [a.to_compact_dict() for a in actions]
        return json.dumps(compact_list, separators=(",", ":"))
    return format_actions_markdown(actions, match_name=match_name)


def render_teams_output(
    teams: List[TeamInfo],
    active_team_id: Optional[str] = None,
    output_format: str = "markdown",
) -> str:
    """Render user teams as either a clean Markdown table or compact high-signal JSON."""
    fmt = (output_format or "markdown").lower().strip()
    if fmt in ("compact", "json"):
        compact_list = [t.to_compact_dict() for t in teams]
        return json.dumps(compact_list, separators=(",", ":"))
    return format_teams_markdown(teams, active_team_id=active_team_id)
