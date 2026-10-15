# 🏐 Hudl Volleyball MCP Server (`hudl-volleyball-mcp`)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-1.3+-green.svg)](https://modelcontextprotocol.io/)
[![Build System Hatchling](https://img.shields.io/badge/build-hatchling-purple.svg)](https://hatch.pypa.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Strict Read-Only](https://img.shields.io/badge/Security-Strict%20Read--Only-brightgreen.svg)]()
[![DataVolley Compatible](https://img.shields.io/badge/OpenVolley-DataVolley%20.dvw-orange.svg)]()

A 5/5 production-grade [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that connects AI clients (**Claude Desktop**, **Cursor**, **Antigravity**, or custom LLM agents) to Hudl and Balltime volleyball analytics.

Transform your AI into a Staff Volleyball Performance Analyst capable of scouting opponents, diagnosing rotation breakdowns (P1–P6), analyzing serve-receive stability, generating box scores, and exporting event-by-event touches directly to **DataVolley (`.dvw`)** and **Pandas**.

---

> [!IMPORTANT]
> ### ⚖️ Legal Disclaimer
> This is an **independent, open-source community project** and is **not affiliated with, maintained by, authorized by, or endorsed by Hudl, Agile Sports Technologies, Volleymetrics, or Balltime**.
>
> All product and company names are trademarks™ or registered® trademarks of their respective holders. Use of them does not imply any affiliation with or endorsement by them. This integration operates under a strict, client-side, read-only policy to access data belonging to your authenticated team account.

---

## 🌟 Why Coaches & Analysts Love This Server

- 🛡️ **Zero Password Storage**: Interactive browser login (`login_to_hudl`) lets you log in via 1Password, Bitwarden, Apple/Google SSO, or 2FA. Your password is never stored or seen by the AI or environment files.
- 📦 **1-Click `.mcpb` Installation**: Distribute a single double-clickable `.mcpb` bundle that non-technical coaches can install into Claude Desktop without touching a terminal.
- ⚡ **Zero-Setup `uvx`**: Run instantly via `uvx mcp-hudl-volleyball` without manually managing virtual environments or dependencies.
- 🪟 **Context-Window Optimized**: Strips bloated API metadata and UI JSON dumps. Tools return either clean Markdown tables or token-efficient compact dictionaries (`output_format="markdown"` or `"compact"`).
- 🛡️ **Defensive Networking & Account Protection**:
  - **Strict Read-Only**: Enforces zero mutation policy; any mutating request is immediately blocked before transmission.
  - **Rate Limiting**: Built-in 2 requests/second token bucket rate limiter with jittered exponential backoff on HTTP 429/5xx.
  - **Multi-Tier Disk Caching**: 7-day persistent cache for match box scores and play-by-play touches; 15-minute cache for schedules and team rosters.
- 🏐 **Volleyball Domain Semantics**: Native support for Rotations P1 through P6, setter distribution, First-Ball Sideout (FBSO), and **DataVolley `.dvw` skill codes** (`S`, `R`, `E`, `A`, `B`, `D`, `F`) and evaluation codes (`#`, `+`, `!`, `-`, `=`).
- 🤖 **5 Built-In FastMCP Prompts (`@mcp.prompt`)**: Pre-packaged, professional coaching workflows for opponent scouting, rotation diagnostics, MVP evaluation, DataVolley export, and serve-receive audits.

---

## 🚀 Quick Start & Installation

### Option 1: 1-Click MCP Bundle (`.mcpb`) for Claude Desktop *(Recommended for Coaches)*

No terminal or programming required!

1. Download the latest `hudl-volleyball-mcp.mcpb` bundle from the GitHub Releases page.
2. Double-click the file, or open **Claude Desktop** > **Settings** > **Extensions** > **Install Extension** and select `hudl-volleyball-mcp.mcpb`.
3. In Claude Desktop chat, simply say: **`"Log me into Hudl"`**. A browser window opens to let you log in securely.

*(Developers: To build the `.mcpb` bundle yourself, run `npx @anthropic-ai/mcpb pack` in the project root).*

---

### Option 2: Zero-Setup `uvx` *(Recommended for Cursor & Terminal Users)*

Requires Astral's ultra-fast [`uv`](https://github.com/astral-sh/uv). No virtual environment activation needed.

#### Claude Desktop Configuration
Add this to your `claude_desktop_config.json`:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "hudl-volleyball": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/onnobos/hudle_volleyball_mcp.git",
        "mcp-hudl-volleyball"
      ]
    }
  }
}
```

#### Cursor IDE Configuration
In Cursor, open **Settings** > **Features** > **MCP Servers** > **Add New MCP Server** (or edit `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "hudl-volleyball": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/onnobos/hudle_volleyball_mcp.git",
        "mcp-hudl-volleyball"
      ]
    }
  }
}
```

---

### Option 3: Local Development Installation

```bash
# 1. Clone the repository
git clone https://github.com/onnobos/hudle_volleyball_mcp.git
cd hudl_mcp

# 2. Create and activate virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install in editable mode with hatchling
pip install -e .

# 4. Install Playwright Chromium browser for interactive login
playwright install chromium
```

---

## 🔐 Frictionless Authentication & Auto-Refresh

We believe coaches should never have to paste sensitive passwords into plain text files.

### Interactive Pop-Up Browser Login (Zero Credential Storage)
1. In your AI chat, say: **`"Log me into Hudl"`** (or trigger the `login_to_hudl` tool).
2. A visible Chromium browser pops up to `https://www.hudl.com/login`.
3. Log in with your password manager (1Password, Bitwarden, iCloud Keychain), Apple/Google SSO, or 2FA.
4. As soon as you reach `hudl.com/home`, session tokens are automatically saved to your OS Keyring and `~/.hudl_mcp/auth_state.json`. The browser closes automatically.
5. You stay logged in for weeks without touching credentials again.

### Automatic 401 Re-Authentication
If your session ever expires while running queries, the server automatically attempts to refresh the session token, clears stale caches, and retries the request without failing your prompt.

---

## 🛠️ Available MCP Tools

| Tool Name | Parameters | Description |
|:---|:---|:---|
| **`get_user_teams`** | `output_format`, `force_refresh` | Automatically discovers all teams on your Hudl account with team IDs, club/school names, and coach roles. |
| **`list_volleyball_matches`** | `team_id`, `limit`, `output_format`, `force_refresh` | Lists recent volleyball matches with match IDs, dates, opponents, and set scores. |
| **`get_match_player_stats`** | `match_id`, `team_id`, `output_format`, `force_refresh` | Retrieves official player box scores: Kills, Errors, Total Attacks, Hitting %, Assists, Aces, Digs, Blocks, and Points. |
| **`get_rotation_breakdown`** | `match_id`, `team_id`, `output_format`, `force_refresh` | Analyzes rotations **P1 through P6**: sideout %, point-scoring %, first-ball sideout (FBSO), and setter distribution tendencies. |
| **`get_game_actions`** | `match_id`, `set_number`, `action_type`, `player`, `team`, `quality`, `limit`, `offset`, `output_format`, `force_refresh` | Retrieves event-by-event volleyball touches with video timestamps, start/dest zones, routes, blockers, and **DataVolley `.dvw` skill/eval codes**. |
| **`login_to_hudl`** | `timeout_seconds` | Opens interactive browser window to log in safely via password manager or SSO. |
| **`refresh_hudl_cookie`** | — | Refreshes session authentication tokens and resets cache. |

> **Format Tip**: All data tools accept `output_format="markdown"` (clean human-readable tables) or `output_format="compact"` (token-efficient minified JSON for large analytics queries).

---

## 🧠 FastMCP Coaching Prompts (`@mcp.prompt`)

The server exposes 5 built-in workflows that structure complex multi-step volleyball analysis:

1. **`scout_opponent(opponent_name)`**:
   Searches matches, calculates offensive kill distributions, isolates weak sideout rotations, evaluates passer stability, and outputs a complete tactical game plan.
2. **`analyze_rotation_weaknesses(match_id)`**:
   Audits P1–P6 sideout efficiencies, detects unforced errors vs blocked attacks, assesses predictable setter choices, and suggests rotational adjustments.
3. **`match_mvp_breakdown(match_id)`**:
   Evaluates True Points, hitting efficiency, clutch performance in late-set situations (set score 20+), and selects Match MVP, Offensive Player, Defensive Anchor, and Unsung Hero.
4. **`datavolley_export(match_id, set_number)`**:
   Converts all video touches into standard DataVolley `.dvw` format strings ready for import into scouting software.
5. **`serve_receive_audit(match_id)`**:
   Calculates passer ratings `(3 * perfect + 2 * positive + 1 * medium) / total`, setter in-system rates, and opponent serving heatmaps.

---

## 📊 OpenVolley & Pandas Compatibility

### OpenVolley / DataVolley (`.dvw`) Syntax
All match touches retrieved via `get_game_actions` include DataVolley `.dvw` standard codes:
```
[Team (* or a)][Jersey (2 digits)][Skill (S/R/E/A/B/D)][Evaluation (#/+/!/-/=)][Zones/Combo]
```
- **Skills**: `S` (Serve), `R` (Receive), `E` (Set), `A` (Attack), `B` (Block), `D` (Dig), `F` (Freeball)
- **Evaluations**: `#` (Perfect / Kill / Ace), `+` (Positive), `!` (Medium), `-` (Poor / Negative), `=` (Error)

### Python `pandas` Integration
Pass `output_format="compact"` to load match actions or player statistics directly into a Pandas DataFrame:

```python
import json
import pandas as pd
from hudl_mcp.server import get_game_actions

# Retrieve touches in compact JSON format
raw_json = await get_game_actions(match_id="your-match-id", output_format="compact", limit=200)
df = pd.DataFrame(json.loads(raw_json))

# Filter in-system attack kills
kills = df[(df["action"] == "attack") & (df["quality"] == "kill")]
print(f"Total Kills: {len(kills)}, Pipe Kills: {len(kills[kills['route'] == 'pipe'])}")
```

---

## 📋 5 Ready-to-Use Volleyball Scouting Prompts

Copy and paste these directly into Claude Desktop or Cursor:

### 1. Opponent Pre-Match Scouting Report
> *"We play Voléro this weekend. Run the `scout_opponent` prompt for 'Voléro'. Find our last match against them, break down their top outside hitter's hitting percentage, identify their weakest sideout rotation, and recommend our serving targets."*

### 2. Rotation Diagnostic & Sideout Droughts
> *"Analyze our rotation weaknesses for match `LUTRY`. Which rotation had the lowest sideout percentage? Were the lost points caused by direct reception errors or blocked attacks? Recommend adjustments for our serve-receive formation."*

### 3. Match MVP & Clutch Performance Breakdown
> *"Run the `match_mvp_breakdown` workflow for match `123456`. Calculate True Points and net point differential for each player. Who scored the most clutch kills after 20 points in Set 3? Name the Match MVP and Defensive Player of the Match."*

### 4. Serve-Receive & Passer Stability Audit
> *"Perform a serve-receive audit on our last match. Calculate the 3-point passing efficiency rating for each passer: `(3*perfect + 2*positive + 1*medium) / attempts`. Which rotation conceded the most aces?"*

### 5. DataVolley Touch Export for Setter Distribution
> *"Export all attacks and sets from Set 2 of match `LUTRY` into DataVolley `.dvw` format. Group setter distribution by pass quality (in-system vs out-of-system) and show attack kill rates from Zone 4, Zone 3, Zone 2, and the pipe."*

---

## 🔒 Security & Strict Read-Only Policy

This server is designed for elite athletic programs that prioritize data security:
- **No Mutations**: Operates exclusively in **READ-ONLY** mode. All GraphQL mutation keywords are intercepted and rejected with `HudlSecurityError`. It cannot alter rosters, delete videos, or overwrite match data.
- **Credential Isolation**: Tokens are stored in OS Keyring or local user cache (`~/.hudl_mcp/`). No passwords are committed to git or exposed to LLM context.
- **WAF & Rate-Limit Shield**: Token-bucket rate limiting (2 req/s) prevents aggressive LLM tool loops from triggering IP bans or rate limits.

---

## 🧪 Testing

Run the comprehensive unit test suite:

```bash
# Run all tests
pytest tests/ -v

# Run connection diagnostics against your live account
hudl-test
```

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for details.
