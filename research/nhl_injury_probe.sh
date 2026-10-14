#!/bin/bash
# Probe NHL shift-chart and play-by-play feeds (robots + one game). Writes data/research/nhl_shift_probe/
D=data/research/nhl_shift_probe; mkdir -p $D
UA="SportsFutures/1.0 (private research; low volume)"
{
for h in api.nhle.com api-web.nhle.com www.nhl.com; do echo "== robots $h"; curl -sSL -m 20 -A "$UA" https://$h/robots.txt -w '\nHTTP %{http_code}\n' | head -30; done
} > $D/robots.txt 2>&1
curl -sSL -m 60 -A "$UA" "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId=2024020500" -o $D/shifts.json -w 'shifts HTTP %{http_code} %{size_download} %{time_total}\n' > $D/status.txt
curl -sSL -m 60 -A "$UA" "https://api-web.nhle.com/v1/gamecenter/2024020500/play-by-play" -o $D/pbp.json -w 'pbp HTTP %{http_code} %{size_download} %{time_total}\n' >> $D/status.txt
curl -sSL -m 60 -A "$UA" "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId=2014020500" -o $D/shifts2014.json -w 'shifts2014 HTTP %{http_code} %{size_download}\n' >> $D/status.txt
curl -sSL -m 60 -A "$UA" "https://api-web.nhle.com/v1/gamecenter/2014020500/play-by-play" -o $D/pbp2014.json -w 'pbp2014 HTTP %{http_code} %{size_download}\n' >> $D/status.txt
