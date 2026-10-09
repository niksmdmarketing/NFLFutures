const $ = id => document.getElementById(id);
const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));

const viewLabels = {
  leaders: "Player leaders",
  teams: "Team season stats",
  games: "Game results",
  standings: "Standings",
  players: "Player directory"
};
const preferredViews = ["leaders", "teams", "games", "standings", "players"];
const viewStats = {
  leaders: ["Player", "Team", "Position", "GP", "MPG", "PPG", "RPG", "APG", "SPG", "BPG", "TOV/G", "FG%", "3P%", "FT%"],
  teams: ["Team", "Team code", "GP", "Wins", "Losses", "PPG", "RPG", "APG", "FG%", "3P%", "FT%"],
  standings: ["Team", "Team code", "Position", "Wins", "Losses", "GP", "Win %", "Points for", "Points against", "Last 5"],
  games: ["Date", "Round", "Home team", "Home score", "Away team", "Away score", "Status", "Venue"],
  players: ["Player", "Team", "Team code", "Position", "Jersey"]
};
const fieldLabels = {
  "player · first_name": "First name", "player · last_name": "Last name",
  "player · display_name": "Player", "player · full_name": "Player",
  "player · name": "Player", "team · name": "Team", "team · team_name": "Team",
  "team · team_code": "Team code", "team · team_nickname": "Team nickname",
  "points_average": "PPG", "points_per_game": "PPG", "rebounds_average": "RPG",
  "rebounds_per_game": "RPG", "assists_average": "APG", "assists_per_game": "APG",
  "steals_average": "SPG", "blocks_average": "BPG", "turnovers_average": "TOV/G",
  "minutes_average": "MPG", "fouls_average": "PF/G", "personal_fouls_average": "PF/G",
  "field_goals_made_average": "FGM/G", "field_goals_attempted_average": "FGA/G",
  "field_goals_percentage": "FG%", "field_goal_percentage": "FG%",
  "three_pointers_made_average": "3PM/G", "three_pointers_attempted_average": "3PA/G",
  "three_pointers_percentage": "3P%", "free_throws_made_average": "FTM/G",
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
  "match_round": "Round", "venue_name": "Venue", "venue": "Venue"
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

function friendlyRows(records) {
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
  const lower = key.toLowerCase();
  if (typeof value === "number" && /(?:percentage|_pct|_percent)$/.test(lower) && value >= 0 && value <= 1) {
    return (value * 100).toFixed(1) + "%";
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
    const season = $("season"), dataset = $("dataset"), search = $("search");
    const head = $("head"), body = $("body");
    season.innerHTML = years.map(year => '<option value="' + esc(year) + '">' + esc(year)
      + "–" + String(Number(year) + 1).slice(-2) + "</option>").join("");
    let rows = [], view = "leaders", sort = { key: "", dir: -1 };

    function render() {
      const query = search.value.trim().toLowerCase();
      let selected = rows;
      if (query) selected = selected.filter(row => Object.values(row).some(value => String(value ?? "").toLowerCase().includes(query)));
      if (sort.key) selected = selected.slice().sort((a, b) => {
        const left = a[sort.key], right = b[sort.key];
        if (left == null) return 1;
        if (right == null) return -1;
        const aNum = Number(left), bNum = Number(right);
        return (Number.isFinite(aNum) && Number.isFinite(bNum)
          ? aNum - bNum : String(left).localeCompare(String(right))) * sort.dir;
      });
      const availableColumns = [...new Set(selected.flatMap(Object.keys))].filter(key => !hiddenField(key));
      const preferred = viewStats[view] || [];
      const columns = [
        ...preferred.map(label => availableColumns.find(key => labelFor(key) === label)).filter(Boolean),
        ...availableColumns.filter(key => !preferred.includes(labelFor(key)))
      ];
      $("status").textContent = selected.length.toLocaleString() + " rows · " + columns.length
        + " readable fields · click a heading to sort · source checked " + (index.meta.updated_utc || "date unavailable")
        + (index.meta.errors?.length ? " · refresh warning; last cached data kept" : "");
      head.innerHTML = "<tr>" + columns.map(key => '<th data-key="' + esc(key) + '">' + esc(labelFor(key)) + "</th>").join("") + "</tr>";
      head.querySelectorAll("th").forEach(th => th.onclick = () => {
        if (sort.key === th.dataset.key) sort.dir *= -1;
        else sort = { key: th.dataset.key, dir: typeof rows[0]?.[th.dataset.key] === "string" ? 1 : -1 };
        render();
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
      rows = friendlyRows(data[view] || []);
      sort = { key: "", dir: -1 };
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
      rows = friendlyRows((seasons[season.value] || {})[view] || []);
      sort = { key: "", dir: -1 };
      render();
    };
    search.oninput = render;
    update();
  })
  .catch(error => {
    $("status").textContent = error.message + ". The automatic refresh will retry.";
    $("stamp").textContent = "NBL data unavailable";
  });
