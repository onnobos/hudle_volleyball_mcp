"""GraphQL Queries for Hudl Volleyball MCP.

HOW TO UPDATE THESE QUERIES USING CHROME DEVTOOLS:
===================================================
1. Open Google Chrome and log in to https://www.hudl.com
2. Navigate to your volleyball team page (e.g. Matches, Box Score, or Reports).
3. Open Chrome Developer Tools:
   - Windows/Linux: Press F12 or Ctrl+Shift+I
   - macOS: Press Cmd+Option+I
4. Select the "Network" tab.
5. In the filter box at the top, type: `graphql` (or filter by `Fetch/XHR`).
6. Click on a match or stats page to trigger network requests.
7. Click on any `graphql` request in the list:
   - Go to the "Payload" tab.
   - Click "View source" or inspect the `query` field.
   - Copy the exact query string.
8. Paste the copied query string into the corresponding query constant below.
   Ensure the variable names ($teamId, $matchId, $limit) match or adjust them
   accordingly.
"""

# ==============================================================================
# 1. RECENT MATCHES QUERY
# ==============================================================================
# Fetches match IDs, dates, opponents, and scores for a specific team.
# Variables expected:
#   - teamId: ID! (or String)
#   - limit: Int (optional, default 10)
# ==============================================================================
GET_RECENT_MATCHES_QUERY = """
query GetRecentMatches($teamId: ID!, $limit: Int = 10) {
  team(id: $teamId) {
    id
    name
    matches(first: $limit) {
      edges {
        node {
          id
          date
          scheduledTime
          status
          result {
            outcome
            score
            setScores
          }
          homeAway
          opponent {
            id
            name
            shortName
          }
          season {
            id
            name
          }
        }
      }
      # Flat list fallback if schema does not use Relay edges
      items {
        id
        date
        scheduledTime
        status
        result {
          outcome
          score
          setScores
        }
        homeAway
        opponent {
          id
          name
        }
      }
    }
  }
}
"""


# ==============================================================================
# 2. MATCH PLAYER STATS / BOX SCORE QUERY
# ==============================================================================
# Fetches individual athlete statistics for a volleyball match:
# - Attacking: kills, attack errors, total attacks (attempts), hitting percentage
# - Setting: assists, ball handling errors
# - Serving: aces, service errors, total serves
# - Defense / Passing: digs, pass rating, reception errors
# - Blocking: block solos, block assists, total blocks, block errors
#
# Variables expected:
#   - matchId: ID!
#   - teamId: ID (optional, to filter to team)
# ==============================================================================
GET_MATCH_PLAYER_STATS_QUERY = """
query GetMatchPlayerStats($matchId: ID!, $teamId: ID) {
  match(id: $matchId) {
    id
    date
    opponent {
      id
      name
    }
    volleyballStats(teamId: $teamId) {
      teamId
      teamName
      setsPlayed
      athleteStats {
        athlete {
          id
          name
          jerseyNumber
          position
        }
        stats {
          setsPlayed
          # Attack
          kills
          attackErrors
          totalAttacks
          hittingPercentage
          # Setting
          assists
          ballHandlingErrors
          # Serving
          serviceAces
          serviceErrors
          totalServes
          # Defense & Reception
          digs
          passRating
          receptionErrors
          # Blocking
          blockSolos
          blockAssists
          totalBlocks
          blockingErrors
          # Overall
          points
        }
      }
    }
  }
}
"""


# ==============================================================================
# 3. ROTATION BREAKDOWN & SETTER TENDENCIES QUERY
# ==============================================================================
# Fetches rotation efficiency (P1 through P6):
# - Sideout percentage (Sideouts / Receiving Attempts)
# - Point scoring percentage (Points / Serving Attempts)
# - First-ball sideout (FBSO) percentage
# - Setter distribution / tendencies by rotation
#
# Variables expected:
#   - matchId: ID!
#   - teamId: ID (optional)
# ==============================================================================
GET_ROTATION_STATS_QUERY = """
query GetRotationStats($matchId: ID!, $teamId: ID) {
  match(id: $matchId) {
    id
    date
    rotationBreakdown(teamId: $teamId) {
      rotations {
        rotationNumber
        rotationName
        sideoutPercentage
        sideoutsEarned
        sideoutAttempts
        pointScoringPercentage
        pointsScoredServing
        serveAttempts
        firstBallSideoutRate
        setterTendencies {
          leftSidePercent
          middlePercent
          rightSidePercent
          backRowPercent
          setterDumpPercent
        }
        notes
      }
    }
  }
}
"""
