"""Reproducibility gate (projexions learning; TypeSafe 85%). write: record code commit, BT_/NHL_/MLB_ settings, argv and SHA-256 of
input files next to a replay's CSVs. check: re-run the recorded command in a temp folder and require byte-identical CSVs.
  python research/replay_manifest.py write <out_dir> <input files...> -- <command...>
  python research/replay_manifest.py check <out_dir>"""
import hashlib, json, os, subprocess, sys, tempfile


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write(out, inputs, cmd):
    m = {"commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
         "env": {k: v for k, v in os.environ.items() if k.startswith(("BT_", "NHL_", "MLB_"))}, "cmd": cmd,
         "inputs": {p: sha(p) for p in inputs}, "outputs": {f: sha(os.path.join(out, f)) for f in sorted(os.listdir(out)) if f.endswith(".csv")}}
    json.dump(m, open(os.path.join(out, "manifest.json"), "w"), indent=1)
    print("manifest", len(m["outputs"]), "csvs")


def check(out):
    m = json.load(open(os.path.join(out, "manifest.json")))
    bad = [p for p, h in m["inputs"].items() if not os.path.exists(p) or sha(p) != h]
    if bad:
        print("INPUTS CHANGED:", bad); return 1
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, **m["env"], "BT_OUTDIR": d}
        subprocess.run([c.replace("{OUT}", d) for c in m["cmd"]], env=env, check=True, capture_output=True)
        diff = [f for f, h in m["outputs"].items() if not os.path.exists(os.path.join(d, f)) or sha(os.path.join(d, f)) != h]
    print("REPRODUCED" if not diff else f"NOT REPRODUCED: {diff}")
    return 0 if not diff else 1


if __name__ == "__main__":
    if sys.argv[1] == "write":
        i = sys.argv.index("--"); sys.exit(write(sys.argv[2], sys.argv[3:i], sys.argv[i + 1:]))
    sys.exit(check(sys.argv[2]))
