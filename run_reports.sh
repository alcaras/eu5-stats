#!/bin/bash
# EU5 Report Generator - runs all reports and puts output in one folder

# Change to script directory
cd "$(dirname "$0")"

# Get most recent save file
SAVE_FILE=$(ls -t save/*.eu5 2>/dev/null | head -1)
if [ -z "$SAVE_FILE" ]; then
    echo "No .eu5 save file found in save/"
    exit 1
fi

# Get second most recent save file for comparison (if exists)
PREV_SAVE=$(ls -t save/*.eu5 2>/dev/null | head -2 | tail -1)
if [ "$PREV_SAVE" = "$SAVE_FILE" ]; then
    PREV_SAVE=""
fi

echo "Save file: $SAVE_FILE"
if [ -n "$PREV_SAVE" ]; then
    echo "Previous:  $PREV_SAVE"
fi

# Extract date from save file (first 100 lines)
SAVE_DATE=$(head -100 "$SAVE_FILE" | grep -o 'date=[0-9]*\.[0-9]*\.[0-9]*' | head -1 | cut -d= -f2 | tr '.' '_')
if [ -z "$SAVE_DATE" ]; then
    SAVE_DATE="unknown"
fi

# Create timestamped output folder
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="reports/${SAVE_DATE}_${TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"

echo "Output: $OUTPUT_DIR"
echo ""

# Run generate_report.py (text reports)
echo "=== Generating text reports ==="
if [ -n "$PREV_SAVE" ]; then
    python3 generate_report.py "$SAVE_FILE" -o "$OUTPUT_DIR" --no-timestamp --compare "$PREV_SAVE"
else
    python3 generate_report.py "$SAVE_FILE" -o "$OUTPUT_DIR" --no-timestamp
fi

echo ""

# Run compare_players_v2.py (charts)
echo "=== Generating charts ==="
python3 compare_players_v2.py "$SAVE_FILE" -o "$OUTPUT_DIR" --no-timestamp

echo ""
echo "=== Done ==="
echo "All reports saved to: $OUTPUT_DIR"
ls -la "$OUTPUT_DIR"
