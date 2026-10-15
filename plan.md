You are an expert Python developer. Build a complete, production-ready Model Context Protocol (MCP) server in Python called "hudl-volleyball-mcp" that connects an AI client (such as Claude Desktop or Cursor) to Hudl's internal GraphQL API (https://www.hudl.com/api/graphql) to retrieve and analyze volleyball statistics.

1. SYSTEM ARCHITECTURE & TECH STACK
- Language: Python 3.11+
- MCP Framework: FastMCP (using the official mcp Python SDK)
- HTTP Client: httpx (async client with timeout and header management)
- Data Parsing: pydantic (v2)
- Environment Management: python-dotenv
- Auth Automation (Optional fallback): playwright (headless browser to refresh expired cookies)

2. TARGET FILE STRUCTURE
Create the following project files:
- pyproject.toml (or requirements.txt)
- .env.example
- src/hudl_mcp/__init__.py
- src/hudl_mcp/server.py (FastMCP server instance and tool definitions)
- src/hudl_mcp/client.py (Async HTTPX GraphQL wrapper and cookie authentication)
- src/hudl_mcp/queries.py (Isolated GraphQL query strings for easy updating)
- src/hudl_mcp/models.py (Pydantic models to clean raw JSON into compact analytical data)
- src/hudl_mcp/auth_refresh.py (Playwright script to log into hudl.com and update the cookie)
- README.md (Setup instructions and Claude/Cursor MCP config JSON)

3. AUTHENTICATION & CLIENT LOGIC (client.py)
- Load HUDL_COOKIE, HUDL_TEAM_ID, HUDL_EMAIL, and HUDL_PASSWORD from the .env file.
- Because Hudl has no public API, authenticate requests to https://www.hudl.com/api/graphql by passing HUDL_COOKIE inside the "Cookie" HTTP header.
- Include realistic browser headers: User-Agent, Origin ("https://www.hudl.com"), Referer ("https://www.hudl.com/home"), and Content-Type ("application/json").
- Create an async function execute_graphql(query: str, variables: dict) that sends POST requests, checks for 401/403 status codes or GraphQL UNAUTHENTICATED errors, and returns a clear error message telling the AI if the session cookie needs to be refreshed.

4. GRAPHQL QUERIES (queries.py)
Create placeholder GraphQL query strings with clear comments showing where I can paste my exact query payloads from Chrome DevTools Network tab:
- GET_RECENT_MATCHES_QUERY: Fetches match IDs, dates, and opponent names for a team.
- GET_MATCH_PLAYER_STATS_QUERY: Fetches individual player stats (kills, attack errors, total attacks, hitting percentage, aces, serve errors, digs, blocks, pass rating).
- GET_ROTATION_STATS_QUERY: Fetches sideout percentage, point-scoring percentage, and setter tendencies across Rotations 1 to 6.

5. MCP TOOLS TO EXPOSE (server.py)
Expose these @mcp.tool() functions with clear docstrings so the LLM knows when to call them:
- list_volleyball_matches(team_id: Optional[str] = None, limit: int = 10) -> str
  Fetches recent matches so the AI can find the right match_id from natural language requests.
- get_match_player_stats(match_id: str, team_id: Optional[str] = None) -> str
  Fetches athlete box scores, strips out unnecessary UI metadata, calculates Hitting % ((Kills - Errors) / Attempts) if missing, and returns a clean Markdown table or compact JSON.
- get_rotation_breakdown(match_id: str, team_id: Optional[str] = None) -> str
  Fetches performance by rotation (P1 through P6) including sideout efficiency and first-ball sideout rates.
- refresh_hudl_cookie() -> str
  Runs auth_refresh.py using headless Playwright to log into https://www.hudl.com/login with HUDL_EMAIL and HUDL_PASSWORD, extracts the new "ident" session cookie, updates the .env file and active memory, and returns a success confirmation.

6. DELIVERABLES
Please generate the full code for every file listed in the target file structure so I can copy and run the project immediately.