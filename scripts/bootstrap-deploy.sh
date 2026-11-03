#!/usr/bin/env bash
# Run once as a human Azure administrator after observing the bootstrap claims.
set -euo pipefail
: "${OIDC_SUBJECT:?Set the exact sub printed by Deploy dev with bootstrap=true}"
az identity federated-credential create \
  --name github-dev \
  --identity-name id-shopshield-github \
  --resource-group rg-shopshield \
  --issuer https://token.actions.githubusercontent.com \
  --subject "$OIDC_SUBJECT" \
  --audiences api://AzureADTokenExchange
