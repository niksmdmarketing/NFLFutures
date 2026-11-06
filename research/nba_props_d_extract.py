"""Development feature rows for challenger d (research/NBA_PROPS_PRICE_TEST_RULE.md Amendment 9): run the frozen forecaster once in
replay mode at a cutoff before 12 Jan 2026 and save the full prop-feature table it builds (every 2024-25 and 2025-26 row up to the
cutoff, point-in-time features as in the research build), after the M2 minutes features are added. The forecaster is not edited:
the table is captured by wrapping research/nba_minutes_tail_test.features. No price is read.
Usage: python research/nba_props_d_extract.py <out.parquet> <cutoff ISO> <reports_csv,reports_csv>"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main(out, cutoff, reports):
    os.environ.update(NBA_PROPS_SEASON="2026", NBA_PROPS_PARAMS_ID="b", NBA_PROPS_REPLAY_REPORTS=reports)
    import nba_minutes_tail_test as TT
    import nba_props_live as L
    orig = TT.features
    cap = {}

    def wrapped(F):
        F2 = orig(F)
        cap["F"] = F2.copy()
        return F2
    TT.features = wrapped
    import argparse
    a = argparse.Namespace(archive=tempfile.mkdtemp(), now=cutoff, force_game=None, horizon="60", pending_hours=None)
    L.run(a)
    F = cap["F"]
    F.to_parquet(out, index=False)
    print(out, len(F), sorted(F.season.unique()), str(F.tip.max()))


if __name__ == "__main__":
    main(*sys.argv[1:4])
