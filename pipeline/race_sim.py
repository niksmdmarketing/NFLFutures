"""Top-of-the-table individual races (most goals and the like): chance each player finishes first.

Appearances left ~ Binomial(team matches left, availability), events ~ Poisson(rate x gamma talent noise x appearances);
rate = events per appearance shrunk toward last season's over K appearances; availability = share of team matches so far
shrunk toward 80% over 6 matches. Ties at the top split the chance. Used by the AFL Coleman race (afl_site.awards).
"""
import numpy as np


def simulate_race(G, A, T, R, prior, k, shape, sims=20000, seed=7):
    rng = np.random.default_rng(seed)
    G, A, T, R, prior = (np.asarray(x, float) for x in (G, A, T, R, prior))
    rate = (G + k * prior) / (A + k)
    avail = (A + 0.8 * 6) / (T + 6)
    n = len(G)
    out = np.zeros(n)
    done = 0
    while done < sims:
        S = min(2000, sims - done)
        apps = rng.binomial(R.astype(int)[None, :].repeat(S, 0), np.clip(avail[None, :] + rng.normal(0, .1, (S, n)), 0, 1))
        fin = G[None, :] + rng.poisson(rate[None, :] * rng.gamma(shape, 1 / shape, (S, n)) * apps)
        w = (fin == fin.max(1, keepdims=True)).astype(float)
        out += (w / w.sum(1, keepdims=True)).sum(0)
        done += S
    return out / sims, G + rate * avail * R
