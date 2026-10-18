#!/bin/sh
# Print material/shader/python problems logged by the editor since line $1 of Saved/Logs/Tread.log
# Usage: sh Tools/ue_logcheck.sh <start_line>
LOG="$(dirname "$0")/../Saved/Logs/Tread.log"
tail -n +"${1:-1}" "$LOG" | grep -v "LogHttp" | grep -A2 -E "Failed to compile|LogMaterial: (Error|Warning)|LogShaderCompilers: (Error|Warning)|LogPython: (Error|Warning)|LogStaticMesh: (Error|Warning)|LogInterchange.*(Error|Warning)" | grep -v "^--" | awk '!s[substr($0,32)]++' | cut -c1-320 | head -${2:-40}
