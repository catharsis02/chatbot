#!/bin/bash
set -e

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip (optional but recommended)
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Run the script
python script.py
