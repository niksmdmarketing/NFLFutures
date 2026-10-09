const $ = id => document.getElementById(id);
const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));

const viewLabels = {
  leaders: "Player leaders",
  teams: "Team season stats",
  games: "Games & schedule",
  boxscores: "Player game logs",
  standings: "Standings",
  players: "Roster lookup"
};
const preferredViews = ["leaders", "teams", "boxscores", "games", "standings", "players"];
const viewStats = {
  leaders: ["Phase", "Player", "Team", "Position", "GP", "GS", "MPG", "PPG", "RPG", "APG", "SPG", "BPG", "TOV/G", "FG%", "3P%", "FT%", "eFG%", "TS%", "AST/TOV"],
  teams: ["Phase", "Team", "Team code", "GP", "Wins", "Losses", "PPG", "Opponent PPG", "Point diff", "Pace", "OffRtg", "DefRtg", "NetRtg", "eFG%", "TS%", "3P rate", "FT rate", "RPG", "APG", "TOV/G"],
  standings: ["Phase", "Team", "Team code", "Position", "Wins", "Losses", "GP", "Win %", "Points for", "Points against", "Last 5"],
  games: ["Phase", "Date", "Round", "Matchup", "Score", "Status", "Venue"],
  players: ["Phase", "Player", "Team", "Position", "Jersey", "Height", "Weight", "Nationality"],
  boxscores: ["Phase", "Date", "Round", "Matchup", "Player", "Team", "MIN", "PTS", "REB", "OREB", "DREB", "AST", "STL", "BLK", "TOV", "FGM", "FGA", "FG%", "3PM", "3PA", "3P%", "FTM", "FTA", "FT%", "+/-"]
};
const statGroups = {
  leaders: {
    production: ["Phase", "Player", "Team", "Position", "GP", "GS", "MPG", "PPG", "RPG", "APG", "SPG", "BPG", "TOV/G", "AST/TOV"],
    shooting: ["Phase", "Player", "Team", "GP", "FG%", "3P%", "FT%", "eFG%", "TS%"]
  },
  teams: {
    summary: ["Phase", "Team", "GP", "Wins", "Losses", "Win %", "PPG", "Opponent PPG", "Point diff"],
    efficiency: ["Phase", "Team", "Pace", "OffRtg", "DefRtg", "NetRtg", "eFG%", "TS%", "3P rate", "FT rate"],
    boxscore: ["Phase", "Team", "GP", "RPG", "APG", "TOV/G"]
  },
  boxscores: {
    production: ["Phase", "Date", "Round", "Matchup", "Player", "Team", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "+/-"],
    shooting: ["Phase", "Date", "Matchup", "Player", "Team", "FGM", "FGA", "FG%", "3PM", "3PA", "3P%", "FTM", "FTA", "FT%"],
    rebounding: ["Phase", "Date", "Matchup", "Player", "Team", "REB", "OREB", "DREB", "STL", "BLK", "+/-"]
  }
};
function columnGroup(key, view) {
  const field = (key + " " + labelFor(key)).toLowerCase();
  if (view === "leaders") return /(?:field.goal|three.point|free.throw|shoot|fgm|fga|3pm|3pa|ftm|fta|efg|ts%|percentage)/i.test(field) ? "shooting" : "production";
  if (view === "teams") {
    if (/(?:rating|efficien|percentage|rate|pace|possession)/i.test(field)) return "efficiency";
    if (/(?:rebound|assist|turnover|block|steal|foul|\+\/|-)/i.test(field)) return "boxscore";
    return "summary";
  }
  if (view === "boxscores") {
    if (/(?:field.goal|three.point|free.throw|shoot|fgm|fga|3pm|3pa|ftm|fta|percentage)/i.test(field)) return "shooting";
    if (/(?:rebound|block|steal|defen|offen|plus.minus|\+\/|-)/i.test(field)) return "rebounding";
    return "production";
  }
  return "production";
}
const groupLabels = {production:"Production", shooting:"Shooting", summary:"Summary", efficiency:"Efficiency", boxscore:"Rebounding & playmaking", rebounding:"Rebounding & defense"};
const fieldLabels = {
  "Player": "Player", "Team": "Team", "Team code": "Team code", "Position": "Position",
  "Phase": "Season phase", "phase": "Season phase",
  "GP": "GP", "GS": "GS", "MPG": "MPG", "PPG": "PPG", "RPG": "RPG", "APG": "APG",
  "SPG": "SPG", "BPG": "BPG", "TOV/G": "TOV/G", "FG%": "FG%", "3P%": "3P%", "FT%": "FT%",
  "eFG%": "eFG%", "TS%": "TS%", "AST/TOV": "AST/TOV", "Opponent PPG": "Opponent PPG",
  "Point diff": "Point diff", "Pace": "Pace", "OffRtg": "OffRtg", "DefRtg": "DefRtg",
  "NetRtg": "NetRtg", "3P rate": "3P rate", "FT rate": "FT rate",
  "Wins": "Wins", "Losses": "Losses", "Win %": "Win %", "Points for": "Points for",
  "Points against": "Points against", "Last 5": "Last 5", "Date": "Date", "Round": "Round",
  "Matchup": "Matchup", "Score": "Score", "Status": "Status", "Venue": "Venue", "Jersey": "Jersey",
  "Height": "Height", "Weight": "Weight", "Nationality": "Nationality",
  "MIN": "MIN", "PTS": "PTS", "REB": "REB", "OREB": "OREB", "DREB": "DREB", "AST": "AST", "STL": "STL", "BLK": "BLK", "TOV": "TOV", "FGM": "FGM", "FGA": "FGA", "3PM": "3PM", "3PA": "3PA", "FTM": "FTM", "FTA": "FTA", "+/-": "+/-",
  "team_code": "Team code", "played": "GP", "won": "Wins", "lost": "Losses",
  "points_average": "PPG", "points_against_average": "Opponent PPG", "points_allowed_average": "Opponent PPG",
  "point_diff_average": "Point diff", "pace": "Pace", "offensive_rating": "OffRtg",
  "defensive_rating": "DefRtg", "net_rating": "NetRtg", "effective_field_goal_percentage": "eFG%",
  "true_shooting_percentage": "TS%", "three_point_rate": "3P rate", "free_throw_rate": "FT rate",
  "opponent_points_average": "Opponent PPG", "points_diff_average": "Point diff",
  "offensive_efficiency": "OffRtg", "defensive_efficiency": "DefRtg", "net_efficiency": "NetRtg",
  "efg_percentage": "eFG%", "ts_percentage": "TS%", "tov_average": "TOV/G",
  "three_pointers_attempted_rate": "3P rate", "free_throws_attempted_rate": "FT rate",
  "player · first_name": "First name", "player · last_name": "Last name",
  "player · display_name": "Player", "player · full_name": "Player",
  "player · name": "Player", "team · name": "Team", "team · team_name": "Team",
  "team · team_code": "Team code", "team · team_nickname": "Team nickname",
  "points_average": "PPG", "points_per_game": "PPG", "rebounds_average": "RPG",
  "rebounds_per_game": "RPG", "assists_average": "APG", "assists_per_game": "APG",
  "steals_average": "SPG", "blocks_average": "BPG", "turnovers_average": "TOV/G",
  "minutes_average": "MPG", "fouls_average": "PF/G", "personal_fouls_average": "PF/G",
  "games_played": "GP", "games_started": "GS", "games_started_avg": "GS", "minutes_played_per_game_avg": "MPG",
  "field_goal_avg": "FGM/G", "field_goal_attempt_avg": "FGA/G", "fg_per_avg": "FG%",
  "3pfg_avg": "3PM/G", "3pfga_avg": "3PA/G", "3pfg_per_avg": "3P%",
  "ft_avg": "FTM/G", "fta_avg": "FTA/G", "ft_per_avg": "FT%",
  "trb_avg": "RPG", "ast_avg": "APG", "stl_avg": "SPG", "blk_avg": "BPG", "tov_avg": "TOV/G",
  "field_goals_made_average": "FGM/G", "field_goals_attempted_average": "FGA/G",
  "field_goals_percentage": "FG%", "field_goal_percentage": "FG%", "fg_percentage": "FG%",
  "three_pointers_made_average": "3PM/G", "three_pointers_attempted_average": "3PA/G",
  "three_pointers_percentage": "3P%", "three_point_percentage": "3P%", "free_throws_made_average": "FTM/G",
  "free_throws_attempted_average": "FTA/G", "free_throws_percentage": "FT%",
  "position": "Position", "playing_position": "Position", "jersey_number": "Jersey",
  "points_for": "Points for", "points_against": "Points against",
  "points_percentage": "Points ratio", "win_percentage": "Win %",
  "won": "Wins", "lost": "Losses", "played": "GP", "last_5": "Last 5",
  "home_wins": "Home wins", "home_losses": "Home losses",
  "away_wins": "Away wins", "away_losses": "Away losses",
  "match_status": "Status", "match_date": "Date", "scheduled_start": "Date",
  "start_time": "Start time", "home_score": "Home score", "away_score": "Away score",
  "home_team_score": "Home score", "away_team_score": "Away score",
  "home_team_name": "Home team", "away_team_name": "Away team",
  "home_team · name": "Home team", "away_team · name": "Away team",
  "home_team · team_code": "Home code", "away_team · team_code": "Away code",
  "match_round": "Round", "round_number": "Round", "venue_name": "Venue", "venue": "Venue",
  "home_team · team_name": "Home team", "away_team · team_name": "Away team",
  "home_team · display_name": "Home team", "away_team · display_name": "Away team",
  "home_team · team_nickname": "Home team", "away_team · team_nickname": "Away team",
  "home_team_score": "Home score", "away_team_score": "Away score",
  "home_score": "Home score", "away_score": "Away score",
  "player · jersey_number": "Jersey", "player · position": "Position",
  "player · playing_position": "Position", "player · height": "Height", "player · weight": "Weight",
  "player · nationality": "Nationality", "player · country": "Nationality",
  "nationality": "Nationality", "country": "Nationality", "height": "Height", "weight": "Weight"
};
const hiddenField = key => {
  const parts = key.toLowerCase().split(" · ");
  if (parts[0] === "season" || parts.includes("competition")) return true;
  return parts.some(part => /(^|_)(id|uuid|external_id)$/.test(part)
    || /(^|_)(logo|logo_transparent|ticket_url|blurhash|color_primary|color_secondary|color_tertiary)$/.test(part)
    || /(^|_)(image|photo|avatar|url|uri)$/.test(part)
    || part.includes("odds") || part.includes("external") || part.includes("color")
    || part.includes("blurhash") || part.includes("ticket")
    || (part === "name" && parts.length > 1 && !["team", "home_team", "away_team", "player"].includes(parts.at(-2))));
};

function flatten(value, prefix = "", out = {}) {
  if (value == null) return out;
  if (Array.isArray(value)) {
    out[prefix] = value.map(item => typeof item === "object" ? JSON.stringify(item) : item).join(", ");
    return out;
  }
  if (typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      const path = prefix ? prefix + " · " + key : key;
      if (hiddenField(path)) continue;
      if (child && typeof child === "object" && !Array.isArray(child)) flatten(child, path, out);
      else if (Array.isArray(child)) out[path] = child.map(item => typeof item === "object"
        ? Object.values(item).filter(part => typeof part !== "object").join(" ") : item).join(", ");
      else out[path] = child;
    }
    return out;
  }
  out[prefix] = value;
  return out;
}

function friendlyRows(records, view = "") {
  return records.map(record => {
    const row = flatten(record);
    const first = row["player · first_name"] || row.first_name || "";
    const last = row["player · last_name"] || row.last_name || "";
    const fullName = row["player · display_name"] || row["player · full_name"] || row["player · name"]
      || row.player_name || [first, last].filter(Boolean).join(" ");
    if (fullName) row.Player = fullName;
    delete row["player · first_name"];
    delete row["player · last_name"];
    delete row.first_name;
    delete row.last_name;
    for (const key of ["player · display_name", "player · full_name", "player · name", "player_name"]) delete row[key];
    if (row["team · name"]) row.Team = row["team · name"];
    else if (row["team · team_name"]) row.Team = row["team · team_name"];
    if (row["team · team_code"] || row.team_code) row["Team code"] = row["team · team_code"] || row.team_code;
    else if (row.abbreviation) row["Team code"] = row.abbreviation;
    if (!row.Team && row.name && row["Team code"]) row.Team = row.name;
    for (const key of ["team · name", "team · team_name", "team · team_code", "team · team_nickname", "team_code", "abbreviation", "season · year", "season · season_type"]) delete row[key];
    if (row.name && row.Team) delete row.name;
    if (view === "leaders") {
      const pick = (...keys) => keys.map(key => row[key]).find(value => value != null && value !== "");
      const number = value => value == null || value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
      const stat = (...keys) => number(pick(...keys));
      const gp = stat("games", "games_played", "played", "GP");
      const gs = stat("games_started", "games_started_avg", "games_started_total", "GS");
      const mpg = stat("minutes_average", "minutes_per_game", "MPG", "minutes_played_per_game_avg");
      const ppg = stat("points_average", "points_per_game", "PPG", "points_average_per_game", "pts_avg");
      const rpg = stat("rebounds_average", "rebounds_per_game", "RPG", "total_rebounds_average", "trb_avg");
      const apg = stat("assists_average", "assists_per_game", "APG", "ast_avg");
      const spg = stat("steals_average", "steals_per_game", "SPG", "stl_avg");
      const bpg = stat("blocks_average", "blocks_per_game", "BPG", "blk_avg");
      const tov = stat("turnovers_average", "turnovers_per_game", "TOV/G", "tov_avg");
      const fgm = stat("field_goals_made_average", "field_goals_made_per_game", "field_goal_avg", "FGM/G", "field_goals_made");
      const fga = stat("field_goals_attempted_average", "field_goals_attempted_per_game", "field_goal_attempt_avg", "FGA/G", "field_goals_attempted");
      const tpm = stat("three_pointers_made_average", "three_pointers_made_per_game", "3PM/G", "3pfg_avg", "three_pointers_made");
      const fta = stat("free_throws_attempted_average", "free_throws_attempted_per_game", "FTA/G", "fta_avg", "free_throws_attempted");
      const fgPct = stat("field_goals_percentage", "field_goal_percentage", "fg_percentage", "FG%", "fg_per_avg")
        ?? (fgm != null && fga > 0 ? fgm / fga * 100 : null);
      const threePct = stat("three_pointers_percentage", "three_point_percentage", "three_point_field_goal_percentage", "3P%", "3pfg_per_avg")
        ?? (tpm != null && stat("three_pointers_attempted_average", "three_pointers_attempted_per_game", "3PA/G", "3pfga_avg") > 0
          ? tpm / stat("three_pointers_attempted_average", "three_pointers_attempted_per_game", "3PA/G", "3pfga_avg") * 100 : null);
      const ftm = stat("free_throws_made_average", "free_throws_made_per_game", "FTM/G", "ft_avg", "free_throws_made");
      const ftPct = stat("free_throws_percentage", "free_throw_percentage", "FT%", "ft_per_avg")
        ?? (ftm != null && fta > 0 ? ftm / fta * 100 : null);
      const assists = stat("assists_average", "assists_per_game", "APG", "ast_avg");
      const turnovers = tov;
      const ratio = fga > 0 && fgm != null && tpm != null ? 100 * (fgm + 0.5 * tpm) / fga : null;
      const efgRaw = stat("effective_field_goal_percentage", "effective_fg_percentage", "efg_percentage", "eFG%");
      const efg = efgRaw ?? ratio;
      const directTs = stat("true_shooting_percentage", "true_shooting_pct", "ts_percentage", "TS%");
      const pointsForEfficiency = ppg ?? (fgm != null && tpm != null && ftm != null ? 2 * fgm + tpm + ftm : null);
      const ts = directTs ?? (pointsForEfficiency != null && fga != null && fta != null && fga + 0.44 * fta > 0
        ? 100 * pointsForEfficiency / (2 * (fga + 0.44 * fta)) : null);
      const astTov = assists != null && turnovers > 0 ? assists / turnovers : null;
      const phase = pick("Phase", "phase", "season · season_type");
      const name = pick("Player", "player_name", "name", "display_name", "full_name") || "Name unavailable";
      const team = pick("Team", "team_name", "team · name", "team · team_name") || "—";
      const pos = pick("Position", "position", "playing_position", "player · position", "player · playing_position");
      const extras = Object.fromEntries(Object.entries(row).filter(([key, value]) =>
        typeof value === "number" && !hiddenField(key)));
      return { ...extras, Phase: phase, Player: name, Team: team, Position: pos, GP: gp, GS: gs, MPG: mpg, PPG: ppg, RPG: rpg, APG: apg,
        SPG: spg, BPG: bpg, "TOV/G": tov, "FG%": fgPct, "3P%": threePct, "FT%": ftPct, "eFG%": efg, "TS%": ts, "AST/TOV": astTov };
    }
    if (view === "teams") {
      const pick = (...keys) => keys.map(key => row[key]).find(value => value != null && value !== "");
      const name = pick("Team", "team_name", "team · name", "team · team_name", "name") || "Team unavailable";
      const code = pick("Team code", "team · team_code", "team_code", "abbreviation");
      const number = (...keys) => {
        const value = pick(...keys);
        return value == null || !Number.isFinite(Number(value)) ? null : Number(value);
      };
      const gp = number("played", "games_played", "games", "GP");
      const wins = number("won", "wins", "w", "Won");
      const losses = number("lost", "losses", "l", "Lost");
      const winPct = number("win_percentage", "win_pct", "Win %") ?? (gp > 0 && wins != null ? wins / gp : null);
      const ppg = number("points_average", "points_per_game", "PPG", "scoring_average");
      const opp = number("opponent_points_average", "points_against_average", "points_allowed_average", "opp_points_average", "opponent_ppg");
      const pointDiff = number("point_diff_average", "average_point_differential", "point_differential", "point_diff");
      const pace = number("pace", "pace_average", "possessions_per_game", "possessions_average");
      const off = number("offensive_rating", "offensive_rating_average", "ortg", "off_rating");
      const def = number("defensive_rating", "defensive_rating_average", "drtg", "def_rating");
      const net = number("net_rating", "net_rating_average", "netrtg", "net_efficiency");
      const efg = number("effective_field_goal_percentage", "efg_percentage", "efg_pct", "eFG%");
      const ts = number("true_shooting_percentage", "ts_percentage", "ts_pct", "TS%");
      const threeRate = number("three_point_rate", "three_point_attempt_rate", "three_rate", "3P rate");
      const ftRate = number("free_throw_rate", "free_throw_attempt_rate", "ft_rate", "FT rate");
      const rpg = number("rebounds_average", "rebounds_per_game", "RPG", "total_rebounds_average", "trb_avg");
      const apg = number("assists_average", "assists_per_game", "APG", "ast_avg");
      const tov = number("turnovers_average", "turnovers_per_game", "TOV/G", "tov_avg");
      const phase = pick("Phase", "phase", "season · season_type");
      const extras = Object.fromEntries(Object.entries(row).filter(([key, value]) =>
        typeof value === "number" && !hiddenField(key)));
      return { ...extras, Phase: phase, Team: name, "Team code": code, GP: gp, Wins: wins, Losses: losses, "Win %": winPct, PPG: ppg,
        "Opponent PPG": opp, "Point diff": pointDiff, Pace: pace, OffRtg: off, DefRtg: def,
        NetRtg: net, "eFG%": efg, "TS%": ts, "3P rate": threeRate, "FT rate": ftRate,
        RPG: rpg, APG: apg, "TOV/G": tov };
    }
    if (view === "games") {
      const pick = (...keys) => keys.map(key => row[key]).find(value => value != null && value !== "");
      const home = pick("home_team_name", "home_team · name", "home_team · team_name", "home_team · display_name", "home_team · team_nickname", "home_team · team_code", "home · name", "home · team_name");
      const away = pick("away_team_name", "away_team · name", "away_team · team_name", "away_team · display_name", "away_team · team_nickname", "away_team · team_code", "away · name", "away · team_name");
      const homeScore = pick("home_team_score", "home_score", "home_team · score", "home · score");
      const awayScore = pick("away_team_score", "away_score", "away_team · score", "away · score");
      const date = pick("scheduled_start", "start_time_datetime", "start_time", "match_date", "date");
      const round = pick("match_round", "round_number", "round · name", "round");
      let status = pick("match_status", "status", "state") || "Scheduled";
      status = ({ scheduled: "Upcoming", complete: "Final", completed: "Final", finished: "Final", live: "In progress", in_progress: "In progress" })[String(status).toLowerCase()] || status;
      const venue = pick("venue_name", "venue · name", "venue");
      const score = homeScore != null && homeScore !== "" && awayScore != null && awayScore !== ""
        ? homeScore + "–" + awayScore : "—";
      return { Date: date, Round: round, Matchup: [home, away].filter(Boolean).join(" vs "), Score: score, Status: status, Venue: venue };
    }
    if (view === "boxscores") {
      const game = row["_game"] || {};
      const get = (...keys) => keys.map(key => row[key]).find(value => value != null && value !== "");
      const name = get("Player", "player_name", "player · display_name", "player · full_name", "player · name", "name") || "—";
      const team = get("Team", "team · name", "team · team_name") || "—";
      const home = game.home_team?.name || game.home_team?.team_code || "";
      const away = game.away_team?.name || game.away_team?.team_code || "";
      const rawDate = game.start_time || "";
      const number = (...keys) => { const value = get(...keys); return value == null || !Number.isFinite(Number(value)) ? null : Number(value); };
      const fgm = number("field_goals_made", "field_goal_made", "field_goal_avg");
      const fga = number("field_goals_attempted", "field_goal_attempted", "field_goal_attempt_avg");
      const tpm = number("three_pointers_made", "three_point_made", "3pfg_avg");
      const tpa = number("three_pointers_attempted", "three_point_attempted", "3pfga_avg");
      const ftm = number("free_throws_made", "free_throw_made", "ft_avg");
      const fta = number("free_throws_attempted", "free_throw_attempted", "fta_avg");
      return { Date: rawDate, Round: game.match_round || game.round_number, Matchup: [home, away].filter(Boolean).join(" vs "), Player: name, Team: team,
        MIN: number("minutes", "minutes_played", "minutes_played_total"), PTS: number("points", "points_total"), REB: number("rebounds", "total_rebounds", "rebounds_total"),
        OREB: number("offensive_rebounds", "offensive_rebounds_total"), DREB: number("defensive_rebounds", "defensive_rebounds_total"),
        AST: number("assists", "assists_total"), STL: number("steals", "steals_total"), BLK: number("blocks", "blocks_total"), TOV: number("turnovers", "turnovers_total"),
        FGM: fgm, FGA: fga, "FG%": fgm != null && fga > 0 ? 100 * fgm / fga : null,
        "3PM": tpm, "3PA": tpa, "3P%": tpm != null && tpa > 0 ? 100 * tpm / tpa : null,
        FTM: ftm, FTA: fta, "FT%": ftm != null && fta > 0 ? 100 * ftm / fta : null,
        "+/-": number("plus_minus", "plus_minus_total", "plusminus") };
    }
    if (view === "players") {
      const pick = (...keys) => keys.map(key => row[key]).find(value => value != null && value !== "");
      const player = pick("Player", "player_name", "name", "display_name", "full_name");
      const team = pick("Team", "team_name", "team · name", "team · team_name");
      const position = pick("Position", "position", "playing_position", "player · position", "player · playing_position");
      const jersey = pick("Jersey", "jersey_number", "player · jersey_number", "shirt_number");
      const height = pick("Height", "height", "player · height");
      const weight = pick("Weight", "weight", "player · weight");
      const nationality = pick("Nationality", "nationality", "country", "player · nationality", "player · country");
      const code = pick("Team code", "team_code", "team · team_code", "abbreviation");
      return { Player: player || "Name unavailable", Team: team || "—", Position: position, Jersey: jersey, Height: height, Weight: weight, Nationality: nationality,
        ...(code ? { "Team code": code } : {}) };
    }
    return row;
  });
}

function labelFor(key) {
  if (key in fieldLabels) return fieldLabels[key];
  const tail = key.split(" · ").at(-1);
  if (tail in fieldLabels) return fieldLabels[tail];
  return tail.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
}

function displayValue(key, value) {
  if (value == null || value === "") return "—";
  const lower = labelFor(key).toLowerCase();
  if (typeof value === "number" && (["fg%", "3p%", "ft%", "efg%", "ts%", "win %"].includes(lower) || /%$/.test(lower))) {
    return (value <= 1 ? value * 100 : value).toFixed(1) + "%";
  }
  if (typeof value === "number" && ["3p rate", "ft rate"].includes(lower)) {
    return (value <= 1 ? value * 100 : value).toFixed(1) + "%";
  }
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(1);
  if (typeof value === "string" && /(?:date|scheduled_start)$/.test(lower) && /^\d{4}-\d\d-\d\d/.test(value)) {
    const date = new Date(value);
    if (!Number.isNaN(date.valueOf())) return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }
  return String(value);
}

fetch("data/stats_index.json", { cache: "no-cache" })
  .then(response => {
    if (!response.ok) throw Error("NBL data unavailable (" + response.status + ")");
    return response.json();
  })
  .then(index => {
    const seasons = index.seasons || {};
    const years = Object.keys(seasons).sort((a, b) => Number(b) - Number(a));
    const season = $("season"), dataset = $("dataset"), groupSelect = $("statGroup"),
      groupField = $("groupField"), search = $("search");
    const head = $("head"), body = $("body");
    season.innerHTML = years.map(year => '<option value="' + esc(year) + '">' + esc(year)
      + "–" + String(Number(year) + 1).slice(-2) + "</option>").join("");
    season.value = years[0] || "";
    let rows = [], view = "leaders", group = "production", sort = { key: "", dir: -1 };

    function setDefaultSort() {
      const defaults = {
        leaders: {production:["PPG",-1], shooting:["TS%",-1]},
        teams: {summary:["Win %",-1], efficiency:["NetRtg",-1], boxscore:["RPG",-1]},
        boxscores: {production:["Date",-1], shooting:["Date",-1], rebounding:["Date",-1]},
        games: {default:["Date",1]}, standings: {default:["Position",1]}, players: {default:["Player",1]}
      };
      const [label, dir] = defaults[view]?.[group] || defaults[view]?.default || ["",-1];
      const key = Object.hasOwn(rows[0] || {}, label) ? label : Object.keys(rows[0] || {}).find(field => labelFor(field) === label) || label;
      sort = {key, dir};
    }

    function render() {
      const query = search.value.trim().toLowerCase();
      let selected = rows;
      if (query) selected = selected.filter(row => Object.values(row).some(value => String(value ?? "").toLowerCase().includes(query)));
      if (sort.key) selected = selected.slice().sort((a, b) => {
        const left = a[sort.key], right = b[sort.key];
        if (left == null || left === "") return right == null || right === "" ? 0 : 1;
        if (right == null || right === "") return -1;
        const aNum = Number(left), bNum = Number(right);
        return (Number.isFinite(aNum) && Number.isFinite(bNum)
          ? aNum - bNum : String(left).localeCompare(String(right))) * sort.dir;
      });
      const availableColumns = [...new Set(rows.flatMap(Object.keys))].filter(key => !hiddenField(key));
      const preferred = statGroups[view]?.[group] || viewStats[view] || [];
      const primary = preferred.map(label => availableColumns.includes(label)
        ? label : availableColumns.find(key => labelFor(key) === label)).filter(Boolean);
      const candidates = [...new Set([...primary, ...availableColumns.filter(key =>
        statGroups[view] ? columnGroup(key, view) === group : true)])];
      const columns = candidates.filter((key, i) =>
        candidates.findIndex(candidate => labelFor(candidate) === labelFor(key)) === i);
      $("status").textContent = selected.length.toLocaleString() + " rows · " + columns.length
        + " readable fields · click a heading to sort · source checked " + (index.meta.updated_utc || "date unavailable")
        + (index.meta.errors?.length ? " · refresh warning; last cached data kept" : "");
      head.innerHTML = "<tr>" + columns.map(key => '<th scope="col" tabindex="0" aria-sort="' + (sort.key === key ? (sort.dir > 0 ? "ascending" : "descending") : "none") + '" data-key="' + esc(key) + '">' + esc(labelFor(key)) + "</th>").join("") + "</tr>";
      head.querySelectorAll("th").forEach(th => {
        const onSort = () => {
          if (sort.key === th.dataset.key) sort.dir *= -1;
          else sort = { key: th.dataset.key, dir: typeof rows[0]?.[th.dataset.key] === "string" ? 1 : -1 };
          render();
          head.querySelector('[data-key="' + CSS.escape(th.dataset.key) + '"]')?.focus();
        };
        th.onclick = onSort;
        th.onkeydown = event => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault(); onSort();
        };
      });
      body.innerHTML = selected.slice(0, 5000).map(row => "<tr>" + columns.map(key => {
        const value = displayValue(key, row[key]);
        return '<td title="' + esc(value) + '">' + esc(value) + "</td>";
      }).join("") + "</tr>").join("")
        || '<tr><td colspan="' + Math.max(columns.length, 1) + '" class="txt">No stats match those filters.</td></tr>';
    }

    function update() {
      const data = seasons[season.value] || {};
      const available = Object.entries(data).filter(([, value]) => Array.isArray(value));
      available.sort(([a], [b]) => preferredViews.indexOf(a) - preferredViews.indexOf(b));
      dataset.innerHTML = available.map(([key, value]) => '<option value="' + esc(key) + '">'
        + esc(viewLabels[key] || key.replaceAll("_", " ")) + " (" + value.length + ")</option>").join("");
      view = available.some(([key]) => key === "leaders") ? "leaders" : available[0]?.[0];
      dataset.value = view;
      group = Object.keys(statGroups[view] || {})[0] || "default";
      groupField.hidden = !statGroups[view];
      if (statGroups[view]) {
        groupSelect.innerHTML = Object.keys(statGroups[view]).map(key => '<option value="' + esc(key) + '">' + esc(groupLabels[key] || key) + '</option>').join("");
        groupSelect.value = group;
      }
      rows = friendlyRows(data[view] || [], view);
      setDefaultSort();
      render();
    }

    $("stamp").textContent = "NBL stats · updated " + (index.meta.updated_utc || "unknown");
    if (!years.length) {
      $("status").textContent = "No season data is available yet. The automatic refresh will retry.";
      return;
    }
    season.onchange = update;
    dataset.onchange = () => {
      view = dataset.value;
      group = Object.keys(statGroups[view] || {})[0] || "default";
      groupField.hidden = !statGroups[view];
      if (statGroups[view]) {
        groupSelect.innerHTML = Object.keys(statGroups[view]).map(key => '<option value="' + esc(key) + '">' + esc(groupLabels[key] || key) + '</option>').join("");
        groupSelect.value = group;
      }
      rows = friendlyRows((seasons[season.value] || {})[view] || [], view);
      setDefaultSort();
      render();
    };
    groupSelect.onchange = () => { group = groupSelect.value; setDefaultSort(); render(); };
    search.oninput = render;
    update();
  })
  .catch(error => {
    $("status").textContent = error.message + ". The automatic refresh will retry.";
    $("stamp").textContent = "NBL data unavailable";
  });
