"""FastMCP server instance and tool definitions for Hudl Volleyball MCP.

This server exposes Model Context Protocol tools for AI clients (such as Claude Desktop
or Cursor) to query Hudl's internal GraphQL API for volleyball matches, athlete box
scores, rotation breakdowns, and automated session cookie refreshing.
"""

from __future__ import annotations

import os
from typing import Annotated, Optional
from mcp.server.fastmcp import FastMCP

from hudl_mcp.auth_refresh import interactive_login, refresh_session
from hudl_mcp.cache import clear_all_cache
from hudl_mcp.client import (
    HudlAuthError,
    HudlClient,
    HudlConnectionError,
    HudlError,
    HudlGraphQLError,
    HudlSecurityError,
    get_hudl_team_id,
)
from hudl_mcp.models import (
    format_actions_markdown,
    format_matches_markdown,
    format_player_stats_markdown,
    format_rotation_stats_markdown,
    format_teams_markdown,
    render_actions_output,
    render_matches_output,
    render_player_stats_output,
    render_rotation_stats_output,
    render_teams_output,
)

# Initialize FastMCP Server
mcp = FastMCP(
    "hudl-volleyball-mcp",
    instructions=(
        "Hudl Volleyball MCP Server connects to Hudl and Balltime video breakdown APIs "
        "to retrieve match schedules, athlete box scores, rotation breakdown statistics (P1-P6), "
        "and complete event-by-event volleyball touches with DataVolley (.dvw) skill and evaluation codes. "
        "Use get_user_teams to discover your team ID automatically, list_volleyball_matches to find matches, "
        "get_match_player_stats to analyze individual player box scores, get_rotation_breakdown to analyze P1-P6 efficiencies, "
        "get_game_actions to query all tagged actions and touches (serves, passes, attacks, digs, sets, blocks), "
        "and login_to_hudl to log in interactively via an pop-up browser window without storing passwords."
    ),
)


@mcp.tool()
async def get_user_teams(
    output_format: Annotated[
        str,
        "Desired output representation: 'markdown' for human-readable table or 'compact' for token-efficient JSON",
    ] = "markdown",
    force_refresh: Annotated[
        bool,
        "Bypass local 15-minute disk cache and force a live API fetch",
    ] = False,
) -> str:
    """Discover and list all Hudl teams associated with your account to find your Team ID.

    Retrieves team names, team IDs, club/school organizations, roles (e.g. Coach),
    and active seasons directly from your authenticated Hudl account.

    Args:
        output_format: Format of the output: 'markdown' (clean table) or 'compact' (token-efficient JSON).
        force_refresh: If True, bypasses local 15-minute disk cache and forces a live fetch.

    Returns:
        A formatted Markdown table or compact JSON dictionary of your teams.
    """
    try:
        client = HudlClient()
        teams = await client.get_user_teams(force_refresh=force_refresh)
        active_tid = client.team_id or get_hudl_team_id()
        return render_teams_output(teams, active_team_id=active_tid, output_format=output_format)

    except HudlAuthError as exc:
        return (
            f"⚠️ Authentication Error: {exc}\n\n"
            "Action Required: Please call the `login_to_hudl` tool (or say 'Log me into Hudl') to log in via a browser window."
        )
    except HudlSecurityError as exc:
        return f"🛡️ Security Error: {exc}"
    except HudlConnectionError as exc:
        return f"🌐 Connection Error: {exc}"
    except HudlError as exc:
        return f"⚠️ Error: {exc}"
    except Exception as exc:
        return f"Unexpected error while fetching user teams: {type(exc).__name__}: {exc}"


@mcp.tool()
async def list_volleyball_matches(
    team_id: Annotated[
        Optional[str],
        "Hudl team identifier. If omitted, automatically resolves your active team ID.",
    ] = None,
    limit: Annotated[
        int,
        "Maximum number of recent matches and video recordings to retrieve (default: 10)",
    ] = 10,
    output_format: Annotated[
        str,
        "Output format: 'markdown' (table) or 'compact' (token-efficient JSON)",
    ] = "markdown",
    force_refresh: Annotated[
        bool,
        "Bypass local 15-minute disk cache and force a live API fetch",
    ] = False,
) -> str:
    """Fetch recent volleyball matches for a team from Hudl.

    Returns a table or compact JSON containing match IDs, dates, opponent names, results,
    and set scores. Call this tool first when a user asks about match results or team
    performance to discover the appropriate match_id for downstream analysis.

    Args:
        team_id: Optional Hudl team ID. If omitted, uses auto-detected team ID.
        limit: Maximum number of recent matches to retrieve (default: 10).
        output_format: Output format: 'markdown' (table) or 'compact' (token-efficient JSON).
        force_refresh: If True, bypasses local 15-minute disk cache and forces a live fetch.

    Returns:
        A formatted table or compact JSON of matches or an actionable error message.
    """
    try:
        client = HudlClient()
        active_team_id = team_id or client.team_id or await client.resolve_active_team_id(force_refresh=force_refresh)
        matches = await client.get_recent_matches(team_id=active_team_id, limit=limit, force_refresh=force_refresh)
        return render_matches_output(matches, team_id=active_team_id, output_format=output_format)

    except HudlAuthError as exc:
        return (
            f"⚠️ Authentication Error: {exc}\n\n"
            "Action Required: Your Hudl session cookie has expired or is missing. "
            "Please call the `login_to_hudl` tool (or say 'Log me into Hudl') to log in via a browser window."
        )
    except HudlSecurityError as exc:
        return f"🛡️ Security Error: {exc}"
    except HudlGraphQLError as exc:
        return (
            f"❌ GraphQL Query Error: {exc}\n\n"
            "Note: If Hudl changed its GraphQL schema, inspect the request in "
            "Chrome DevTools (Network tab -> graphql) and update GET_RECENT_MATCHES_QUERY in queries.py."
        )
    except HudlConnectionError as exc:
        return f"🌐 Connection Error: {exc}"
    except HudlError as exc:
        return f"⚠️ Error: {exc}"
    except Exception as exc:
        return f"Unexpected error while fetching matches: {type(exc).__name__}: {exc}"


@mcp.tool()
async def get_match_player_stats(
    match_id: Annotated[
        str,
        "Unique Hudl match identifier or video hex ID (obtainable via list_volleyball_matches)",
    ],
    team_id: Annotated[
        Optional[str],
        "Optional Hudl team ID to filter athlete statistics to a specific squad",
    ] = None,
    output_format: Annotated[
        str,
        "Desired output representation: 'markdown' for standard box score table or 'compact' for token-efficient JSON",
    ] = "markdown",
    force_refresh: Annotated[
        bool,
        "Bypass local 7-day disk cache and force a live API fetch",
    ] = False,
) -> str:
    """Fetch individual athlete box scores and volleyball statistics for a match.

    Retrieves player stats, strips unnecessary UI metadata, ensures hitting percentage
    ((Kills - Errors) / Total Attacks) is accurately calculated, and formats the output
    into a clean, standard volleyball box score table or compact JSON including Kills (K),
    Attack Errors (E), Total Attacks (TA), Hitting % (Hit%), Assists (A), Service Aces (SA),
    Service Errors (SE), Digs (D), Block Solos (BS), Block Assists (BA), Total Blocks (TB),
    and Total Points (PTS).

    Args:
        match_id: The unique Hudl match identifier (obtainable via list_volleyball_matches).
        team_id: Optional Hudl team ID to filter stats to a specific team.
        output_format: Output format: 'markdown' (standard box score table) or 'compact' (token-efficient JSON).
        force_refresh: If True, bypasses local 7-day disk cache and forces a live fetch.

    Returns:
        A formatted volleyball box score table or compact JSON.
    """
    if not match_id or not match_id.strip():
        return "Error: 'match_id' parameter is required. Use 'list_volleyball_matches' to find match IDs."

    try:
        client = HudlClient()
        players = await client.get_match_player_stats(
            match_id=match_id.strip(), team_id=team_id, force_refresh=force_refresh
        )
        return render_player_stats_output(players, match_id=match_id.strip(), output_format=output_format)

    except HudlAuthError as exc:
        return (
            f"⚠️ Authentication Error: {exc}\n\n"
            "Action Required: Please call the `login_to_hudl` tool (or say 'Log me into Hudl') to log in via a browser window."
        )
    except HudlSecurityError as exc:
        return f"🛡️ Security Error: {exc}"
    except HudlGraphQLError as exc:
        return (
            f"❌ GraphQL Query Error: {exc}\n\n"
            "Tip: Check GET_MATCH_PLAYER_STATS_QUERY in queries.py against your Chrome DevTools Network payload."
        )
    except HudlConnectionError as exc:
        return f"🌐 Connection Error: {exc}"
    except HudlError as exc:
        return f"⚠️ Error: {exc}"
    except Exception as exc:
        return f"Unexpected error while fetching player statistics: {type(exc).__name__}: {exc}"


@mcp.tool()
async def get_rotation_breakdown(
    match_id: Annotated[
        str,
        "Unique Hudl match identifier or video hex ID (obtainable via list_volleyball_matches)",
    ],
    team_id: Annotated[
        Optional[str],
        "Optional Hudl team ID to filter rotation analytics to a specific squad",
    ] = None,
    output_format: Annotated[
        str,
        "Desired output representation: 'markdown' for P1-P6 sideout table or 'compact' for token-efficient JSON",
    ] = "markdown",
    force_refresh: Annotated[
        bool,
        "Bypass local 7-day disk cache and force a live API fetch",
    ] = False,
) -> str:
    """Fetch tactical performance metrics broken down by volleyball rotation (P1 through P6).

    Returns sideout efficiency (earned sideout points / total receive opportunities), point
    scoring percentage while serving, first-ball sideout (FBSO) conversion rates, and
    setter distribution tendencies for each rotation (P1: Setter in Zone 1 serving/receiving,
    P2: Setter in Zone 6, P3: Setter in Zone 5, P4: Setter in Zone 4, P5: Setter in Zone 3,
    P6: Setter in Zone 2).

    Args:
        match_id: The unique Hudl match identifier (obtainable via list_volleyball_matches).
        team_id: Optional Hudl team ID to filter breakdown to a specific team.
        output_format: Output format: 'markdown' (table) or 'compact' (token-efficient JSON).
        force_refresh: If True, bypasses local 7-day disk cache and forces a live fetch.

    Returns:
        A formatted table or compact JSON of rotation analytics (P1 through P6).
    """
    if not match_id or not match_id.strip():
        return "Error: 'match_id' parameter is required. Use 'list_volleyball_matches' to find match IDs."

    try:
        client = HudlClient()
        rotations = await client.get_rotation_stats(
            match_id=match_id.strip(), team_id=team_id, force_refresh=force_refresh
        )
        return render_rotation_stats_output(rotations, match_id=match_id.strip(), output_format=output_format)

    except HudlAuthError as exc:
        return (
            f"⚠️ Authentication Error: {exc}\n\n"
            "Action Required: Please call the `login_to_hudl` tool (or say 'Log me into Hudl') to log in via a browser window."
        )
    except HudlSecurityError as exc:
        return f"🛡️ Security Error: {exc}"
    except HudlGraphQLError as exc:
        return (
            f"❌ GraphQL Query Error: {exc}\n\n"
            "Tip: Check GET_ROTATION_STATS_QUERY in queries.py against your Chrome DevTools Network payload."
        )
    except HudlConnectionError as exc:
        return f"🌐 Connection Error: {exc}"
    except HudlError as exc:
        return f"⚠️ Error: {exc}"
    except Exception as exc:
        return f"Unexpected error while fetching rotation breakdown: {type(exc).__name__}: {exc}"


@mcp.tool()
async def get_game_actions(
    match_id: Annotated[
        str,
        "Unique match identifier, Balltime UUID, Hudl video hex ID, or match title",
    ],
    set_number: Annotated[
        Optional[int],
        "Set number (e.g. 1, 2, 3, 4, 5) to restrict events to a specific set",
    ] = None,
    action_type: Annotated[
        Optional[str],
        "Volleyball skill/action filter: 'attack' (A), 'serve' (S), 'receive'/'pass' (R), 'set' (E), 'dig' (D), 'block' (B)",
    ] = None,
    player: Annotated[
        Optional[str],
        "Athlete filter: jersey number (e.g. '20', '#7') or player name",
    ] = None,
    team: Annotated[
        Optional[str],
        "Team filter: 'a', 'b', home/away, or team name (e.g. 'Lutry' or 'Voléro')",
    ] = None,
    quality: Annotated[
        Optional[str],
        "DataVolley evaluation/quality filter: 'kill' (#), 'error' (=), 'ace' (#), 'assist', 'in_play', 'perfect_pass' (#), 'positive_pass' (+), 'medium_pass' (!), 'poor_pass' (-)",
    ] = None,
    limit: Annotated[
        int,
        "Maximum number of chronological volleyball touches to return (default: 50)",
    ] = 50,
    offset: Annotated[
        int,
        "Pagination offset for scrolling through match events (default: 0)",
    ] = 0,
    output_format: Annotated[
        str,
        "Desired output representation: 'markdown' for action table or 'compact' for token-efficient JSON",
    ] = "markdown",
    force_refresh: Annotated[
        bool,
        "Bypass local 7-day disk cache and force a live API fetch",
    ] = False,
) -> str:
    """Retrieve detailed tagged volleyball actions and touch events from a match/video breakdown.

    Returns an event-by-event timeline including set number, score, video timestamp,
    player jersey/name, action type (serve, receive, set, attack, dig, block), result/quality
    (kill, error, ace, assist, in-play, rating), and tactical details (start/end zones, attack routes,
    blocker count, FBSO). Supports DataVolley (.dvw) skill codes (S, R, E, A, B, D, F) and
    evaluation codes (# Perfect/Kill/Ace, + Positive, ! Medium, - Poor, = Error).

    Args:
        match_id: The unique match identifier, Balltime video ID, Hudl video hex ID, or match name/title.
        set_number: Optional set number (e.g. 1, 2, 3) to filter events to a specific set.
        action_type: Optional action filter: 'attack', 'serve', 'receive'/'pass', 'set', 'dig', 'block'.
        player: Optional player filter: jersey number (e.g. '17', '1') or player name.
        team: Optional team filter: 'a', 'b', or team name (e.g. 'Lutry' or 'Voléro').
        quality: Optional quality/result filter: 'kill', 'error', 'ace', 'assist', 'in_play'.
        limit: Maximum number of events to return (default: 50).
        offset: Offset for paging through match events (default: 0).
        output_format: Output format: 'markdown' (table) or 'compact' (token-efficient JSON).
        force_refresh: If True, bypasses local 7-day disk cache and forces a live fetch.

    Returns:
        A formatted table or compact JSON of tagged match actions and event statistics.
    """
    if not match_id or not match_id.strip():
        return "Error: 'match_id' parameter is required. Use 'list_volleyball_matches' to find match IDs."

    try:
        client = HudlClient()
        actions = await client.get_game_actions(
            match_id=match_id.strip(),
            set_number=set_number,
            action_type=action_type,
            player=player,
            team=team,
            quality=quality,
            limit=limit,
            offset=offset,
            force_refresh=force_refresh,
        )
        return render_actions_output(actions, match_name=match_id.strip(), output_format=output_format)

    except HudlAuthError as exc:
        return (
            f"⚠️ Authentication Error: {exc}\n\n"
            "Action Required: Please call the `login_to_hudl` tool (or say 'Log me into Hudl') to log in via a browser window."
        )
    except HudlSecurityError as exc:
        return f"🛡️ Security Error: {exc}"
    except HudlConnectionError as exc:
        return f"🌐 Connection Error: {exc}"
    except HudlError as exc:
        return f"⚠️ Error: {exc}"
    except Exception as exc:
        return f"Unexpected error while fetching game actions: {type(exc).__name__}: {exc}"


@mcp.tool()
async def login_to_hudl(timeout_seconds: int = 300) -> str:
    """Open an interactive pop-up browser window to log into Hudl and save session state.

    Opens a visible browser to https://www.hudl.com/login where you can log in normally
    using your password manager (1Password, Bitwarden, iCloud Keychain, etc.), Google/Apple SSO,
    or two-factor authentication (2FA).

    The moment navigation to https://www.hudl.com/home is detected, the session state
    is automatically saved to ~/.hudl_mcp/auth_state.json, the browser closes, and your active
    session is updated without ever storing your password.

    Args:
        timeout_seconds: Maximum time in seconds to wait for login completion (default: 300 = 5 minutes).

    Returns:
        A confirmation status message when login completes or details on any error.
    """
    res = await interactive_login(timeout_seconds=timeout_seconds)
    if res.get("success"):
        clear_all_cache()
        return (
            f"✅ **Hudl Login Successful!**\n\n"
            f"- **Browser Window Closed**: Login completed.\n"
            f"- **Session State Saved**: `{res.get('storage_state_file')}`\n"
            f"- **Active Session**: `{res.get('masked_cookie')}`\n\n"
            "You are authenticated! You can now run any volleyball queries (box scores, matches, rotations, actions)."
        )
    else:
        err = res.get("error", "Unknown error")
        return f"❌ **Hudl Login Failed**: {err}"


@mcp.tool()
async def refresh_hudl_cookie() -> str:
    """Refresh the Hudl session authentication cookie.

    If credentials are configured in .env, attempts automated refresh.
    Otherwise, recommends or triggers interactive pop-up browser login via login_to_hudl.

    Returns:
        A confirmation status message indicating success or details on how to log in.
    """
    if os.getenv("HUDL_EMAIL") and os.getenv("HUDL_PASSWORD"):
        res = await refresh_session()
        if res.get("success"):
            clear_all_cache()
            return (
                f"✅ Hudl Session Refreshed Successfully!\n\n"
                f"- Masked Cookie: `{res.get('masked_cookie')}`\n"
                f"- Configuration File Updated: `{res.get('env_file')}`\n\n"
                "The active in-memory session has been updated. You can now re-run your volleyball queries."
            )
        else:
            err = res.get("error", "Unknown error")
            return (
                f"❌ Failed to refresh Hudl session: {err}\n\n"
                "Recommended Action: Call the `login_to_hudl` tool (or say 'Log me into Hudl') to log in "
                "interactively via a browser window using your password manager, Google/Apple SSO, or 2FA."
            )

    return (
        "ℹ️ **Interactive Login Recommended**\n\n"
        "Username and password are not stored in `.env`. Please call the `login_to_hudl` tool "
        "(or say **'Log me into Hudl'**).\n\n"
        "This will open a visible pop-up browser window to https://hudl.com/login where you can log in "
        "using your password manager, Google/Apple SSO, or 2FA. Once you reach `hudl.com/home`, the session "
        "is automatically saved to `~/.hudl_mcp/auth_state.json` and the window closes."
    )


# ---------------------------------------------------------------------------
# FastMCP Prompts for Volleyball Coaching and Scouting Workflows
# ---------------------------------------------------------------------------


@mcp.prompt()
def scout_opponent(
    opponent_name: Annotated[
        str,
        "Name of the opponent volleyball team or school/club to scout",
    ],
) -> str:
    """Generate a comprehensive tactical scouting report on an opponent team.

    This workflow guides the AI through locating recent matches against or featuring
    the opponent, analyzing top scoring threats, identifying serve-receive weaknesses,
    and designing a match game plan.
    """
    return (
        f"You are an expert Volleyball Performance Analyst and Head Coach preparing a match scouting report on '{opponent_name}'.\n\n"
        "Follow these analytical steps:\n"
        f"1. **Locate Match Data**: Call `list_volleyball_matches(limit=10)` to find recent matches involving '{opponent_name}'.\n"
        "2. **Analyze Opponent Offense**: For the identified match, call `get_match_player_stats(match_id=...)` to inspect the box score. "
        "Identify their primary point producers, high-volume pin hitters, and their hitting percentage ((K - E) / TA).\n"
        "3. **Audit Opponent Rotations**: Call `get_rotation_breakdown(match_id=...)` to examine their sideout efficiencies across rotations P1 through P6. "
        "Highlight their weakest sideout rotation (lowest sideout %) where our team should look to score multi-point service runs.\n"
        "4. **Analyze Serve-Receive Vulnerabilities**: Call `get_game_actions(match_id=..., action_type='receive')` to evaluate their passers. "
        "Find which passer has the highest error rate or lowest 3-pass percentage.\n"
        "5. **Synthesize Game Plan**: Produce a structured coaching report containing:\n"
        "   - **Key Players to Neutralize**: Attack tendencies, favored zones (e.g. Zone 4 line vs cross, Zone 2 cut, pipe).\n"
        "   - **Serving Strategy**: Recommended serving targets (seams, short Zone 2/4, deep corner) and specific passers to isolate.\n"
        "   - **Defensive & Blocking Scheme**: Perimeter vs middle-up defense, commit vs read blocking against their middles.\n"
        "   - **Rotational Exploit Targets**: Specific rotations (P1-P6) where we must apply maximum pressure."
    )


@mcp.prompt()
def analyze_rotation_weaknesses(
    match_id: Annotated[
        str,
        "Unique Hudl match ID or video hex ID to diagnose",
    ],
) -> str:
    """Diagnose sideout and point scoring vulnerabilities across rotations P1 through P6.

    This workflow evaluates rotation-by-rotation performance to isolate tactical flaws
    in serve-receive formations, setter distribution, or transition scoring.
    """
    return (
        f"You are a Volleyball Tactical Analyst conducting a deep-dive rotation analysis for match '{match_id}'.\n\n"
        "Execute the following steps:\n"
        f"1. **Fetch Rotation Analytics**: Call `get_rotation_breakdown(match_id='{match_id}')` to retrieve sideout percentage, "
        "point-scoring percentage, and first-ball sideout (FBSO) rates for rotations P1, P2, P3, P4, P5, and P6.\n"
        f"2. **Investigate Trouble Rotations**: For any rotation with sideout efficiency below 50%:\n"
        f"   - Call `get_game_actions(match_id='{match_id}', action_type='receive', quality='error')` to check for direct reception errors.\n"
        f"   - Call `get_game_actions(match_id='{match_id}', action_type='attack', quality='error')` to check if errors were unforced attack errors or blocked attacks.\n"
        "3. **Setter Distribution**: Evaluate whether the setter became predictable in out-of-system plays (e.g., exclusively setting high-ball outside to Zone 4).\n"
        "4. **Actionable Coaching Recommendations**: Provide concrete adjustments:\n"
        "   - Serve-receive pattern adjustment (e.g. dropping an OH deeper, switching to a 2-person receive line, or hiding a weaker passer).\n"
        "   - Route adjustments (e.g. running middle slide behind setter in P1/P2 or back-row pipe to open the net).\n"
        "   - Sideout tempo modifications to relieve pressure."
    )


@mcp.prompt()
def match_mvp_breakdown(
    match_id: Annotated[
        str,
        "Unique Hudl match ID or video hex ID to evaluate",
    ],
) -> str:
    """Determine the Most Valuable Player (MVP) of a match using advanced volleyball metrics.

    Calculates True Point Scoring (Points = Kills + Aces + Blocks), Efficiency ((K - E) / TA),
    and Defensive Impact (Digs, Passer Rating) to select the MVP with quantitative rigor.
    """
    return (
        f"You are an Elite Volleyball Analyst selecting the official Match MVP for match '{match_id}'.\n\n"
        "Follow these steps:\n"
        f"1. **Retrieve Box Score**: Call `get_match_player_stats(match_id='{match_id}')`.\n"
        "2. **Calculate Advanced Value Metrics**:\n"
        "   - **True Points**: Kills + Aces + Solo Blocks + 0.5 * Block Assists.\n"
        "   - **Hitting Efficiency**: (Kills - Attack Errors) / Total Attacks.\n"
        "   - **Point Differential**: Total Points scored minus Total Errors committed (Attack Errors + Service Errors + Ball Handling Errors).\n"
        f"3. **Inspect Clutch Touches**: Call `get_game_actions(match_id='{match_id}', quality='kill', limit=50)` to evaluate late-set kills (set scores 20+).\n"
        "4. **Award Categories**:\n"
        "   - 🏆 **Match MVP**: The athlete with the highest net impact on match outcome, supported by exact statistics.\n"
        "   - ⚡ **Offensive Player of the Match**: Highest kill efficiency and terminal attack rate.\n"
        "   - 🛡️ **Defensive Anchor**: Best performance in digs, serve receive stability, and block touches.\n"
        "   - ⭐ **Unsung Hero**: A role player whose contributions (e.g. clutch serving run, key middle touches) changed the match momentum."
    )


@mcp.prompt()
def datavolley_export(
    match_id: Annotated[
        str,
        "Unique Hudl match ID or video hex ID",
    ],
    set_number: Annotated[
        Optional[int],
        "Optional set number to export (1-5). If omitted, exports all available touches.",
    ] = None,
) -> str:
    """Generate standardized DataVolley (.dvw) scouting codes for match touches.

    Translates tagged match actions into standard DataVolley syntax:
    [Team (* or a)][Jersey (2 digits)][Skill (S/R/E/A/B/D)][Evaluation (#/+/!/-/=)][Zones/Combo].
    """
    set_clause = f", set_number={set_number}" if set_number is not None else ""
    return (
        f"You are an accredited DataVolley Scout transforming Hudl/Balltime touch data for match '{match_id}' into standard .dvw code format.\n\n"
        "Follow these steps:\n"
        f"1. **Retrieve Match Touches**: Call `get_game_actions(match_id='{match_id}'{set_clause}, output_format='compact', limit=100)`.\n"
        "2. **Format DataVolley Codes** using standard OpenVolley conventions:\n"
        "   - **Team**: `*` for Home team / Team A, `a` for Away team / Team B.\n"
        "   - **Jersey**: 2 digits (e.g., `07`, `17`, `20`). If unknown, use `00`.\n"
        "   - **Skill Codes**: `S` (Serve), `R` (Receive), `E` (Set), `A` (Attack), `B` (Block), `D` (Dig), `F` (Freeball).\n"
        "   - **Evaluation Codes**: `#` (Perfect / Kill / Ace), `+` (Positive), `!` (Medium), `-` (Poor / Negative), `=` (Error).\n"
        "3. **Present Output**: Provide a clean DataVolley event table and a raw text block of `.dvw` scouting strings ready for copy-pasting into DataVolley or OpenVolley tools."
    )


@mcp.prompt()
def serve_receive_audit(
    match_id: Annotated[
        str,
        "Unique Hudl match ID or video hex ID to audit",
    ],
) -> str:
    """Conduct a comprehensive serve-receive and passing performance audit.

    Analyzes 3-point pass percentages, reception errors, setter in-system rates,
    and identifies opponent serving pressure points.
    """
    return (
        f"You are a Volleyball Passing & Receiving Specialist auditing serve-receive performance for match '{match_id}'.\n\n"
        "Follow these steps:\n"
        f"1. **Fetch Receptions & Serves**: Call `get_game_actions(match_id='{match_id}', action_type='receive', limit=100)` and "
        f"`get_game_actions(match_id='{match_id}', action_type='serve', limit=100)`.\n"
        "2. **Calculate Passer Efficiency Ratings**:\n"
        "   - Perfect Pass (# / 3-pass): In-system ball enabling middle quick or slide.\n"
        "   - Positive Pass (+ / 2-pass): Good pass enabling pin attack options.\n"
        "   - Medium Pass (! / 1-pass): Out-of-system emergency set.\n"
        "   - Reception Error (= / 0-pass): Direct ace conceded.\n"
        "   - Overall Rating Formula: `(3 * perfect + 2 * positive + 1 * medium) / total_receptions` (Target: > 2.00).\n"
        "3. **Diagnose Opponent Service Pressure**:\n"
        "   - Identify which opponent servers caused the most reception errors or poor passes.\n"
        "   - Analyze target areas (Zone 1, Zone 5, Zone 6, or seam between passers).\n"
        "4. **Deliver Coaching Adjustments**:\n"
        "   - Specific passing lineup adjustments (e.g. shift receive seam left/right, pinch libero).\n"
        "   - First-contact focus areas for next practice session."
    )


def main() -> None:
    """Run the FastMCP server via standard IO transport."""
    mcp.run()


if __name__ == "__main__":
    main()
