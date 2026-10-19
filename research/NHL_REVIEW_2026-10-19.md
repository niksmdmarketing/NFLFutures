# NHL early-season review (19 Oct 2026)

Live pre-game win chances (forecast-archive, scored with pipeline/live_check.py logic): 31 games since the archive began on 12 Oct.
Log loss 0.630 (coin flip 0.693; fixed 55% home 0.663); 64.5% of favourites won; home sides won 67.7% (small sample).
Season futures: not scoreable until the season is half played.

Replay calibration (model/replay/nhl_*.csv, regenerated with the live model, 2014-2025): at 5-12 games played the conference-final (reach the Cup Final)
calibration slope is 1.57 (season-bootstrap 90%: 1.27-1.94), Cup 1.45 (0.99-2.20), make playoffs 1.10 (0.89-1.31); at 12-25 games 1.29 / 1.28 / 0.94.
So early Cup and conference odds remain too flat, as already noted when the live playoff fade was raised from 1.0 to 3.0 on 15 Oct 2026
(pipeline/nhl_model.py, PO_FADE). The live model is still more decisive than Polymarket on the leaders (e.g. COL 51% West vs 36%).

Decision (TypeSafe 58%, 19 Oct 2026): no new test now. Two tuning steps have already been taken on the same ten seasons; a third (higher fade)
would risk fitting noise. The prospective comparison already running (live fade 3.0 vs archived shadow 1.0) is reviewed at mid-season.
Runner-up for a later dated rule (40%): a different mechanism for the early flatness rather than a larger fade.
