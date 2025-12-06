#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=".env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Creating $ENV_FILE from .env.example"
  cp .env.example "$ENV_FILE"
fi

if ! grep -q '^SECRET_KEY=' "$ENV_FILE" || [[ -z "$(grep '^SECRET_KEY=' "$ENV_FILE" | cut -d'=' -f2-)" ]]; then
  echo "Generating SECRET_KEY"
  SECRET=$(python - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)
  if grep -q '^SECRET_KEY=' "$ENV_FILE"; then
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET/" "$ENV_FILE"
  else
    printf "\nSECRET_KEY=%s\n" "$SECRET" >> "$ENV_FILE"
  fi
fi

echo "Done. Review $ENV_FILE and restart services."

