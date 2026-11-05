"""Independent GitHub-server upload evidence for NFL props; never use commit clocks."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL).decode().strip()


def timestamp(value):
    t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("Receipt timestamp must have a timezone")
    return t.astimezone(dt.timezone.utc)


def identity(root):
    branch = git(root, "branch", "--show-current")
    if not branch.startswith("nfl-props-"):
        raise ValueError("Expected an NFL props archive branch")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        remote = git(root, "remote", "get-url", "origin")
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", remote)
        repo = m[1] if m else ""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Cannot establish GitHub repository identity")
    return repo, branch


def load_activity(root, evidence_file=None):
    repo, branch = identity(root)
    cache = Path(root) / "scores" / "github_push_activity.json"
    old = json.loads(cache.read_text()) if cache.exists() else {}
    if old and (old.get("repository") != repo or old.get("branch") != branch):
        raise ValueError("Receipt cache repository/branch mismatch")
    if evidence_file:
        doc = json.loads(Path(evidence_file).read_text())
        if isinstance(doc, dict) and (doc.get("repository") != repo or doc.get("branch") != branch):
            raise ValueError("Offline receipt evidence repository/branch mismatch")
        return doc.get("pushes", []) if isinstance(doc, dict) else doc
    pushes = old.get("pushes", [])
    url = ("https://api.github.com/repos/" + repo + "/activity?" +
           urllib.parse.urlencode(dict(ref=branch, activity_type="push", per_page=100, time_period="year")))
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "nfl-props-receipt-audit"}
    if token:
        headers["Authorization"] = "Bearer " + token
    fetched = []
    try:
        # Complete pagination; cached older server receipts are retained.
        for page in range(100):
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40) as response:
                fetched.extend(json.load(response))
                link = response.headers.get("Link", "")
            next_link = re.search(r'<([^>]+)>; rel="next"', link)
            if not next_link:
                break
            url = next_link[1]
            if urllib.parse.urlsplit(url).netloc != "api.github.com":
                raise ValueError("Unexpected receipt pagination host")
        else:
            raise ValueError("Receipt pagination incomplete")
    except Exception as exc:
        if not pushes:
            raise RuntimeError("No server push evidence available; refusing commit-time substitution") from exc
        print("Receipt API unavailable; using previously saved server evidence only.")
    by_key = {(p.get("timestamp"), p.get("after")): p for p in pushes}
    for p in fetched:
        by_key[(p.get("timestamp"), p.get("after"))] = {k: p.get(k) for k in
            ("timestamp", "after", "before", "ref", "id", "activity_type")}
    pushes = list(by_key.values())
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(repository=repo, branch=branch, pushes=pushes), indent=2), encoding="utf-8")
    tmp.replace(cache)
    return pushes


def build_receipts(root, pushes):
    """Map immutable snapshot paths to first independently received server timestamp."""
    root = Path(root)
    _, branch = identity(root)
    additions, commit = {}, None
    history = git(root, "log", "--format=COMMIT:%H", "--diff-filter=A", "--name-only", "HEAD", "--", "snapshots")
    for line in history.splitlines():
        if line.startswith("COMMIT:"):
            commit = line[7:]
        elif line:
            additions[line] = commit
    result = {}
    for push in pushes:
        if push.get("ref") != "refs/heads/" + branch or push.get("activity_type") != "push":
            continue
        try:
            received = timestamp(push["timestamp"])
            ancestors = set(git(root, "rev-list", push["after"]).splitlines())
        except (KeyError, ValueError, subprocess.CalledProcessError):
            continue
        for path, adding_commit in additions.items():
            if adding_commit in ancestors and (path not in result or received < result[path]):
                result[path] = received
    for path in list(result):
        edits = git(root, "log", "--format=%H", "HEAD", "--", path).splitlines()
        if len(edits) != 1:
            del result[path]  # the creation receipt does not prove modified bytes
    return result


def snapshot_valid(root, row):
    root = Path(root).resolve()
    path = (root / row["file"]).resolve()
    if not path.is_relative_to(root / "snapshots"):
        return False
    try:
        snap = json.loads(path.read_text())
        # The archive hashes the forecast before adding its self-identifying hash.
        body = {k: v for k, v in snap.items() if k != "forecast_sha256"}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        game = next(g for g in snap["games"] if g["game_id"] == row["game_id"])
        return (digest == row["sha256"] == snap.get("forecast_sha256") and
                timestamp(snap["generated_utc"]) == timestamp(row["generated_utc"]) and
                timestamp(game["kickoff_utc"]) == timestamp(row["kickoff_utc"]))
    except (OSError, KeyError, ValueError, StopIteration, TypeError):
        return False
