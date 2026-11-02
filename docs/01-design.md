# Architecture, networking and cost gate

View [architecture.png](architecture.png) at full resolution. It depicts the implemented baseline, including the control-plane boundary, node subnet, overlay pod CIDR, service CIDR, NSG, managed identities, artifact pipeline and monitoring. It does not imply a production security or availability certification.

## Ten services and their boundaries

| Service | Responsibility | Downstream services |
|---|---|---|
| gateway | Public-facing JSON API through localhost port-forward | catalog, cart, orders, recommendations |
| catalog | Product names and authoritative prices | none |
| cart | In-memory carts | none |
| pricing | Calculates item total using catalog prices | catalog |
| inventory | Checks fixed demonstration stock | none |
| orders | Checkout orchestration and process-local idempotency | cart, inventory, pricing, payments, shipping, notifications |
| payments | Simulated authorization/decline | none |
| shipping | Simulated shipping quote | none |
| notifications | Simulated notification acceptance | none |
| recommendations | Selects products from catalog | catalog |

Ten service modules are built into ten images, and deployed through ten Deployments and ten ClusterIP Services. Sharing `common.py` is a build-time dependency; services communicate over HTTP at runtime. There is no shared runtime process and no shared database. The commerce logic is intentionally limited: inventory does not reserve stock, carts/orders disappear with pod replacement, payment does not contact a provider, and notification does not send email. One replica per service is required by this state model.

## Network plan

| Boundary | Address / implementation | Purpose |
|---|---|---|
| Azure VNet | 10.20.0.0/16 | Private network for AKS worker nodes |
| Node subnet | 10.20.0.0/22 | Addresses for two worker nodes and upgrade capacity |
| Pod network | 10.244.0.0/16, Azure CNI Overlay | Pod addresses, separate from VNet subnet |
| Service network | 10.96.0.0/16 | Virtual ClusterIP addresses; not an Azure subnet |
| DNS service | 10.96.0.10 | CoreDNS service discovery |
| Kubernetes namespaces | shopshield, monitoring, kube-system | Logical workload separation, not Azure subnets |
| Subnet NSG | Azure default rules | VNet access allowed, unsolicited internet inbound denied, internet outbound allowed |
| Application policy | Cilium + Kubernetes NetworkPolicy | Default deny, DNS, exact service graph and monitoring scrape allowances |
| Application access | kubectl port-forward over authenticated API | Localhost only; no public app ingress |
| AKS API | Public HTTPS endpoint + Entra authentication/RBAC | Human and GitHub deployment administration |
| Outbound | AKS-managed Standard load balancer + public IP | Node image pulls, Azure dependencies and internet egress |

Only one Azure subnet is needed here. Adding empty subnets for databases, gateways or firewalls would misrepresent the implemented project. Ensure the CIDRs do not conflict with local VPN/enterprise networks before applying. CNI overlay source-NATs traffic leaving the pod network to node addresses. [Azure CNI Overlay](https://learn.microsoft.com/en-us/azure/aks/azure-cni-overlay).

Worker nodes have private addresses; that does not make the AKS API private. The diagram shows the API outside the VNet. An empty API IP allowlist allows hosted CI to reach the authenticated endpoint. An IP-restricted endpoint requires a trusted runner with allowed network access; a private cluster requires additional DNS and connectivity design. Neither a private cluster nor a WAF is claimed here.

NetworkPolicy rules are additive: a caller needs allowed egress and the receiver needs allowed ingress. The supplied chart generates both from the service call graph. DNS egress selects CoreDNS in kube-system. Monitoring can scrape application TCP/8080. The NSG and NetworkPolicy solve different problems; NSG rules do not replace pod policies.

## Security and delivery flow

1. Local integration tests exercise all ten processes.
2. GitHub Actions validates Terraform, renders/lints Helm, scans source/secrets and builds/scans ten images.
3. Only successful main pushes publish commit-tagged images to GHCR.
4. Human setup creates Azure infrastructure and namespace boundaries.
5. A manual deploy workflow checks a successful CI run, then uses short-lived GitHub OIDC to authenticate as a dedicated Azure identity.
6. Azure permissions allow obtaining cluster-user credentials and writing inside shopshield only. Application pods receive no Azure permissions and no mounted service-account token.
7. Non-root containers, read-only root filesystems, dropped capabilities, restricted Pod Security Admission and explicit network policies constrain the runtime.
8. Prometheus scrapes application metrics; Grafana visualizes them. Rules are evaluated locally in Prometheus.

The AKS control-plane identity has subnet Network Contributor. A separate kubelet identity is created by AKS for node operations. The GitHub deploy identity is separate from both. OIDC on AKS is enabled for later workload-identity exercises; the application does not currently request Azure tokens.

## Azure Free subscription: what is and is not covered

Verified against Microsoft documentation on 2026-11-02. Your subscription's remaining credit, eligibility, region capacity and quota are account-specific and cannot be established from these files.

| Component | Free-account interpretation |
|---|---|
| AKS Free control plane | No cluster-management fee; no financially backed control-plane SLA |
| Two D4s_v5 worker nodes | Billable compute; do not assume free VM offers apply |
| Node OS managed disks | Billable storage; may remain billable when compute is stopped |
| Standard load balancer/public IP | Potential billable networking for AKS outbound connectivity |
| VNet/subnet/NSG | Basic resources generally have no standalone hourly charge; associated connectivity/services may charge |
| Prometheus/Grafana containers | Open-source software; they consume paid node resources |
| GHCR/Actions | GitHub plan, visibility and usage limits apply; independent of Azure credit |
| Local Docker | No Azure resources; local machine resources and applicable Docker licensing still matter |

Microsoft describes AKS Free tier as charging for underlying resources. Azure free-account credit is time-limited and offer-specific; the common new-customer offer advertises $200 for 30 days. After that period, free service quotas do not mean all Azure products are free. [AKS pricing](https://azure.microsoft.com/en-us/pricing/details/kubernetes-service/), [Azure free account](https://azure.microsoft.com/en-us/free/).

The chosen baseline reserves two 4-vCPU nodes (8 vCPUs total), with one extra 4-vCPU node potentially needed during upgrades (12 total). Region/family quota and capacity must support this. Current system-pool guidance specifies at least two nodes, 4-vCPU/4-GB minimum VM SKU, and no B-series. Some AKS documentation pages expose different minimums; this guide follows the stricter system-pool page. Do not assume an old one-node/B-series tutorial works. [System node pools](https://learn.microsoft.com/en-us/azure/aks/use-system-pools), [AKS quotas and SKU restrictions](https://learn.microsoft.com/en-us/azure/aks/quotas-skus-regions).

Before applying, check credit and expiration in Cost Management, inspect quota for your chosen region and D-family, and use the Azure pricing calculator for two VMs, two OS disks, load balancer, public IP and expected runtime. No fixed rupee estimate is given because your region, currency, offer and rates determine it. Budgets notify; they do not cap spending. If quota/credit is inadequate, complete the local Docker and CI path and defer AKS. Do not upgrade a subscription assuming AKS becomes free. [Azure pricing calculator](https://azure.microsoft.com/en-us/pricing/calculator/), [Budget behavior](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).

## `scripts/preflight.sh`

Read-only checks. SKU availability does not guarantee quota or regional capacity. Do not paste account IDs or quota output into public issues without reviewing it.

```bash file=scripts/preflight.sh
#!/usr/bin/env bash
set -euo pipefail
REGION="${REGION:-centralindia}"
az account show --query '{subscription:name,state:state}' -o table
az vm list-usage --location "$REGION" -o table
az vm list-skus --location "$REGION" --size Standard_D4s_v5 \
  --all --query '[].{name:name,restrictions:restrictions}' -o json
az aks get-versions --location "$REGION" -o table
for provider in Microsoft.ContainerService Microsoft.Compute Microsoft.Network Microsoft.ManagedIdentity; do
  az provider show --namespace "$provider" --query '{name:namespace,state:registrationState}' -o table
done
```

Run `az login`, select your subscription, then `bash scripts/preflight.sh`. Inspect the result yourself; the script does not decide that the deployment is free or automatically apply Terraform.
