#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/build.py
printf '\n완료: dist/AmebloStudio.app (배포용 서명/공증은 별도)\n'
