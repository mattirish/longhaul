#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}/src"

WORKDIR="${LONGHAUL_REFERENCE_WORKDIR:-$(mktemp -d /tmp/longhaul-reference.XXXXXX)}"
SEGMENT_SIZE="${LONGHAUL_SEGMENT_SIZE:-256}"
LINK_BPS="${LONGHAUL_LINK_BPS:-2000}"
PROFILE="${LONGHAUL_REFERENCE_PROFILE:-default}"

SENDER="${WORKDIR}/sender"
RECEIVER="${WORKDIR}/receiver"
CHANGED_DIR="${WORKDIR}/changed-files"
ARTIFACT_ROOT="${WORKDIR}/artifact"
METRICS_PATH="${WORKDIR}/metrics.json"

git_init_repo() {
  local repo="$1"
  git init "${repo}" >/dev/null
  git -C "${repo}" config user.name "Longhaul Reference"
  git -C "${repo}" config user.email "longhaul@example.com"
}

airtime_seconds() {
  python3 - "$1" "$2" <<'PY'
import sys
bits = int(sys.argv[1]) * 8
bps = int(sys.argv[2])
print(bits / bps)
PY
}

prepare_fixture_default() {
  mkdir -p "${SENDER}/src" "${SENDER}/docs" "${SENDER}/notes"
  for i in $(seq 1 60); do
    cat >"${SENDER}/src/module_${i}.txt" <<EOF
module ${i}
line 1 base
line 2 base
line 3 base
line 4 base
EOF
  done
  for i in $(seq 1 12); do
    cat >"${SENDER}/docs/doc_${i}.md" <<EOF
# Document ${i}

Baseline text for document ${i}.
EOF
  done
  cat >"${SENDER}/notes/status.txt" <<'EOF'
baseline status
EOF
}

update_fixture_default() {
  mkdir -p "${CHANGED_DIR}/src" "${CHANGED_DIR}/docs" "${CHANGED_DIR}/notes"
  for i in $(seq 1 25); do
    cat >>"${SENDER}/src/module_${i}.txt" <<EOF
update line a for module ${i}
update line b for module ${i}
EOF
    cp "${SENDER}/src/module_${i}.txt" "${CHANGED_DIR}/src/module_${i}.txt"
  done
  for i in $(seq 61 68); do
    cat >"${SENDER}/src/module_${i}.txt" <<EOF
module ${i}
new file ${i}
payload line 1
payload line 2
EOF
    cp "${SENDER}/src/module_${i}.txt" "${CHANGED_DIR}/src/module_${i}.txt"
  done
  mv "${SENDER}/docs/doc_1.md" "${SENDER}/docs/doc_1_renamed.md"
  cp "${SENDER}/docs/doc_1_renamed.md" "${CHANGED_DIR}/docs/doc_1_renamed.md"
  cat >>"${SENDER}/notes/status.txt" <<'EOF'
sender update applied
EOF
  cp "${SENDER}/notes/status.txt" "${CHANGED_DIR}/notes/status.txt"
}

case "${PROFILE}" in
  default) ;;
  *)
    echo "unsupported reference profile: ${PROFILE}" >&2
    exit 1
    ;;
esac

mkdir -p "${SENDER}" "${RECEIVER}" "${CHANGED_DIR}"
git_init_repo "${SENDER}"
prepare_fixture_default
git -C "${SENDER}" add .
git -C "${SENDER}" commit -m "base fixture" >/dev/null
BASE_COMMIT="$(git -C "${SENDER}" rev-parse HEAD)"

python3 -m longhaul.cli repo init --repo "${SENDER}" --node-id denver >/dev/null
REPO_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repo_id"])' "${SENDER}/.longhaul/config.json")"

git clone "${SENDER}" "${RECEIVER}" >/dev/null 2>&1
python3 -m longhaul.cli repo init --repo "${RECEIVER}" --node-id michigan --repo-id "${REPO_ID}" >/dev/null

update_fixture_default
git -C "${SENDER}" add .
git -C "${SENDER}" commit -m "reference update" >/dev/null
TARGET_COMMIT="$(git -C "${SENDER}" rev-parse HEAD)"

git -C "${SENDER}" diff --name-only "${BASE_COMMIT}" "${TARGET_COMMIT}" >"${WORKDIR}/changed-paths.txt"
tar -czf "${WORKDIR}/changed-files.tar.gz" -C "${CHANGED_DIR}" .
git -C "${SENDER}" bundle create "${WORKDIR}/update.bundle" HEAD "^${BASE_COMMIT}" >/dev/null

python3 -m longhaul.cli repo advertise --repo "${RECEIVER}" >"${WORKDIR}/advertise.json"
python3 -m longhaul.cli plan artifact \
  --repo "${SENDER}" \
  --advertisement "${WORKDIR}/advertise.json" \
  --target-ref HEAD \
  --output-dir "${ARTIFACT_ROOT}" \
  --segment-size "${SEGMENT_SIZE}" >/dev/null

ARTIFACT_DIR="$(find "${ARTIFACT_ROOT}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
MANIFEST_PATH="${ARTIFACT_DIR}/manifest.json"
PAYLOAD_PATH="${ARTIFACT_DIR}/payload.bundle"

python3 -m longhaul.cli send offer --manifest "${MANIFEST_PATH}" --message "${WORKDIR}/offer.lhm" >/dev/null

SEGMENT_COUNT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["segment_count"])' "${MANIFEST_PATH}")"
mkdir -p "${WORKDIR}/segment-messages"
for i in $(seq 0 $((SEGMENT_COUNT - 1))); do
  python3 -m longhaul.cli send segment \
    --artifact-dir "${ARTIFACT_DIR}" \
    --index "${i}" \
    --output "${WORKDIR}/segments-${i}.json" \
    --spool "${WORKDIR}/segment-messages" >/dev/null
done

python3 - "$WORKDIR" "$BASE_COMMIT" "$TARGET_COMMIT" "$SEGMENT_SIZE" "$LINK_BPS" <<'PY' >"${METRICS_PATH}"
import json
import os
import sys
from pathlib import Path

workdir = Path(sys.argv[1])
base_commit = sys.argv[2]
target_commit = sys.argv[3]
segment_size = int(sys.argv[4])
link_bps = int(sys.argv[5])

manifest = json.loads((next((workdir / "artifact").glob("*/manifest.json"))).read_text())
segment_envelopes = sorted((workdir / "segment-messages" / "outgoing").glob("*-SEGMENT.lhm"))

def size(path: Path) -> int:
    return path.stat().st_size

def airtime(byte_count: int) -> float:
    return (byte_count * 8) / link_bps

changed_paths = [line for line in (workdir / "changed-paths.txt").read_text().splitlines() if line]
changed_tar = workdir / "changed-files.tar.gz"
bundle = workdir / "update.bundle"
payload = next((workdir / "artifact").glob("*/payload.bundle"))

metrics = {
    "profile": "default",
    "base_commit": base_commit,
    "target_commit": target_commit,
    "segment_size": segment_size,
    "link_bps": link_bps,
    "changed_path_count": len(changed_paths),
    "comparison": {
        "naive_changed_tar_gz": {
            "bytes": size(changed_tar),
            "estimated_airtime_seconds": airtime(size(changed_tar)),
        },
        "git_bundle": {
            "bytes": size(bundle),
            "estimated_airtime_seconds": airtime(size(bundle)),
        },
        "longhaul_payload_bundle": {
            "bytes": size(payload),
            "estimated_airtime_seconds": airtime(size(payload)),
        },
        "longhaul_protocol_messages": {
            "offer_bytes": size(workdir / "offer.lhm"),
            "segment_message_bytes": sum(size(path) for path in segment_envelopes),
            "message_count": 1 + len(segment_envelopes),
            "estimated_airtime_seconds": airtime(size(workdir / "offer.lhm") + sum(size(path) for path in segment_envelopes)),
        },
    },
    "manifest": {
        "artifact_id": manifest["artifact_id"],
        "payload_size": manifest["payload_size"],
        "segment_count": manifest["segment_count"],
        "target_ref": manifest["target_ref"],
    },
}

print(json.dumps(metrics, indent=2))
PY

cat "${METRICS_PATH}"
