# GitHub Actions: tests, scans, images and controlled deployment

Create a public GitHub repository, use `main`, and copy the workflows below. CI has no Azure credentials. Pull requests test and scan; only main pushes publish images. Deployment is a separate manual action with an explicit successful CI run ID, so it cannot silently build an unreviewed artifact.

Tags in this teaching workflow are readable but mutable references. Before presenting this as a hardened supply chain, resolve reviewed actions to full commit SHAs, enable Dependabot updates and branch protection, and use image digests/signature verification. Those are extension tasks, not implemented claims.

## `.github/workflows/ci.yaml`

The first job tests the ten-process application, checks Terraform formatting/validation, renders Helm and runs Trivy secret and vulnerability scanning. Each matrix job then scans its own image before pushing it. Scans intentionally fail on HIGH/CRITICAL findings, including newly discovered base-image issues: update and investigate rather than adding `continue-on-error`. Misconfiguration scans are recorded separately because this lab deliberately omits production HA and persistence; review those findings.

```yaml file=.github/workflows/ci.yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: python tests/integration.py
      - uses: hashicorp/setup-terraform@v3
        with: {terraform_version: '1.9.8'}
      - run: |
          terraform -chdir=infra fmt -check
          terraform -chdir=infra init -backend=false
          terraform -chdir=infra validate
      - uses: azure/setup-helm@v4.3.0
        with: {version: 'v3.17.3'}
      - run: |
          helm lint charts/shopshield
          helm lint monitoring
          helm template shopshield charts/shopshield > app-rendered.yaml
          helm template monitoring monitoring > monitoring-rendered.yaml
      - uses: aquasecurity/trivy-action@v0.36.0
        with:
          scan-type: fs
          scan-ref: .
          scanners: vuln,secret
          severity: HIGH,CRITICAL
          exit-code: '1'
      - uses: aquasecurity/trivy-action@v0.36.0
        with:
          scan-type: config
          scan-ref: .
          exit-code: '0'
  images:
    needs: verify
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    strategy:
      fail-fast: false
      matrix:
        service: [gateway, catalog, cart, pricing, inventory, orders, payments, shipping, notifications, recommendations]
    steps:
      - uses: actions/checkout@v4
      - name: Set lowercase image name
        shell: bash
        run: echo "IMAGE=ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/shopshield-${{ matrix.service }}:${GITHUB_SHA}" >> "$GITHUB_ENV"
      - run: docker build --build-arg SERVICE=${{ matrix.service }} -t "$IMAGE" .
      - uses: aquasecurity/trivy-action@v0.36.0
        with:
          image-ref: ${{ env.IMAGE }}
          scanners: vuln
          severity: HIGH,CRITICAL
          exit-code: '1'
      - uses: docker/login-action@v3
        if: github.event_name == 'push'
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - if: github.event_name == 'push'
        run: docker push "$IMAGE"
```

Run `terraform fmt` locally before pushing; the guide's readable indentation may be normalized by Terraform. The ten matrix jobs can use substantial Actions minutes on private repositories. Check your GitHub plan.

## OIDC bootstrap: use the actual subject

GitHub's OIDC subject format can vary by repository configuration and creation date. Do not blindly paste an old `repo:owner/repo:environment:lab` subject. The deploy workflow has a bootstrap mode that prints only the issuer, audience and subject from its short-lived token, never the token itself. Configure Azure trust for the exact observed `sub`. [GitHub OIDC guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure).

Create a GitHub environment named `lab`, restricted to `main`; enable approval protection if your GitHub plan supports it. Set repository Actions variables:

| Variable | Value |
|---|---|
| AZURE_CLIENT_ID | Terraform `deploy_client_id` output |
| AZURE_TENANT_ID | Your tenant ID |
| AZURE_SUBSCRIPTION_ID | Your subscription ID |
| AKS_RESOURCE_GROUP | `rg-shopshield` |
| AKS_NAME | `aks-shopshield` |

Run Deploy manually from main with bootstrap=true. Copy its reported `sub` exactly, then create the credential as your human Azure administrator. This is the only trust setup; never use wildcard trust for other repositories.

## `scripts/bootstrap-deploy.sh`

```bash file=scripts/bootstrap-deploy.sh
#!/usr/bin/env bash
set -euo pipefail
: "${OIDC_SUBJECT:?Set this to the exact sub printed by the lab bootstrap run}"
az identity federated-credential create \
  --name github-lab --identity-name id-shopshield-github \
  --resource-group rg-shopshield \
  --issuer https://token.actions.githubusercontent.com \
  --subject "$OIDC_SUBJECT" --audiences api://AzureADTokenExchange
```

```bash
export OIDC_SUBJECT='COPY_THE_EXACT_OBSERVED_SUBJECT'
bash scripts/bootstrap-deploy.sh
```

## `.github/workflows/deploy.yaml`

Choose a successful main push CI run ID, not a workflow run from a fork. The workflow checks its identity and conclusion, checks out that exact source revision and deploys that revision's image tags. It uses namespace-scoped Azure RBAC Writer, not cluster-admin. Monitoring and namespace creation remain human administration tasks. Azure RBAC Writer can manage Secrets in its namespace, including Helm release records; do not put unrelated workloads or secrets there.

```yaml file=.github/workflows/deploy.yaml
name: Deploy
on:
  workflow_dispatch:
    inputs:
      bootstrap:
        description: Print OIDC claims for initial trust setup only
        type: boolean
        default: false
      ci_run_id:
        description: Successful main push CI run ID (required unless bootstrap)
        type: string
permissions:
  contents: read
  actions: read
  id-token: write
concurrency:
  group: deploy-lab
  cancel-in-progress: false
jobs:
  deploy:
    if: github.ref == 'refs/heads/main'
    environment: lab
    runs-on: ubuntu-latest
    steps:
      - name: Inspect safe OIDC claims for trust setup
        if: inputs.bootstrap
        shell: bash
        run: |
          python3 - <<'PY'
          import os, json, base64, urllib.request
          url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'] + '&audience=api%3A%2F%2FAzureADTokenExchange'
          req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
          token = json.load(urllib.request.urlopen(req, timeout=20))['value']
          payload = token.split('.')[1]
          claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
          print(json.dumps({k: claims[k] for k in ('iss', 'aud', 'sub')}))
          PY
      - name: Verify chosen CI run
        if: ${{ !inputs.bootstrap }}
        id: revision
        env:
          GH_TOKEN: ${{ github.token }}
          RUN_ID: ${{ inputs.ci_run_id }}
        shell: bash
        run: |
          [[ "$RUN_ID" =~ ^[0-9]+$ ]]
          gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN_ID" > run.json
          python3 - <<'PY'
          import json, os, re
          run = json.load(open('run.json'))
          assert run['conclusion'] == 'success' and run['status'] == 'completed'
          assert run['event'] == 'push' and run['head_branch'] == 'main'
          assert run['path'] == '.github/workflows/ci.yaml'
          assert run['head_repository']['full_name'] == os.environ['GITHUB_REPOSITORY']
          assert re.fullmatch('[0-9a-f]{40}', run['head_sha'])
          with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
              output.write('sha=' + run['head_sha'] + '\n')
          PY
      - uses: actions/checkout@v4
        if: ${{ !inputs.bootstrap }}
        with:
          ref: ${{ steps.revision.outputs.sha }}
      - uses: azure/login@v2
        if: ${{ !inputs.bootstrap }}
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
      - uses: azure/setup-helm@v4.3.0
        if: ${{ !inputs.bootstrap }}
        with: {version: 'v3.17.3'}
      - uses: azure/setup-kubectl@v4
        if: ${{ !inputs.bootstrap }}
      - uses: azure/use-kubelogin@v1
        if: ${{ !inputs.bootstrap }}
        with: {kubelogin-version: 'v0.2.2'}
      - name: Deploy verified images
        if: ${{ !inputs.bootstrap }}
        env:
          RG: ${{ vars.AKS_RESOURCE_GROUP }}
          AKS: ${{ vars.AKS_NAME }}
          REVISION: ${{ steps.revision.outputs.sha }}
        shell: bash
        run: |
          set -euo pipefail
          az aks get-credentials -g "$RG" -n "$AKS" --overwrite-existing
          kubelogin convert-kubeconfig -l azurecli
          helm upgrade --install shopshield charts/shopshield -n shopshield \
            --set imagePrefix="ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/shopshield" \
            --set imageTag="$REVISION" --atomic --wait --timeout 10m --history-max 3
          kubectl -n shopshield get deployments
      - name: Smoke test deployed gateway
        if: ${{ !inputs.bootstrap }}
        shell: bash
        run: |
          set -euo pipefail
          kubectl -n shopshield port-forward service/gateway 18080:8080 > /tmp/port-forward.log 2>&1 &
          FORWARD_PID=$!
          trap 'kill "$FORWARD_PID" 2>/dev/null || true' EXIT
          curl --retry 15 --retry-connrefused --retry-delay 2 --fail http://localhost:18080/products
          curl --fail -H 'Content-Type: application/json' http://localhost:18080/cart \
            -d '{"cart_id":"pipeline","items":[{"sku":"book","qty":2}]}'
          curl --fail -H 'Content-Type: application/json' -H "Idempotency-Key: ci-$GITHUB_RUN_ID" \
            http://localhost:18080/checkout \
            -d '{"cart_id":"pipeline","country":"IN","token":"demo-approved"}'
```

Deployment assumes public GHCR images and an AKS API reachable by the runner. The first hosted-runner deployment requires the empty API allowlist documented in chapter 4. If you choose an IP-restricted endpoint, run this job on your trusted self-hosted Linux runner within the allowed network. Do not expose Grafana or application ports to solve API reachability.

A failed post-deployment smoke check marks the run failed; it does not automatically revert a release that Helm already accepted. Diagnose it, then use the rollback commands in chapter 8.
