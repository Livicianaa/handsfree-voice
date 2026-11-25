#!/usr/bin/env bash
python3 -c '' 2>/dev/null && exec python3 "$(dirname "$0")/kur.py" "$@" || exec python "$(dirname "$0")/kur.py" "$@"
