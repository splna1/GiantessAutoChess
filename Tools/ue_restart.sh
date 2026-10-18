#!/bin/sh
# Relaunch the Tread editor (after a crash) and wait until Python remote execution answers.
# Usage: sh Tools/ue_restart.sh [max_wait_s]
UE="${UE_EDITOR:-G:/epicgame/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe}"
PROJ="E:/AI/Tread/Tread/Tread.uproject"
cd "$(dirname "$0")/.." || exit 1
taskkill //F //IM CrashReportClientEditor.exe >/dev/null 2>&1
if ! tasklist | grep -qi "UnrealEditor.exe"; then
    [ -f Saved/Logs/Tread.log ] && cp Saved/Logs/Tread.log "Saved/Logs/Tread_prev_$(date +%H%M%S).log"
    nohup "$UE" "$PROJ" >/dev/null 2>&1 &
    sleep 45
fi
MAX=${1:-400}
T=0
while [ $T -lt $MAX ]; do
    if python Tools/ue_run.py -c "print('ready')" >/dev/null 2>&1; then
        echo "editor ready (${T}s)"
        exit 0
    fi
    sleep 10
    T=$((T + 10))
done
echo "editor not ready after ${MAX}s"
exit 1
