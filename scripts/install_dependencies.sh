#!/usr/bin/env bash
# Simple helper to install Python dependencies for Payroll Indonesia
echo "Installing Python dependencies..."
python -m pip install --upgrade pip
if [ -f requirements.txt ]; then
    python -m pip install -r requirements.txt
fi
