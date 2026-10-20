"""Canonical NBA team identities (ESPN abbreviations, as in the box scores) and every alias the data sources use.
resolve() maps an ESPN abbreviation, a league (injury-report) code or a full team name to the ESPN abbreviation, or returns None.
python research/nba_teams.py  -> self-test (exit code 1 on any failure)
"""
import sys

# ESPN abbreviation: (league code, full name)
TEAMS = {
    "ATL": ("ATL", "Atlanta Hawks"), "BKN": ("BKN", "Brooklyn Nets"), "BOS": ("BOS", "Boston Celtics"), "CHA": ("CHA", "Charlotte Hornets"),
    "CHI": ("CHI", "Chicago Bulls"), "CLE": ("CLE", "Cleveland Cavaliers"), "DAL": ("DAL", "Dallas Mavericks"), "DEN": ("DEN", "Denver Nuggets"),
    "DET": ("DET", "Detroit Pistons"), "GS": ("GSW", "Golden State Warriors"), "HOU": ("HOU", "Houston Rockets"), "IND": ("IND", "Indiana Pacers"),
    "LAC": ("LAC", "LA Clippers"), "LAL": ("LAL", "Los Angeles Lakers"), "MEM": ("MEM", "Memphis Grizzlies"), "MIA": ("MIA", "Miami Heat"),
    "MIL": ("MIL", "Milwaukee Bucks"), "MIN": ("MIN", "Minnesota Timberwolves"), "NO": ("NOP", "New Orleans Pelicans"),
    "NY": ("NYK", "New York Knicks"), "OKC": ("OKC", "Oklahoma City Thunder"), "ORL": ("ORL", "Orlando Magic"),
    "PHI": ("PHI", "Philadelphia 76ers"), "PHX": ("PHX", "Phoenix Suns"), "POR": ("POR", "Portland Trail Blazers"),
    "SAC": ("SAC", "Sacramento Kings"), "SA": ("SAS", "San Antonio Spurs"), "TOR": ("TOR", "Toronto Raptors"), "UTAH": ("UTA", "Utah Jazz"),
    "WSH": ("WAS", "Washington Wizards"),
}
EXTRA_NAMES = {"Los Angeles Clippers": "LAC"}
_ALIAS = {}
for espn, (league, name) in TEAMS.items():
    for a in (espn, league, name):
        _ALIAS[a.upper()] = espn
for n, espn in EXTRA_NAMES.items():
    _ALIAS[n.upper()] = espn


def resolve(x):
    if x is None or (isinstance(x, float) and x != x):
        return None
    return _ALIAS.get(str(x).strip().upper())


def selftest():
    errors = []
    for espn, (league, name) in TEAMS.items():
        for a in (espn, league, name, name.lower()):
            if resolve(a) != espn:
                errors.append(f"{a!r} -> {resolve(a)!r}, expected {espn}")
    if len(set(TEAMS)) != 30 or len({v[0] for v in TEAMS.values()}) != 30:
        errors.append("team table is not 30 distinct teams")
    for bad in ("XYZ", "", None, "New York"):
        if resolve(bad) is not None:
            errors.append(f"unknown {bad!r} resolved to {resolve(bad)!r}")
    try:
        sys.path.insert(0, __file__.rsplit("/", 2)[0] + "/pipeline")
        import nba as N
        if sorted(N.TEAMS) != sorted(TEAMS):
            errors.append(f"pipeline TEAMS differ: {sorted(set(N.TEAMS) ^ set(TEAMS))}")
        import nba_official as O
        for code, name in O.OFFICIAL_TEAMS.items():
            if resolve(code) is None or resolve(name) is None or resolve(code) != resolve(name):
                errors.append(f"official {code}/{name} does not resolve consistently")
    except ImportError as e:
        errors.append(f"import: {e}")
    return errors


if __name__ == "__main__":
    errs = selftest()
    print("\n".join(errs) if errs else "team mapping self-test: all 30 teams resolve from ESPN, league and full names")
    sys.exit(1 if errs else 0)
