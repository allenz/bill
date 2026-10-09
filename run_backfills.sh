#!/bin/bash
# Chain the backfills, one ECW job at a time (they share the one ESession
# state, so they must not run in parallel):
#   1. wait for the already-running backfill_teleweb_details.py (92-day run)
#   2. backfill_yellow_notes.py
#   3. backfill_teleweb_details.py 365 (the 92-day portion is a no-op via the
#      sqlite response cache; only the older encounters are fetched)
set -u
cd /srv/code/bill
FIRST_PID="$1"
echo "run_backfills: waiting for teleweb backfill pid $FIRST_PID to finish"
while kill -0 "$FIRST_PID" 2>/dev/null; do sleep 60; done
echo "run_backfills: $(date) teleweb 92d done, starting yellow notes"
python backfill_yellow_notes.py
echo "run_backfills: $(date) yellow notes done, starting teleweb 365d"
python backfill_teleweb_details.py 365
echo "run_backfills: $(date) all backfills finished"
