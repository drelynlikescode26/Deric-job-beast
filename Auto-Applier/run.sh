#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

COMMAND="$1"
if [[ -z "$COMMAND" || "$COMMAND" == "help" || "$COMMAND" == "-h" ]]; then
  cat <<'EOF'
Usage: ./run.sh <command>

Commands:
  scout      Run the scouter once with main.py --scout-now
  telegram   Start the Telegram bot listener
  executor   Run the executor directly
  main       Run main.py without extra arguments
  help       Show this help message
EOF
  exit 0
fi

case "$COMMAND" in
  scout)
    exec python3 main.py --scout-now
    ;;
  telegram)
    exec python3 telegram_bot.py
    ;;
  executor)
    exec python3 executor.py
    ;;
  warmup)
    if [[ -f ".env" ]]; then
      set -a
      source ".env"
      set +a
    fi
    PROFILE_DIR="${BROWSER_PROFILE_PATH:-$SCRIPT_DIR/chrome_profile}"
    CHROME_BIN="${CHROME_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
    echo "Warmup will use browser profile: $PROFILE_DIR"
    mkdir -p "$PROFILE_DIR"
    exec "$CHROME_BIN" --user-data-dir="$PROFILE_DIR"
    ;;
  main)
    exec python3 main.py
    ;;
  *)
    echo "Unknown command: $COMMAND"
    echo "Use ./run.sh help"
    exit 1
    ;;
esac
