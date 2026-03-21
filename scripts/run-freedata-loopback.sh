#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="${ROOT}/src"
export PYTHONPATH

WORKDIR="${LONGHAUL_LOOPBACK_WORKDIR:-$(mktemp -d /tmp/longhaul-loopback.XXXXXX)}"
HOST="${FREEDATA_HOST:-127.0.0.1}"
CMD_PORT="${FREEDATA_CMD_PORT:-9100}"
DATA_PORT="${FREEDATA_DATA_PORT:-9101}"
SEGMENT_SIZE="${LONGHAUL_SEGMENT_SIZE:-32}"
INBOX="${FREEDATA_LOOPBACK_INBOX:-/tmp/freedata_socket_inbox}"
DAEMON_LOG="${WORKDIR}/freedata.log"

cleanup() {
  if [[ -n "${DAEMON_PID:-}" ]] && kill -0 "${DAEMON_PID}" 2>/dev/null; then
    kill "${DAEMON_PID}" 2>/dev/null || true
    wait "${DAEMON_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

rm -rf "${INBOX}"
mkdir -p "${INBOX}"

"${ROOT}/scripts/start-freedata-local.sh" >"${WORKDIR}/freedata-config-path.txt" 2>"${DAEMON_LOG}" &
DAEMON_PID=$!

for _ in $(seq 1 30); do
  if python3 -m longhaul.cli transport probe \
    --transport freedata \
    --root "${WORKDIR}/transport" \
    --station-id denver \
    --peer-id michigan \
    --host "${HOST}" \
    --cmd-port "${CMD_PORT}" \
    --data-port "${DATA_PORT}" \
    --session-mode data-only >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

python3 -m longhaul.cli transport probe \
  --transport freedata \
  --root "${WORKDIR}/transport" \
  --station-id denver \
  --peer-id michigan \
  --host "${HOST}" \
  --cmd-port "${CMD_PORT}" \
  --data-port "${DATA_PORT}" \
  --session-mode data-only >/dev/null

mkdir -p "${WORKDIR}/sender" "${WORKDIR}/receiver" "${WORKDIR}/messages" \
  "${WORKDIR}/sender-spool" "${WORKDIR}/receiver-spool" "${WORKDIR}/transport"

git init "${WORKDIR}/sender" >/dev/null
git -C "${WORKDIR}/sender" config user.name "Longhaul Test"
git -C "${WORKDIR}/sender" config user.email "longhaul@example.com"
printf 'alpha\n' >"${WORKDIR}/sender/hello.txt"
git -C "${WORKDIR}/sender" add hello.txt
git -C "${WORKDIR}/sender" commit -m "base" >/dev/null

python3 -m longhaul.cli repo init --repo "${WORKDIR}/sender" --node-id denver >/dev/null
REPO_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repo_id"])' "${WORKDIR}/sender/.longhaul/config.json")"

git clone "${WORKDIR}/sender" "${WORKDIR}/receiver" >/dev/null 2>&1
python3 -m longhaul.cli repo init --repo "${WORKDIR}/receiver" --node-id michigan --repo-id "${REPO_ID}" >/dev/null

printf 'bravo\ncharlie\ndelta\necho\nfoxtrot\n' >>"${WORKDIR}/sender/hello.txt"
git -C "${WORKDIR}/sender" commit -am "update" >/dev/null

python3 -m longhaul.cli repo advertise --repo "${WORKDIR}/receiver" >"${WORKDIR}/advertise.json"
python3 -m longhaul.cli plan artifact \
  --repo "${WORKDIR}/sender" \
  --advertisement "${WORKDIR}/advertise.json" \
  --target-ref HEAD \
  --output-dir "${WORKDIR}/artifact" \
  --segment-size "${SEGMENT_SIZE}" >/dev/null

ARTIFACT_DIR="$(find "${WORKDIR}/artifact" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
ARTIFACT_ID="$(basename "${ARTIFACT_DIR}")"

python3 -m longhaul.cli send offer \
  --manifest "${ARTIFACT_DIR}/manifest.json" \
  --message "${WORKDIR}/messages/offer.json" >/dev/null

python3 -m longhaul.cli transport dispatch \
  --transport freedata \
  --root "${WORKDIR}/transport" \
  --message "${WORKDIR}/messages/offer.json" \
  --station-id denver \
  --peer-id michigan \
  --host "${HOST}" \
  --cmd-port "${CMD_PORT}" \
  --data-port "${DATA_PORT}" \
  --session-mode data-only >/dev/null
python3 -m longhaul.cli transport loopback-import \
  --inbox "${INBOX}" \
  --spool "${WORKDIR}/receiver-spool" >/dev/null

SEGMENT_COUNT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["segment_count"])' "${ARTIFACT_DIR}/manifest.json")"

for i in $(seq 0 $((SEGMENT_COUNT - 1))); do
  python3 -m longhaul.cli send segment \
    --artifact-dir "${ARTIFACT_DIR}" \
    --index "${i}" \
    --output "${WORKDIR}/messages/segment-${i}.json" \
    --spool "${WORKDIR}/sender-spool" >/dev/null
done

for msg in "${WORKDIR}/sender-spool"/outgoing/*-SEGMENT.json; do
  python3 -m longhaul.cli transport dispatch \
    --transport freedata \
    --root "${WORKDIR}/transport" \
    --message "${msg}" \
    --station-id denver \
    --peer-id michigan \
    --host "${HOST}" \
    --cmd-port "${CMD_PORT}" \
    --data-port "${DATA_PORT}" \
    --session-mode data-only >/dev/null
  python3 -m longhaul.cli transport loopback-import \
    --inbox "${INBOX}" \
    --spool "${WORKDIR}/receiver-spool" >/dev/null
done

OFFER_PATH="$(find "${WORKDIR}/receiver-spool/incoming" -maxdepth 1 -type f -name '*-OFFER.json' | head -n 1)"
python3 -m longhaul.cli receive offer --repo "${WORKDIR}/receiver" --message "${OFFER_PATH}" >/dev/null

for msg in "${WORKDIR}/receiver-spool"/incoming/*-SEGMENT.json; do
  python3 -m longhaul.cli receive segment --repo "${WORKDIR}/receiver" --message "${msg}" >/dev/null
done

python3 -m longhaul.cli receive complete \
  --repo "${WORKDIR}/receiver" \
  --artifact-id "${ARTIFACT_ID}" \
  --spool "${WORKDIR}/receiver-spool" >/dev/null
python3 -m longhaul.cli receive apply \
  --repo "${WORKDIR}/receiver" \
  --artifact-id "${ARTIFACT_ID}" \
  --spool "${WORKDIR}/receiver-spool" >/dev/null

python3 - <<PY
import json
import subprocess
from pathlib import Path

workdir = Path("${WORKDIR}")
manifest = json.loads((workdir / "artifact" / "${ARTIFACT_ID}" / "manifest.json").read_text())
receive_state = json.loads((workdir / "receiver" / ".longhaul" / "receive-state.json").read_text())
receiver_head = subprocess.check_output(
    ["git", "-C", str(workdir / "receiver"), "rev-parse", "HEAD"],
    text=True,
).strip()
result = {
    "workdir": str(workdir),
    "daemon_log": str(workdir / "freedata.log"),
    "artifact_id": manifest["artifact_id"],
    "segment_count": manifest["segment_count"],
    "target_commit": manifest["target_commit"],
    "receiver_head": receiver_head,
    "receiver_matches_target": receiver_head == manifest["target_commit"],
    "receiver_spool_count": len(list((workdir / "receiver-spool" / "incoming").glob("*.json"))),
    "loopback_inbox_count": len(list(Path("${INBOX}").glob("*.json"))),
    "receive_state": receive_state,
}
print(json.dumps(result, indent=2))
PY
