#!/bin/bash
set -e

curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
source ./.venv/bin/activate
./.venv/bin/python3 script.py