#!/bin/bash
# Full run for research/NBA_JOINT_TEAM_PLAYER_RULE.md (frozen code). Usage: bash research/nba_joint_run.sh  (2 CPUs: arms run two at a time)
set -e
cd "$(dirname "$0")/.."
export NBA_STINTS=${NBA_STINTS:-/home/claude/nbapbp/jstints}
OUT=model/replay/nba_joint
mkdir -p $OUT
[ -f model/replay/nba_joint_params.json ] || python3 research/nba_joint_select.py
BASE="BT_PO_GAMES=1 BT_SAVE_RATING=1"
L="BT_FULL=1 BT_PO_K=1 BT_PO_GAMMA=1.5 BT_PO_LASTPO=1"     # the live model's replay settings (A0)
run() { arm=$1; shift; mkdir -p $OUT/$arm; env $BASE "$@" BT_OUTDIR=$OUT/$arm python3 research/replay_nba.py 2016 2026 > $OUT/$arm.log 2>&1; echo "$arm done"; }
run A0 $L &
run A2 BT_JOINT=1 &
wait
run A1 $L BT_ROSTER=v2 &
run A2_noscale BT_JOINT=1 BT_JOINT_SCALE=0 &
wait
run A1_noleak $L BT_ROSTER=v2 BT_FULL_NOLEAK=1 &
run A2_noleak BT_JOINT=1 BT_FULL_NOLEAK=1 &
wait
python3 research/nba_joint_score.py
