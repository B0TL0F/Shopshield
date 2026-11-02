# ShopShield: ten-service DevSecOps learning project

The runnable application source is now in [the application](../README.md). Start there and run its integration test. Create Docker and infrastructure files yourself using the guides below; their implementation files appear inside Markdown code blocks. Use `shopshield/` as your project root.

1. [Architecture, networking and Azure costs](01-design.md)
2. [Ten services and integration tests](02-application.md)
3. [Docker and local development](03-docker.md)
4. [Terraform infrastructure](04-terraform.md)
5. [Helm and network policies](05-helm.md)
6. [GitHub Actions and identity](06-pipelines.md)
7. [Prometheus and Grafana](07-monitoring.md)
8. [Exercises, troubleshooting, cleanup and resume](08-operations.md)

[Open the architecture PNG](architecture.png).

[Verification results and checks you still need to run](09-validation.md).

ShopShield is an educational commerce simulator with ten independent service images. Payments and notifications are simulated. State is in memory, there is no customer authentication, and this is not a production shop. AKS consumes trial credit or incurs charges; use Docker first if your subscription cannot support it.
