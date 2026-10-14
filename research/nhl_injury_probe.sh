#!/bin/bash
# Probe free NHL injury / IR sources (robots + shape). Writes data/research/nhl_injury_probe.txt
mkdir -p data/research; O=data/research/nhl_injury_probe.txt
UA="SportsFutures/1.0 (private research; low volume)"
{
echo "== robots puckpedia"; curl -sS -m 20 -A "$UA" -w '\nHTTP %{http_code}\n' https://puckpedia.com/robots.txt | head -40
echo "== puckpedia injuries page (TOR)"; curl -sS -m 30 -A "$UA" -o /tmp/pp.html -w 'HTTP %{http_code} bytes %{size_download}\n' https://puckpedia.com/team/toronto-maple-leafs/injuries
grep -o -i 'injur[^<]\{0,120\}' /tmp/pp.html | head -15
echo "== NHL roster endpoint keys"; curl -sS -m 30 -A "$UA" https://api-web.nhle.com/v1/roster/TOR/current -o /tmp/r.json -w 'HTTP %{http_code}\n'
python3 -c "import json;d=json.load(open('/tmp/r.json'));print(list(d));print(d['forwards'][0])"
echo "== NHL player landing keys"; pid=$(python3 -c "import json;d=json.load(open('/tmp/r.json'));print(d['forwards'][0]['id'])"); curl -sS -m 30 -A "$UA" https://api-web.nhle.com/v1/player/$pid/landing -o /tmp/p.json -w 'HTTP %{http_code}\n'; python3 -c "import json;d=json.load(open('/tmp/p.json'));print(sorted(d.keys()))"
echo "== NHL stats API injury/transaction search"; for u in "https://api.nhle.com/stats/rest/en/transaction" "https://api-web.nhle.com/v1/transactions" ; do curl -sS -m 20 -A "$UA" -o /dev/null -w "$u HTTP %{http_code}\n" "$u"; done
} > $O 2>&1
