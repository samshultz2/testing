#!/usr/bin/env bash
# Prepare the environment so tests and the app can run.
# Safe to re-run; failures are non-fatal so a session never gets blocked.
set -u

echo "[setup] Installing Python dependencies..."
pip install -q -r requirements.txt 2>/dev/null || pip install -q -r requirements.txt || true

# OCR engine for the result-scanning feature / tests.
if ! command -v tesseract >/dev/null 2>&1; then
    echo "[setup] Installing Tesseract OCR..."
    (apt-get update -y -q && apt-get install -y -q tesseract-ocr tesseract-ocr-osd) 2>/dev/null \
        || (sudo apt-get update -y -q && sudo apt-get install -y -q tesseract-ocr tesseract-ocr-osd) 2>/dev/null \
        || echo "[setup] Could not install Tesseract automatically (OCR features will be limited)."
fi

# Ensure runtime folders exist.
mkdir -p uploads instance 2>/dev/null || true

echo "[setup] Done."
