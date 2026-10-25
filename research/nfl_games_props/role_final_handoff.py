"""Final handoff including the separately labelled actual-role-change diagnostic."""
import json,hashlib,zipfile
from pathlib import Path
from role_test import DEST,utc

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    dest=DEST/'FINAL_HANDOFF.json'
    if dest.exists():raise FileExistsError(dest)
    diag=json.loads((DEST/'OUTCOME_ROLE_DIAGNOSTIC.json').read_text())
    changed=diag['groups']['True']
    intro=f'''# Final verdict: role separation built, starter changes not yet solved

QB attempts improve 4.0% on conditional distribution score and pass the written overall research screen. Receiver redistribution improves only 0.05%, wins 2/4 seasons, and fails. Neither is deployed.

**Important final diagnostic:** among {changed['n']} involved QB appearances where the QB actually became the primary passer after not being the preceding game's primary, the candidate's score is {changed['candidate']:.6f} versus {changed['baseline']:.6f}: about {100*(-changed['relative_gain']):.1f}% worse. This group is defined using outcomes and is diagnostic only, not a pregame group or adoption gate. It qualifies the overall pass: the new candidate does not demonstrate a fix to actual starter/takeover changes. Gains among all non-previous-primary QBs also include relief appearances and must not be presented as gains on takeovers specifically.

The small pregame group where the previous primary was reported Out/Doubtful did improve, but has only 35 involved QB appearances. Most of the broader actual-change problem remains: late benchings, starter confirmations, early in-game injuries and unseen QBs cannot be reliably inferred from historical usage alone. The most-attempts passer can also differ from the announced starter, so this is not an exact starter-change audit.

The evaluation candidate list contains the actual primary in roughly 93–95% of team-games that already have a QB candidate. Completely uncovered team-games are outside that denominator. This is a material coverage limitation.

**Decision:** preserve the current forecasts. Keep the new QB role model as a research candidate; do not describe it as a validated starter-change replacement. Retain the old reception model. A future dated expected-starter/roster integration should be tested under a new rule, not retrospectively fed actual starters. The scenario API is ready for a separately recorded, genuinely known or explicitly assumed primary role.

**Not an ability breakthrough:** this experiment keeps team passing volume fixed and does not add a new QB ability metric. For receivers it separates opportunity from the existing catch-rate estimate. It does not establish market profitability.

The complete initial research report follows. Its PASS refers to the prewritten research screen, not production adoption.

---

'''
    report=DEST/'REPORT_FINAL.md';report.write_text(intro+(DEST/'REPORT.md').read_text(encoding='utf-8'),encoding='utf-8')
    src=Path(__file__).parent;package=DEST/'ROLE_FOUNDATION_CODE_ONLY_FINAL.zip'
    with zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.iterdir()):
            if p.is_file() and p.suffix in ('.py','.md'):z.write(p,'research/nfl_games_props/'+p.name)
    record=dict(sealed_at=utc(),earlier_handoff_manifest_sha256=sha(DEST/'HANDOFF_MANIFEST.json'),
        report_sha256=sha(report),code_package_sha256=sha(package),diagnostic_sha256=sha(DEST/'OUTCOME_ROLE_DIAGNOSTIC.json'),
        code_sha256={p.name:sha(p) for p in src.iterdir() if p.is_file() and p.suffix in ('.py','.md')},
        live_model_unchanged=True,site_unchanged=True,published=False)
    with dest.open('x') as f:json.dump(record,f,indent=2)
    print(str(report))

if __name__=='__main__':main()
