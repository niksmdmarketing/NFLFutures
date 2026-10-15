#!/bin/bash
# Robots / access probe for football data sites (robots.txt and one page status only). Writes data/research/site_probe.txt
mkdir -p data/research; O=data/research/site_probe.txt
UA="SportsFutures/1.0 (private research; low volume)"
{
for site in www.whoscored.com www.transfermarkt.com www.fotmob.com; do
  echo "== $site"
  curl -sSL -m 20 -A "$UA" "https://$site/robots.txt" -o /tmp/rb.txt -w 'robots HTTP %{http_code}\n'
  python3 - "$site" <<'PY'
import sys, urllib.robotparser
site = sys.argv[1]
txt = open('/tmp/rb.txt', errors='ignore').read()
print('  first lines:', ' | '.join(txt.splitlines()[:12])[:600])
rp = urllib.robotparser.RobotFileParser(); rp.parse(txt.splitlines())
paths = {'www.whoscored.com': ['/Regions/252/Tournaments/2/England-Premier-League', '/Players/1'],
         'www.transfermarkt.com': ['/premier-league/startseite/wettbewerb/GB1', '/liverpool-fc/kader/verein/31'],
         'www.fotmob.com': ['/api/matchDetails', '/leagues/47/overview/premier-league']}[site]
for ua in ('anthropic-ai', 'ClaudeBot', 'SportsFutures', '*'):
    print('  ', ua, {p: rp.can_fetch(ua, f'https://{site}{p}') for p in paths})
PY
  curl -sSL -m 20 -A "$UA" "https://$site/" -o /dev/null -w '  home page HTTP %{http_code}\n'
done
} > $O 2>&1
