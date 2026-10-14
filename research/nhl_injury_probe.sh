#!/bin/bash
# Fetch one copy of two robots-permitted NHL injury pages to inspect their structure. Writes data/research/nhl_inj_raw/.
mkdir -p data/research/nhl_inj_raw; D=data/research/nhl_inj_raw
UA="SportsFutures/1.0 (private research; low volume)"
curl -sSL -m 30 -A "$UA" https://www.cbssports.com/nhl/injuries/ -o $D/cbs.html -w 'cbs HTTP %{http_code} %{size_download}\n' > $D/status.txt 2>&1
sleep 5
curl -sSL -m 30 -A "$UA" https://www.hockey-reference.com/friv/injuries.cgi -o $D/hr.html -w 'hr HTTP %{http_code} %{size_download}\n' >> $D/status.txt 2>&1
