# Three inactive owner overrides — 29 October 2026

Retired the Highsmith/PHX, Sochan/POR and Brown/NY minutes entries into
`model/nba_overrides.json:retired_minutes`, retaining their original amounts,
notes, transaction dates and evidence links. No new team assignment was made.
The normal override loader reads only `minutes`; historical calls remain auditable.

Evidence: [Portland's 17 October waiver announcement](https://www.nba.com/blazers/news/trail-blazerswaivejeremy-sochan);
[Brown's dated waiver update](https://www.nba.com/nets/player/1628971/bruce-brown);
[Highsmith's dated player update](https://cdn-uat.nba.com/player/1629312/haywood-highsmith).
The latter two are syndicated player news carried on NBA pages, not club
transaction announcements. Profile mastheads/cached pages can still show old
teams; those labels were not used to invent replacement memberships. The
saved current roster export has none of the three IDs on any team.

On the saved all-team input cohort, retiring these entries leaves all 30
roster-adjusted ratings exactly unchanged. Thus this is input housekeeping,
not a forecast improvement or an explanation of Golden State's division odds.

No merge, deployment, historical archive edit or website change.
