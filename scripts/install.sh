#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: bash $0 PACKAGE.whl REQUIREMENTS.txt" >&2
    exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
    echo "Install uv and make it available on your PATH first." >&2
    exit 1
fi
for artifact in "$@"; do
    if [[ ! -f $artifact ]]; then
        echo "Artifact not found: $artifact" >&2
        exit 1
    fi
done

wheel=$(realpath -- "$1")
requirements=$(realpath -- "$2")
mkdir -p /opt/decky-proxy
cd /opt/decky-proxy

if [[ ! -x .venv/bin/python ]]; then
    uv venv --python 3.14.8 .venv
fi
uv pip sync --python /opt/decky-proxy/.venv/bin/python --require-hashes "$requirements"
uv pip install --python /opt/decky-proxy/.venv/bin/python --no-deps --reinstall "$wheel"
uv pip check --python /opt/decky-proxy/.venv/bin/python
/opt/decky-proxy/.venv/bin/python -c \
    'from importlib.metadata import version; print("Installed decky-proxy " + version("decky-proxy"))'
