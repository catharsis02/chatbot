#!/bin/bash
echo "Setting up Linux environment..."
set -e

echo "Setting up Package Manager..."
curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync

echo "Downloading NLTK data..."
./.venv/bin/python3 script.py

echo "Setting up Python Virtual Environment..."
echo "Activate virtual environment using the command:"
echo "source ./.venv/bin/activate"