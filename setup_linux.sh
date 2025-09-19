#!/bin/bash
set -e

curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
./.venv/bin/python3 script.py
source ./.venv/bin/activate