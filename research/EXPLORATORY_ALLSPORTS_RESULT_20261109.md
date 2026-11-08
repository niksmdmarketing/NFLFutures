# All-sports exploratory search: AFL, NBA, NFL results (9 Nov 2026). NHL and NBL pending (cannot run in the sandbox).
Rule: research/EXPLORATORY_ALLSPORTS_RULE.md (frozen first). Evaluator: research/explore_eval.py. ALL IN-SAMPLE, EXPLORATORY, nothing adopted. dLL = arm minus null log loss (negative = arm better). 'harm cells' = stage x market cells whose 90% upper bound on dLL exceeds +0.002. Null = live code at same sims (NBA 1000, AFL 1500, NFL 1000).

## afl
```
afl: seasons 2013-2026 (14), null null; IN-SAMPLE, EXPLORATORY. discovery < 2021 <= check
m1.4_g1.0      pooled dLL -0.0009 | disc +0.0001 check -0.0019 | best season removed -0.0004 | worst cell third quarter/pf -0.0010 (90% up +0.0037) | harm cells 5/35 | decision playoff@third quarter: slope null 0.67 arm 0.74 contrast +0.071 [10% +0.059, 90% +0.085]
m1.4_g1.1      pooled dLL -0.0008 | disc +0.0004 check -0.0021 | best season removed -0.0001 | worst cell third quarter/finals +0.0024 (90% up +0.0043) | harm cells 10/35 | decision playoff@third quarter: slope null 0.67 arm 0.75 contrast +0.079 [10% +0.066, 90% +0.096]
m2.0_g1.0      pooled dLL -0.0006 | disc +0.0012 check -0.0028 | best season removed +0.0003 | worst cell third quarter/pf +0.0024 (90% up +0.0131) | harm cells 11/35 | decision playoff@third quarter: slope null 0.67 arm 0.87 contrast +0.198 [10% +0.167, 90% +0.234]
m2.0_g1.1      pooled dLL -0.0005 | disc +0.0016 check -0.0029 | best season removed +0.0006 | worst cell third quarter/pf +0.0021 (90% up +0.0128) | harm cells 15/35 | decision playoff@third quarter: slope null 0.67 arm 0.87 contrast +0.197 [10% +0.166, 90% +0.234]
m2.8_g1.0      pooled dLL +0.0014 | disc +0.0040 check -0.0016 | best season removed +0.0028 | worst cell third quarter/pf +0.0131 (90% up +0.0289) | harm cells 17/35 | decision playoff@third quarter: slope null 0.67 arm 1.05 contrast +0.377 [10% +0.322, 90% +0.441]
m2.8_g1.1      pooled dLL +0.0014 | disc +0.0042 check -0.0019 | best season removed +0.0029 | worst cell third quarter/pf +0.0125 (90% up +0.0281) | harm cells 18/35 | decision playoff@third quarter: slope null 0.67 arm 1.04 contrast +0.365 [10% +0.310, 90% +0.430]
```

## nba
```
nba: seasons 2013-2026 (13), null null; IN-SAMPLE, EXPLORATORY. discovery < 2021 <= check
taupre1        pooled dLL +0.0020 | disc +0.0000 check +0.0045 | best season removed +0.0026 | worst cell preseason/playoff +0.0455 (90% up +0.0681) | harm cells 17/45 | decision playoff@preseason: slope null 1.00 arm 0.55 contrast -0.453 [10% -0.526, 90% -0.391]
f0_t1.1        pooled dLL +0.0083 | disc +0.0016 check +0.0163 | best season removed +0.0100 | worst cell preseason/playoff +0.0455 (90% up +0.0681) | harm cells 39/45 | decision playoff@preseason: slope null 1.00 arm 0.55 contrast -0.453 [10% -0.526, 90% -0.391]
f0_t3.3        pooled dLL +0.0021 | disc +0.0065 check -0.0032 | best season removed +0.0031 | worst cell preseason/div +0.0115 (90% up +0.0195) | harm cells 44/45 | decision playoff@preseason: slope null 1.00 arm 1.47 contrast +0.468 [10% +0.405, 90% +0.543]
f0.5_t1.1      pooled dLL +0.0092 | disc +0.0020 check +0.0180 | best season removed +0.0111 | worst cell preseason/playoff +0.0455 (90% up +0.0681) | harm cells 39/45 | decision playoff@preseason: slope null 1.00 arm 0.55 contrast -0.453 [10% -0.526, 90% -0.391]
f0.5_t2.2      pooled dLL +0.0005 | disc -0.0008 check +0.0020 | best season removed +0.0008 | worst cell third quarter/top6 +0.0039 (90% up +0.0078) | harm cells 20/45 | decision playoff@preseason: slope null 1.00 arm 1.00 contrast +0.000 [10% +0.000, 90% +0.000]
f0.5_t3.3      pooled dLL +0.0003 | disc +0.0032 check -0.0032 | best season removed +0.0010 | worst cell preseason/div +0.0115 (90% up +0.0195) | harm cells 23/45 | decision playoff@preseason: slope null 1.00 arm 1.47 contrast +0.468 [10% +0.405, 90% +0.543]
f0.8_t1.1      pooled dLL +0.0099 | disc +0.0023 check +0.0190 | best season removed +0.0118 | worst cell preseason/playoff +0.0455 (90% up +0.0681) | harm cells 39/45 | decision playoff@preseason: slope null 1.00 arm 0.55 contrast -0.453 [10% -0.526, 90% -0.391]
f0.8_t2.2      pooled dLL +0.0014 | disc -0.0006 check +0.0037 | best season removed +0.0019 | worst cell third quarter/top6 +0.0073 (90% up +0.0134) | harm cells 27/45 | decision playoff@preseason: slope null 1.00 arm 1.00 contrast +0.000 [10% +0.000, 90% +0.000]
f0.8_t3.3      pooled dLL +0.0003 | disc +0.0024 check -0.0023 | best season removed +0.0007 | worst cell preseason/div +0.0115 (90% up +0.0195) | harm cells 22/45 | decision playoff@preseason: slope null 1.00 arm 1.47 contrast +0.468 [10% +0.405, 90% +0.543]
```

## nfl
```
nfl: seasons 2022-2025 (4), null null; IN-SAMPLE, EXPLORATORY. discovery < 2024 <= check
s0.80_g10.23   pooled dLL -0.0001 | disc +0.0014 check -0.0016 | best season removed +0.0013 | worst cell second quarter/playoff +0.0034 (90% up +0.0066) | harm cells 6/25 | decision playoff@preseason: slope null 0.68 arm 0.73 contrast +0.050 [10% +0.039, 90% +0.062]
s0.80_g12.51   pooled dLL +0.0001 | disc +0.0036 check -0.0033 | best season removed +0.0027 | worst cell third quarter/div +0.0008 (90% up +0.0083) | harm cells 18/25 | decision playoff@preseason: slope null 0.68 arm 0.78 contrast +0.100 [10% +0.071, 90% +0.126]
s0.98_g10.23   pooled dLL +0.0005 | disc -0.0033 check +0.0042 | best season removed +0.0019 | worst cell third quarter/div +0.0026 (90% up +0.0113) | harm cells 18/25 | decision playoff@preseason: slope null 0.68 arm 0.61 contrast -0.071 [10% -0.094, 90% -0.048]
s0.98_g12.51   pooled dLL +0.0000 | disc -0.0013 check +0.0013 | best season removed +0.0005 | worst cell first quarter/div +0.0024 (90% up +0.0073) | harm cells 10/25 | decision playoff@preseason: slope null 0.68 arm 0.64 contrast -0.043 [10% -0.068, 90% -0.025]
```

## Reading (Claude, for DeepSeek's review)
- AFL: no arm passes the candidate rule. Best pooled gain is -0.0009 (m 1.4), discovery block slightly WORSE, harm cells 5/35. The "most informative" arm (m 2.0, single constant from gp 10) lifts Q3 playoff slope 0.67 -> 0.87 as predicted but pooled -0.0006, discovery +0.0012, best-season-removed +0.0003, 11/35 harm cells. No 2027 candidate named.
- NBA: no arm helps. TAU_PRE 1.0 (the most informative arm) is WORSE (+0.0020 pooled, preseason playoff LL +0.0455, slope 1.00 -> 0.55): the live 2.0 is doing real work. Live preseason playoff slope is already 1.00, so the decision market cannot move toward 1. TEAM_TAU 3.3 fixes nothing pooled (+0.0021 / +0.0003) and over-flattens preseason (slope 1.47). No candidate.
- NFL (descriptive only, 4 seasons): nothing above noise; no candidate possible.
- Pattern across sports: where a lever fixes one stage/market it breaks another, the same as AFL M2.

---
## Amendment (9 Nov 2026, later): the first NBA run was the WRONG ENGINE; corrected run below. Earlier NBA text above is kept as written.
The first NBA arms used replay_nba.py defaults (results-only proxy), not the live flags (BT_FULL=1 BT_PO_K=1 BT_PO_GAMMA=1.5 BT_PO_LASTPO=1 BT_PO_GAMES=1 per WORKLOG line 410). That run's null had preseason playoff slope 1.00 (stored live replay: 1.50). Rerun with live flags (6 arms, 13 seasons 2013-2026 with 2020 skipped by the era logic, 1000 sims):
```
nba: seasons 2013-2026 (13), null null; IN-SAMPLE, EXPLORATORY. discovery < 2021 <= check
taupre1        pooled dLL -0.0018 | disc -0.0031 check -0.0002 | best season removed -0.0015 | worst cell first quarter/seed1 -0.0020 (90% up +0.0006) | harm cells 0/45 | decision playoff@preseason: slope null 2.08 arm 1.22 contrast -0.865 [10% -1.004, 90% -0.755]
t1.1           pooled dLL +0.0027 | disc -0.0030 check +0.0094 | best season removed +0.0040 | worst cell second quarter/top6 +0.0261 (90% up +0.0415) | harm cells 28/45 | decision playoff@preseason: slope null 2.08 arm 1.22 contrast -0.865 [10% -1.004, 90% -0.755]
t3.3           pooled dLL +0.0039 | disc +0.0078 check -0.0007 | best season removed +0.0048 | worst cell preseason/playoff +0.0243 (90% up +0.0293) | harm cells 44/45 | decision playoff@preseason: slope null 2.08 arm 2.90 contrast +0.811 [10% +0.727, 90% +0.900]
f0.5_t2.2      pooled dLL +0.0009 | disc -0.0004 check +0.0024 | best season removed +0.0012 | worst cell third quarter/top6 +0.0052 (90% up +0.0104) | harm cells 21/45 | decision playoff@preseason: slope null 2.08 arm 2.08 contrast +0.000 [10% +0.000, 90% +0.000]
f0.8_t2.2      pooled dLL +0.0016 | disc -0.0004 check +0.0039 | best season removed +0.0021 | worst cell third quarter/top6 +0.0092 (90% up +0.0169) | harm cells 22/45 | decision playoff@preseason: slope null 2.08 arm 2.08 contrast +0.000 [10% +0.000, 90% +0.000]
```
Reproduction check (fails, stated plainly): the regenerated live null does NOT match the committed 5 Nov model/replay/nba_2023.csv (mean abs diff 0.02, max 0.30 on p_title; same with BT_ERA 0 and 2000 sims). Likely cause: the 6 Nov dated bug fix that dropped postponed originals and the Cup final from the simulated schedule (ab09000), unconfirmed. The regenerated null has preseason playoff slope 2.08 (stored 1.50). Arm-vs-null contrasts are internally paired and valid; linking them to the stored CSVs is not.
Result: TAU_PRE 1.0 (live 2.0) is the only arm that is better in every way scored: pooled -0.0018, discovery -0.0031, check -0.0002, best season removed -0.0015, 0 of 45 cells with an upper bound worse than +0.002, preseason playoff slope 2.08 -> 1.22 (toward 1, contrast -0.865 [-1.004, -0.755]). It reverses the 5 Nov-era WORKLOG choice of 2.0 (0.5965 -> 0.5613 preseason playoff LL) and contradicts the results-only run (where 1.0 was worse). Every other arm is worse or harmful. TEAM_TAU and fade arms are inert on the preseason market and worse pooled.

---
## Final rulings (DeepSeek relays 022-024; TypeSafe not consulted on these, rules were frozen first)
- AFL, NFL: no 2027 candidate. NBL: no decision-capable market. NHL: still to run (needs the Action; the gh token in this sandbox fails, so Claude cannot dispatch it).
- NBA: TAU_PRE 1.0 NOT named. The slope contrast (2.08 -> 1.22) is pooled, not on the check block (check-block gain -0.0002). The 5 Nov choice of 2.0 and today's 1.0 differ by equal size and opposite sign (cell 0.5965/0.5613 then, 0.5471/0.5783 now), so the 0.03 is an engine property, not a tau effect. Code at the 5 Nov commit gives the same mismatch to the stored 2023 CSV as HEAD, so the 6 Nov schedule fix is not the cause; the stored CSV's generator is unknown.
- Required before anything is named: identify the stored CSV's generator (data snapshot hash, flags, commit), reproduce row-level (bulk p in 0.05-0.95, sd of z about 1.2, max z < 3.5 at N 2000), then recompute the check-block slope contrast on that configuration. If near -0.86 on the reproduction the arm lands at about 0.64, past 1 (fail); below about -0.4 name it.
