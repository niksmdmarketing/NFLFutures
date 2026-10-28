"""Fixed, result-independent helpers for the registered early-award replay."""
import math

CHECKPOINT_DAYS=(3,7,14,21,28)

def scheduled_games(end_year):
    # Announced before opening night; 2020 opening checkpoints still had an 82-game schedule.
    return {2012:66,2021:72}.get(int(end_year),82)


def validate_distribution(probabilities, allow_empty=False):
    if not probabilities:
        if allow_empty:return
        raise ValueError('No baseline award distribution; stop before scoring')
    if any(not math.isfinite(float(v)) or v<0 for v in probabilities.values()):
        raise ValueError('Non-finite or negative award probability')
    if not math.isclose(sum(probabilities.values()),1.0,abs_tol=1e-10):
        raise ValueError('Award probability mass is not one')


def blend(ps, pp, team_games):
    validate_distribution(ps)
    w=min(1.0,float(team_games)/20.0)
    if w<0:raise ValueError('Negative team-game count')
    if w==1:return dict(ps)  # literal identity, including zero-support entries
    if not pp or sum(pp.values())==0:
        z={k:float(v)**w for k,v in ps.items() if v>0}
        total=sum(z.values())
        result={k:v/total for k,v in z.items()}
    else:
        validate_distribution(pp)
        result={k:w*ps.get(k,0)+(1-w)*pp.get(k,0) for k in sorted(set(ps)|set(pp))}
    validate_distribution(result)
    return result
