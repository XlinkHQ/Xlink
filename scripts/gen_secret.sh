#!/usr/bin/env bash
# Generate a JWT secret key suitable for XLINK_JWT_SECRET_KEY.
set -euo pipefail
openssl rand -hex 32
