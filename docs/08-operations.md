# Learning sequence, operations and resume evidence

## Repository tree

```text
shopshield/
  common.py
  Dockerfile
  compose.yaml
  .dockerignore
  .gitignore
  services/
    gateway.py
    catalog.py
    cart.py
    pricing.py
    inventory.py
    orders.py
    payments.py
    shipping.py
    notifications.py
    recommendations.py
  tests/integration.py
  infra/
    versions.tf
    variables.tf
    main.tf
    outputs.tf
    terraform.tfvars.example
  charts/shopshield/
    Chart.yaml
    values.yaml
    templates/workloads.yaml
    templates/policies.yaml
  monitoring/
    Chart.yaml
    values.yaml
    templates/stack.yaml
  scripts/
    preflight.sh
    bootstrap-deploy.sh
  .github/workflows/
    ci.yaml
    deploy.yaml
```

Generated locally: `infra/terraform.tfvars`, `.terraform/`, `infra/.terraform.lock.hcl`, state and plans. Commit the lockfile; ignore state, tfvars and plans.

## Work through these milestones

| Milestone | What you do | Evidence / understanding check |
|---|---|---|
| Source | Type chapter 2, run integration test | Explain checkout sequence and idempotency limits |
| Docker | Type chapter 3, run Compose and curls | Ten containers, non-root user, decline test |
| Infrastructure code | Type chapter 4, format/validate, review plan | Explain VNet vs pod CIDR vs service CIDR |
| Deployment code | Type chapters 5 and 7, render/lint charts | Ten app Deployments and matching policies |
| CI | Type chapter 6, push all files including monitoring chart | Green tests/scans and ten published images |
| Cost gate | Read chapter 1 and inspect subscription | Record actual credit, quota, expected spend |
| Azure | Apply reviewed plan, get credentials, create namespaces | Two Ready nodes and successful human access |
| First rollout | Verify all packages public; deploy successful CI revision | Ready app pods and successful checkout |
| CD | Bootstrap observed OIDC subject; run verified deploy | Namespace-limited identity, successful smoke test |
| Monitoring | Install chart, open dashboard, generate traffic | Ten scrape targets and service metrics |
| Operations | Perform failure/rollback drills, then destroy | Sanitized evidence and no remaining lab resources |

Write the Docker chapter first as requested, after typing the source it requires. Terraform/Helm validation can run before applying anything. Azure provisioning occurs only after all files are ready and you have reviewed cost/quotas.

## Troubleshooting and controlled failure drills

```bash
kubectl -n shopshield get pods -o wide
kubectl -n shopshield describe pod POD_NAME
kubectl -n shopshield logs deployment/orders --tail=50
kubectl -n shopshield get events --sort-by=.lastTimestamp
kubectl -n monitoring logs deployment/prometheus --tail=50
helm -n shopshield history shopshield
# Choose an actual previous healthy revision from history.
helm -n shopshield rollback shopshield REVISION --wait --timeout 10m
```

- `ImagePullBackOff`: verify owner is lowercase, commit tag exists for all ten images and every package is public. Do not grant subscription Contributor to fix registry access.
- `Pending`: inspect node capacity, requests, taints and events. Free Azure control-plane pricing does not create extra worker capacity.
- `Forbidden`: check correct subscription/tenant, Entra group membership, namespace scope and role propagation. Do not switch CI to admin credentials.
- API timeout: check endpoint IP allowlist and runner reachability. Pod NetworkPolicy does not control public API reachability.
- DNS failure: verify CoreDNS labels and DNS policy. Inspect `kubectl -n kube-system get pods -l k8s-app=kube-dns`.
- Prometheus target down: check service endpoints, readiness and monitoring-to-app policy. Ports must be 8080 for app, 9090 for Prometheus, 3000 for Grafana.
- Grafana password invalid after changing the Secret: its database may retain the prior admin password while the pod survives. Use an appropriate Grafana admin reset procedure, or recreate this ephemeral lab pod and accept lost data.
- Trivy failure: read the exact finding, patch the image/tool reference, rebuild and rerun. A scan is point-in-time evidence, not a guarantee of security.

Failure drill: run `kubectl -n shopshield scale deployment/catalog --replicas=0`. Use a NEW checkout idempotency key so the cached order does not mask the failure. Gateway products should return 503, the target should show DOWN, and Prometheus should fire ServiceUnavailable after one minute. Restore with `kubectl -n shopshield scale deployment/catalog --replicas=1` and verify recovery.

Network-policy drill: from the cart container, access catalog; it should time out because cart has no outbound catalog permission. The allowed pricing-to-catalog path should succeed. Run one command at a time:

```bash
kubectl -n shopshield exec deployment/cart -- python -c 'from urllib.request import urlopen; print(urlopen("http://catalog:8080/products", timeout=3).read())'
kubectl -n shopshield exec deployment/pricing -- python -c 'from urllib.request import urlopen; print(urlopen("http://catalog:8080/products", timeout=3).read())'
```

These checks run in existing application pods and do not download a debugging image. Cilium policy enforcement must be enabled for the denied-path test to mean anything.

## Cleanup

Stop port-forwards with Ctrl+C and local containers with `docker compose down`. Destroy only this lab's Terraform-managed infrastructure after saving sanitized evidence.

```bash
terraform -chdir=infra plan -destroy -out=destroy.tfplan
# Review the exact resources. Then execute your own cleanup:
terraform -chdir=infra apply destroy.tfplan
az group exists --name rg-shopshield
```

AKS deletion should remove its managed node resource group and associated compute/network resources. Verify that node resource group is gone in Azure Portal and inspect Cost Management for remaining resources, public IPs, disks and delayed charges. A stopped AKS cluster is not a full teardown. Keep state until deletion succeeds. The federated credential is a child of the deployment managed identity and disappears when that identity is deleted; an externally created Entra admin group remains yours to manage. GitHub packages/workflow records remain until you remove them separately.

## Resume wording after completing the lab

Project: **ShopShield — ten-service DevSecOps delivery lab on Azure AKS**.

- Built and containerized ten Python HTTP services; validated checkout behavior, input rejection and process-local idempotency through integration tests.
- Provisioned AKS networking and managed identities with Terraform; deployed Helm releases with non-root containers, resource controls, restricted Pod Security Admission and Cilium network policies.
- Automated tests, image/secret scanning and commit-tagged image publication with GitHub Actions; used Azure OIDC and namespace-scoped deployment permissions.
- Provisioned Prometheus/Grafana application monitoring and tested outage detection and Helm rollback.

Use only statements you personally completed. Do not claim production HA, real payment processing, PCI compliance, durable transactions, signed-image admission, p95 monitoring or managed Azure monitoring. Include your GitHub repository, a sanitized PNG, pipeline screenshots, test output and dashboard screenshots. Add measured performance/cost numbers only after collecting them yourself.
