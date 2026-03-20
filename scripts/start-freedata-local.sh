#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${FREEDATA_CONFIG_PATH:-/tmp/longhaul-freedata-live.ini}"
HOST="${FREEDATA_HOST:-127.0.0.1}"
API_PORT="${FREEDATA_API_PORT:-5100}"
CMD_PORT="${FREEDATA_CMD_PORT:-9100}"
DATA_PORT="${FREEDATA_DATA_PORT:-9101}"

cp "$ROOT/vendor/FreeDATA/freedata_server/config.ini.example" "$CONFIG_PATH"

python3 - <<PY
from configparser import ConfigParser

path = "$CONFIG_PATH"
p = ConfigParser()
p.read(path)
p["NETWORK"]["modemaddress"] = "$HOST"
p["NETWORK"]["modemport"] = "$API_PORT"
p["STATION"]["mycall"] = "XX1XXX"
p["GUI"]["auto_run_browser"] = "False"
p["SOCKET_INTERFACE"]["enable"] = "True"
p["SOCKET_INTERFACE"]["host"] = "$HOST"
p["SOCKET_INTERFACE"]["cmd_port"] = "$CMD_PORT"
p["SOCKET_INTERFACE"]["data_port"] = "$DATA_PORT"
p["RADIO"]["control"] = "disabled"
with open(path, "w") as handle:
    p.write(handle)
print(path)
PY

exec env FREEDATA_CONFIG="$CONFIG_PATH" arch -x86_64 "$ROOT/.venv-x86/bin/python" "$ROOT/vendor/FreeDATA/freedata_server/server.py"
