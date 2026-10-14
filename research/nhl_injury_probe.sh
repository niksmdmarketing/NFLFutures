#!/bin/bash
# Probe free NHL injury / IR sources (robots + shape). Writes data/research/nhl_injury_probe.txt
# Only reads robots.txt and, where robots allows, one page. Never retries a block.
mkdir -p data/research; O=data/research/nhl_injury_probe.txt
UA="SportsFutures/1.0 (private research; low volume)"
{
echo "== NHL roster endpoint (redirects followed)"
curl -sSL -m 30 -A "$UA" https://api-web.nhle.com/v1/roster/TOR/current -o /tmp/r.json -w 'HTTP %{http_code} %{url_effective}\n'
python3 -c "import json;d=json.load(open('/tmp/r.json'));print(list(d));print(json.dumps(d['forwards'][0])[:800])"
echo "== robots api-web.nhle.com"; curl -sSL -m 20 -A "$UA" https://api-web.nhle.com/robots.txt | head -20
echo "== NHL player landing keys"
pid=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(d['forwards'][0]['id'])")
curl -sSL -m 30 -A "$UA" https://api-web.nhle.com/v1/player/$pid/landing -o /tmp/p.json -w 'HTTP %{http_code}\n'
python3 -c "import json;d=json.load(open('/tmp/p.json'));print(sorted(d.keys()))"
grep -o -i '"[a-z]*injur[a-z]*"[^,]\{0,80\}' /tmp/p.json | head
echo "== club stats (games played per player, current season)"
curl -sSL -m 30 -A "$UA" https://api-web.nhle.com/v1/club-stats/TOR/now -o /tmp/cs.json -w 'HTTP %{http_code}\n'
python3 -c "import json;d=json.load(open('/tmp/cs.json'));print(list(d));print(json.dumps(d.get('goalies',[{}])[0])[:500])"
echo "== schedule + boxscore (lineups per game)"
curl -sSL -m 30 -A "$UA" https://api-web.nhle.com/v1/club-schedule-season/TOR/now -o /tmp/s.json -w 'HTTP %{http_code}\n'
gid=$(python3 -c "import json;d=json.load(open('/tmp/s.json'));g=[x for x in d['games'] if x.get('gameState') in ('OFF','FINAL')];print(g[-1]['id'] if g else d['games'][0]['id'])")
curl -sSL -m 30 -A "$UA" https://api-web.nhle.com/v1/gamecenter/$gid/boxscore -o /tmp/b.json -w "boxscore $gid HTTP %{http_code}\n"
python3 -c "import json;d=json.load(open('/tmp/b.json'));p=d.get('playerByGameStats',{});print(list(p));print(list(p.get('homeTeam',{})))"
for site in www.dailyfaceoff.com www.capwages.com www.spotrac.com www.cbssports.com www.rotowire.com www.hockey-reference.com www.tsn.ca www.nhl.com; do
  echo "== robots $site"
  curl -sSL -m 20 -A "$UA" "https://$site/robots.txt" -o /tmp/rb.txt -w 'HTTP %{http_code}\n'
  python3 - "$site" <<'PY'
import sys, urllib.robotparser
site = sys.argv[1]
txt = open('/tmp/rb.txt', errors='ignore').read()
rp = urllib.robotparser.RobotFileParser(); rp.parse(txt.splitlines())
paths = {'www.dailyfaceoff.com': ['/teams/toronto-maple-leafs/line-combinations', '/starting-goalies'],
         'www.capwages.com': ['/teams/toronto_maple_leafs', '/injuries'],
         'www.spotrac.com': ['/nhl/injured-reserve/'],
         'www.cbssports.com': ['/nhl/injuries/'],
         'www.rotowire.com': ['/hockey/nhl-lineups.php', '/hockey/injury-report.php'],
         'www.hockey-reference.com': ['/friv/injuries.cgi'],
         'www.tsn.ca': ['/nhl/injuries'],
         'www.nhl.com': ['/news/', '/mapleleafs/roster']}[site]
named = [l.strip() for l in txt.lower().splitlines() if any(b in l for b in ('anthropic', 'claude'))]
print('  mentions anthropic/claude:', named[:6])
for ua in ('anthropic-ai', 'ClaudeBot', 'SportsFutures'):
    print('  ', ua, {p: rp.can_fetch(ua, f'https://{site}{p}') for p in paths})
PY
done
} > $O 2>&1
