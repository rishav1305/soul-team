#!/usr/bin/env bash
# soul-time-beacon.sh — Broadcasts mode transitions to all agents via clawteam inbox.
#
# Launched by soul-team.sh alongside soul-heartbeat.sh.
# Checks mode every 5 minutes; only broadcasts when mode changes (4x/day max).
# Mode boundaries (IST): MORNING 06-10, AFTERNOON 11-16, EVENING 17-21, NIGHT 22-05.

set -euo pipefail

TEAM="soul-team"
LAST_MODE=""
CLAWTEAM="$HOME/.local/bin/clawteam"

get_soul_time_block() {
    local IST_TIME DATE DAY TIME HOUR WEEK DOW MODE

    IST_TIME=$(TZ=Asia/Kolkata date +"%Y-%m-%dT%H:%M:%S+05:30")
    DATE=$(TZ=Asia/Kolkata date +"%Y-%m-%d")
    DAY=$(TZ=Asia/Kolkata date +"%A")
    TIME=$(TZ=Asia/Kolkata date +"%H:%M")
    HOUR=$(TZ=Asia/Kolkata date +"%H" | sed "s/^0//")
    WEEK=$(TZ=Asia/Kolkata date +"%V")
    DOW=$(TZ=Asia/Kolkata date +"%u")

    MODE="NIGHT"
    if   [ "$HOUR" -ge 6  ] && [ "$HOUR" -lt 11 ]; then MODE="MORNING"
    elif [ "$HOUR" -ge 11 ] && [ "$HOUR" -lt 17 ]; then MODE="AFTERNOON"
    elif [ "$HOUR" -ge 17 ] && [ "$HOUR" -lt 22 ]; then MODE="EVENING"
    fi

    printf "[SOUL-TIME]\ndatetime: %s\ndate: %s\nday: %s\ntime: %s IST\nmode: %s\nweek_number: %s\nday_of_week: %s\n[/SOUL-TIME]" \
        "$IST_TIME" "$DATE" "$DAY" "$TIME" "$MODE" "$WEEK" "$DOW"
}

get_current_mode() {
    local HOUR
    HOUR=$(TZ=Asia/Kolkata date +"%H" | sed "s/^0//")
    if   [ "$HOUR" -ge 6  ] && [ "$HOUR" -lt 11 ]; then echo "MORNING"
    elif [ "$HOUR" -ge 11 ] && [ "$HOUR" -lt 17 ]; then echo "AFTERNOON"
    elif [ "$HOUR" -ge 17 ] && [ "$HOUR" -lt 22 ]; then echo "EVENING"
    else echo "NIGHT"
    fi
}

echo "[time-beacon] Started. PID $$. Checking mode transitions every 5 minutes."

# Capture current mode at boot so first check does not broadcast a spurious transition.
LAST_MODE=$(get_current_mode)
echo "[time-beacon] Current mode at boot: ${LAST_MODE}"

while true; do
    sleep 300

    MODE=$(get_current_mode)

    if [ "$MODE" != "$LAST_MODE" ]; then
        TIME_CTX=$(get_soul_time_block)
        MSG="[TIME-UPDATE] Mode transition: ${LAST_MODE} -> ${MODE}

${TIME_CTX}

Adjust your work cadence accordingly. See your Time Awareness section for mode-specific behavior."

        "$CLAWTEAM" inbox broadcast "$TEAM" "$MSG" --from system 2>/dev/null && \
            echo "[time-beacon] Broadcast: ${LAST_MODE} -> ${MODE}" || \
            echo "[time-beacon] WARNING: broadcast failed for ${LAST_MODE} -> ${MODE}"

        LAST_MODE="$MODE"
    fi
done
