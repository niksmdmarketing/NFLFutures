"""Registered research-only preseason component; never infer an opening roster."""
import nhl_lineup


def prior_lineups(previous_skaters, previous_goalies, skaters, goalies, goalie_scale):
    """Value history at the same frozen ratings as today's lineups; no future opening."""
    if skaters is None or goalies is None or skaters.empty or goalies.empty:
        raise ValueError("Preseason RAPM candidate requires frozen skater and goalie ratings")
    if previous_skaters is None or previous_goalies is None:
        return None, None
    return nhl_lineup.game_values_ratings(
        previous_skaters, skaters, goalies, goalie_scale, previous_goalies
    ), None
