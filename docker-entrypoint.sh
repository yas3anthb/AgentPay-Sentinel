#!/usr/bin/env bash
# Ensures a delegation keypair exists before any service starts. In a real
# deployment these live in a KMS and this script would not exist.
set -euo pipefail
python scripts/gen_keys.py
exec "$@"
