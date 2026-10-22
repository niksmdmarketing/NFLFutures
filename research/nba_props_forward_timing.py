"""GitHub-recorded timing of the NBA props forward runs (research/NBA_MINUTES_M2B_RULE.md).
Run/step times are diagnostic only. Eligibility requires the first server-recorded push
whose head contains the forecast's adding commit, at or before its cutoff.
Usage (Actions, GH_TOKEN set): python research/nba_props_forward_timing.py <archive_dir>
"""
import datetime as dt
import json
import os
import sys
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "niksmdmarketing/NFLFutures")


def api(path):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}", headers={
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main(archive):
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, page = [], 1
    while True:
        js = api(f"actions/workflows/nba-props-forward.yml/runs?per_page=100&page={page}&created=>={since}")
        runs = js.get("workflow_runs", [])
        for r in runs:
            rec = dict(run_id=r["id"], event=r["event"], status=r["status"], conclusion=r["conclusion"], created_at=r["created_at"],
                       run_started_at=r.get("run_started_at"), updated_at=r["updated_at"], head_sha=r["head_sha"])
            try:
                for j in api(f"actions/runs/{r['id']}/jobs")["jobs"]:
                    for st in j.get("steps", []):
                        if st["name"] in ("Forecast", "Save", "Forecast loop"):
                            key = st["name"].lower().replace(" ", "_")
                            rec[key + "_completed_at"] = st.get("completed_at")
                            rec[key + "_conclusion"] = st.get("conclusion")
            except Exception as e:  # noqa: BLE001
                rec["jobs_error"] = repr(e)[:200]
            out.append(rec)
        if len(runs) < 100:
            break
        page += 1
    # server-recorded pushes to the archive branch (GitHub repository activity): the time GitHub received each push and the commit it
    # moved the branch to. A forecast file is archived at the first push whose new head contains the commit that added the file.
    pushes = []
    try:
        page = 1
        while True:
            activities = api(f"activity?ref=forecast-archive&activity_type=push&per_page=100&time_period=week&page={page}")
            for a in activities:
                pushes.append(dict(timestamp=a.get("timestamp"), before=a.get("before"), after=a.get("after"), actor=(a.get("actor") or {}).get("login")))
            if len(activities) < 100:
                break
            page += 1
    except Exception as e:  # noqa: BLE001
        pushes.append(dict(error=repr(e)[:200]))
    out = dict(runs=out, pushes=pushes)
    d = os.path.join(archive, "nba", "props_forward", "timing")
    os.makedirs(d, exist_ok=True)
    fn = os.path.join(d, dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%MZ") + ".json")
    with open(fn, "w") as fh:
        json.dump(out, fh, indent=1)
    print(fn, len(out["runs"]), len(out["pushes"]))


if __name__ == "__main__":
    main(sys.argv[1])
