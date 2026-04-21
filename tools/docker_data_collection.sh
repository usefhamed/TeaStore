#!/bin/sh

# Usage: ./tools/docker_data_collection.sh [output_file] [interval_seconds]

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
OUTPUT_FILE="${1:-$SCRIPT_DIR/data/exp_1_output.json}"
INTERVAL="1"

echo "Writing docker stats to: $OUTPUT_FILE"
echo "Sample interval: ${INTERVAL}s"

OUTPUT_DIR="$(dirname "$OUTPUT_FILE")"
mkdir -p "$OUTPUT_DIR" || exit 1
touch "$OUTPUT_FILE" || exit 1

echo "Authenticating sudo once (you may be prompted)..."
if ! sudo -v; then
    echo "Failed to authenticate sudo." >&2
    exit 1
fi

# Sample stats as newline-delimited JSON while the container is running.
while true; do
    STATS_OUTPUT="$(sudo -n docker stats --no-stream --format "json" 2>/dev/null)"
    if [ $? -ne 0 ]; then
        echo "Failed to collect docker stats. Check docker permissions and that Docker daemon is running." >&2
        exit 1
    fi

    if [ -n "$STATS_OUTPUT" ]; then
        SAMPLE_TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        printf '%s\n' "$STATS_OUTPUT" | while IFS= read -r line; do
            printf '{"Timestamp":"%s",%s\n' "$SAMPLE_TS" "${line#\{}" >> "$OUTPUT_FILE"
        done
    else
        echo "No running containers at this sample." >&2
    fi

    # sleep "$INTERVAL"
done