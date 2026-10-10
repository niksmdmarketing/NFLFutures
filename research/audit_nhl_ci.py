"""CI wrapper: NHL part of research/audit_live_effects.py (needs the NHL API). Usage: python research/audit_nhl_ci.py <market-data dir>"""
import os
import subprocess
import sys

out = os.path.join(sys.argv[1], "research", "audit")
os.makedirs(out, exist_ok=True)
env = dict(os.environ, AUDIT_ONLY="nhl_live")
subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_live_effects.py"), "fetch",
                os.path.join(out, "nhl_live_effects.json")], env=env, check=True)
