# Verification record

Checked on 2026-11-02. The 32 implementation blocks were originally extracted into a temporary directory and verified. Following your clarification, the application files are now provided in [the application](../README.md). The integration test was rerun against those actual files and passed; all service modules and the local launcher also passed Python compilation. Docker and infrastructure files remain in the guides for you to create.

| Check | Result |
|---|---|
| Ten-process HTTP integration test | Passed using local Python 3.14 |
| Checkout total and repeated-key order identity | Passed |
| Changed payload/key conflict, payment decline, negative quantity and stock rejection | Passed |
| Recommendations, product routes and metrics | Passed |
| Application Helm lint/render | Passed: 10 Deployments, 10 Services, 27 NetworkPolicies |
| Every declared service call has ingress and egress policy | Passed |
| Monitoring Helm lint/render | Passed: 6 resources |
| Grafana provisioned dashboard JSON | Parsed successfully |
| Terraform formatting | Passed |
| Compose and GitHub workflow YAML | Parsed successfully; not executed |
| Internal Markdown links | Resolved |
| Architecture PNG | Generated at 4640 × 4140 and visually inspected |
| Docker build / Compose runtime / image scans | Not executed: Docker Linux engine was not running |
| Terraform provider initialization / schema validation / plan | Not completed: provider registry access blocked by environment network configuration |
| GitHub Actions, OIDC login and Azure deployment | Not executed; require your account/repository and provisioning |
| Actual AKS policies, dashboard and alert firing | Not verified in a live cluster |

Run the remaining checks on your machine. A successful local test or Helm render does not prove Azure quota, provider compatibility, image pullability, runtime network-policy enforcement or a working OIDC trust. The tutorials include those acceptance checks explicitly.

The diagram uses product artwork bundled with draw.io Desktop's Azure and Docker libraries and its GitHub logo, rasterized locally into the requested PNG. Gradients are flattened. Terraform is shown with a labeled TF badge; Helm with a helm pictogram. The learner workstation is external to Azure and is drawn alongside subscription administration components for context. Namespace and service call cards are logical architecture, not per-node pod placement.
