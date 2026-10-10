"""Download free historical match odds spreadsheets (AusSportsBetting) into the market-data branch (research only)."""
import os, sys, time, urllib.request
OUT = os.path.join(sys.argv[1] if len(sys.argv) > 1 else ".", "match_odds")
os.makedirs(OUT, exist_ok=True)
for sp in ("nba", "nhl", "afl", "nbl", "nfl"):
    for url in (f"https://www.aussportsbetting.com/historical_data/{sp}.xlsx", f"https://www.aussportsbetting.com/historical_data/{sp}.xls"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
            if len(b) > 10000:
                open(os.path.join(OUT, os.path.basename(url)), "wb").write(b)
                print("ok", url, len(b))
                break
            print("small", url, len(b))
        except Exception as e:  # noqa: BLE001
            print("fail", url, e)
        time.sleep(1)
