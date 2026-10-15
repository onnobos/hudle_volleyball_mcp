"""Hudl Volleyball MCP Server package.

A Model Context Protocol server connecting AI assistants to Hudl's internal GraphQL API
for volleyball match, player, and rotation analytics.
"""

from hudl_mcp.client import (
    HudlAuthError,
    HudlClient,
    HudlConnectionError,
    HudlError,
    HudlGraphQLError,
    execute_graphql,
    get_balltime_token,
)
from hudl_mcp.models import (
    MatchSummary,
    PlayerStats,
    RotationStats,
    VolleyballAction,
    format_actions_markdown,
    format_matches_markdown,
    format_player_stats_markdown,
    format_rotation_stats_markdown,
    parse_video_actions,
)
def __getattr__(name: str):
    if name == "mcp":
        from hudl_mcp.server import mcp
        return mcp
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__version__ = "0.1.0"
__all__ = [
    "mcp",
    "HudlClient",
    "execute_graphql",
    "get_balltime_token",
    "HudlError",
    "HudlAuthError",
    "HudlGraphQLError",
    "HudlConnectionError",
    "MatchSummary",
    "PlayerStats",
    "RotationStats",
    "VolleyballAction",
    "format_matches_markdown",
    "format_player_stats_markdown",
    "format_rotation_stats_markdown",
    "format_actions_markdown",
    "parse_video_actions",
]
