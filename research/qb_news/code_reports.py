"""Code each reported QB absence expectation (GPT's 2018-2025 list) into an absence range, from the report wording only.
Rule: research/NFL_QB_NEWS_RULE.md. Output: research/qb_news/qb_reports_coded.csv, one row per report
(case, report date, wording, code, lo, hi, unit). Units: G = team games, W = weeks, M = months, S = rest of season,
C = cleared / returning (no further absence beyond the next game), IR = injured-reserve minimum (set by season), NONE = no usable info.
The mapping is fixed in the rule; this script applies it mechanically. Outcome columns are never read.
"""
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11}


def n(x):
    return int(x) if x.isdigit() else NUM[x.lower()]


W = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven)"


def code(text):
    t = text.lower().replace("–", "-").replace("—", "-")
    # rest of season (and "full return in the 2023 season")
    if re.search(r"season[- ]ending|rest of (the )?(\d{4} )?season|ending his (\d{4} )?season|remainder of (the )?(\d{4} )?(season|year)|out for (the )?(season|year)|season (appears to be )?over|"
                 r"season ends|won't return this season|season is now finished|season officially ended|return in the \d{4} season|shut down .* rest of", t) and "isn't season ending" not in t:
        return "S", None, None
    if "isn't season ending" in t:
        return "G", 1, 4
    if re.search(r"healthy enough to practice and play|(?<!not )cleared for contact", t):
        return "C", 0, 1
    m = re.search(W + r"(?:-| to |-to-)" + W + r"(?:-| )?months?", t)
    if m:
        return "M", n(m.group(1)), n(m.group(2))
    m = re.search(r"(?:at least )?" + W + r" months", t)
    if m:
        lo = n(m.group(1))
        return "M", lo, lo + (1 if "at least" in t else 0)
    m = re.search(W + r"(?:-| to |-to-)" + W + r"(?:-| )?weeks?", t)
    if m:
        lo, hi = n(m.group(1)), n(m.group(2))
        return "W", lo, hi + (2 if "minimum" in t else 0)
    m = re.search(r"(at least|a minimum of|minimum of) " + W + r" weeks", t)
    if m:
        lo = n(m.group(2))
        return "W", lo, lo + 2
    m = re.search(W + r"(?:-| )weeks?", t)
    if m and re.search(r"could sideline|more likely timeframe|could do nothing", t):
        lo = n(m.group(1))
        return "W", lo, lo
    m = re.search(r"suspended (?:for )?(?:the first )?" + W + r" games", t)
    if m:
        k = n(m.group(1))
        return "G", k, k
    m = re.search(r"(?:at least|sit at least|miss at least) (?:the next )?" + W + r"(?: of the remaining \w+)? games", t) or re.search(r"at least next " + W + r" games", t)
    if m:
        k = n(m.group(1))
        return "G", k, k + 2
    m = re.search(r"at least " + W + r" (?:or " + W + r" )?games", t) or re.search(r"miss at least " + W + r" or " + W + r" games", t)
    if m:
        return "G", n(m.group(1)), (n(m.group(2)) if m.lastindex and m.group(m.lastindex) else n(m.group(1))) + 1
    m = re.search(r"sit for the remaining " + W + r" games", t)
    if m:
        k = n(m.group(1))
        return "G", k, k
    m = re.search(r"out until at least week (\d+)", t)
    if m:
        return "UNTILWEEK", int(m.group(1)), int(m.group(1)) + 2
    if re.search(r"injured reserve|reserve/injured|on ir\b|heading to injured reserve", t):
        return "IR", None, None
    if re.search(r"pup list", t):
        return "PUP", None, None
    if re.search(r"week[- ]to[- ]week|multiple weeks|several weeks|multi-game|several games|miss some time|expected to miss multiple|potentially ending", t):
        return "G", 2, 4
    if re.search(r"three months to recover", t):
        return "M", 3, 3
    if re.search(r"not found", t):
        return "NONE", None, None
    # explicit short-term wording
    if re.search(r"day[- ]to[- ]day|day by day|questionable|doubtful|ruled out|will not (play|start)|out for sunday|out vs\.|out for christmas|"
                 r"wouldn't be available|not expected to be available|could miss|status (for week \d+ |for the upcoming week )?(in question|in doubt|uncertain)|"
                 r"concussion protocol|highly unlikely|very likely|not cleared for contact|being monitored|wait and see|one more week", t):
        return "D", 1, 2
    # no usable duration (no timeline, no timetable, indefinitely, no update, other): a first report means [1, 2] games; a revision is ignored
    return "U", 1, 2


def reports(df):
    rows = []
    for i, r in df.iterrows():
        first = str(r.iloc[2])
        m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", first)
        if m:
            rows.append(dict(case=i, kind="first", date=m.group(1), wording=first[:240], **dict(zip(("code", "lo", "hi"), code(first)))))
        rev = str(r.iloc[3])
        for part in re.split(r";\s*(?=\d{4}-\d{2}-\d{2})", rev):
            m = re.match(r"\s*(\d{4}-\d{2}-\d{2}):\s*(.*)", part)
            if m:
                q = re.search(r'"([^"]+)"', m.group(2))
                txt = q.group(1) if q else m.group(2)
                rows.append(dict(case=i, kind="revision", date=m.group(1), wording=txt[:240], **dict(zip(("code", "lo", "hi"), code(txt)))))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    d = pd.read_csv(os.path.join(HERE, "gpt_qb_reports_2018_2025.csv"), encoding="utf-8-sig")
    R = reports(d)
    # version 2 (27 Oct 2026, GPT review): primary uses only bounded statements - season-ending, a stated range or single figure in weeks or
    # months (not "at least" or "minimum"), a fixed suspension or "sit for the remaining N games". Everything else is a sensitivity input.
    lowb = R.wording.str.contains(r"at least|minimum", case=False, regex=True)
    R["bounded"] = (R.code == "S") | (R.code.isin(["W", "M"]) & ~lowb) | ((R.code == "G") & R.wording.str.contains(r"suspended|sit for the remaining", case=False, regex=True))
    R.to_csv(os.path.join(HERE, "qb_reports_coded.csv"), index=False)
    print(R.code.value_counts().to_dict(), len(R))
