# Helm: deploy ten independently built services

Create the chart below. Release name is always `shopshield`, namespace `shopshield`. Fixed service names simplify DNS teaching; install only one release per namespace. One replica per service preserves the limitations of in-memory carts and order idempotency. The chart contains no namespace or cluster-scoped resources, so the CI identity can remain scoped to this namespace.

## `charts/shopshield/Chart.yaml`

```yaml file=charts/shopshield/Chart.yaml
apiVersion: v2
name: shopshield
description: Ten-service commerce simulator
type: application
version: 0.1.0
appVersion: "0.1.0"
```

## `charts/shopshield/values.yaml`

Replace `YOUR_LOWERCASE_OWNER` when deploying. CI pushes all ten images under one commit tag, e.g. `ghcr.io/owner/shopshield-catalog:<40-character-commit>`. Use a public repository and manually verify every GHCR package is public before cluster deployment; private packages need an imagePullSecret which this baseline intentionally does not assume.

```yaml file=charts/shopshield/values.yaml
imagePrefix: ghcr.io/YOUR_LOWERCASE_OWNER/shopshield
imageTag: local
services:
  gateway: {calls: [catalog, cart, orders, recommendations]}
  catalog: {calls: []}
  cart: {calls: []}
  pricing: {calls: [catalog]}
  inventory: {calls: []}
  orders: {calls: [cart, inventory, pricing, payments, shipping, notifications]}
  payments: {calls: []}
  shipping: {calls: []}
  notifications: {calls: []}
  recommendations: {calls: [catalog]}
```

## `charts/shopshield/templates/workloads.yaml`

Every process runs without root, extra capabilities, service-account tokens, or write access to its image filesystem. Requests reserve capacity; limits constrain individual containers. Recreate avoids running two stateful replicas during updates, at the expense of brief downtime. Helm rollback cannot recover in-memory data.

```yaml file=charts/shopshield/templates/workloads.yaml
{{- range $name, $config := .Values.services }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ $name }}
  labels: {app: {{ $name }}, project: shopshield}
spec:
  replicas: 1
  revisionHistoryLimit: 2
  strategy: {type: Recreate}
  selector:
    matchLabels: {app: {{ $name }}}
  template:
    metadata:
      labels: {app: {{ $name }}, project: shopshield}
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: {{ $name }}
          image: "{{ $.Values.imagePrefix }}-{{ $name }}:{{ $.Values.imageTag }}"
          imagePullPolicy: IfNotPresent
          ports: [{name: http, containerPort: 8080}]
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: [ALL]}
          resources:
            requests: {cpu: 25m, memory: 48Mi}
            limits: {cpu: 500m, memory: 128Mi}
          startupProbe:
            httpGet: {path: /health, port: http}
            failureThreshold: 30
            periodSeconds: 2
          readinessProbe:
            httpGet: {path: /health, port: http}
            periodSeconds: 5
          livenessProbe:
            httpGet: {path: /health, port: http}
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: {{ $name }}
  labels: {app: {{ $name }}, project: shopshield}
spec:
  type: ClusterIP
  selector: {app: {{ $name }}}
  ports: [{name: http, port: 8080, targetPort: http}]
{{- end }}
```

## `charts/shopshield/templates/policies.yaml`

Default deny selects only application pods. Allow DNS, explicit caller/callee pairs, and Prometheus scrapes from the monitoring namespace. Policies restrict ports and pods, not URL paths or HTTP authentication. Image pulls are performed by the node, outside pod egress rules. Port-forward uses the authenticated Kubernetes API path; it does not publish the gateway on the internet.

```yaml file=charts/shopshield/templates/policies.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: default-deny}
spec:
  podSelector:
    matchLabels: {project: shopshield}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: allow-dns}
spec:
  podSelector:
    matchLabels: {project: shopshield}
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels: {kubernetes.io/metadata.name: kube-system}
          podSelector:
            matchLabels: {k8s-app: kube-dns}
      ports:
        - {protocol: UDP, port: 53}
        - {protocol: TCP, port: 53}
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: allow-monitoring}
spec:
  podSelector:
    matchLabels: {project: shopshield}
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels: {kubernetes.io/metadata.name: monitoring}
          podSelector:
            matchLabels: {app: prometheus}
      ports: [{protocol: TCP, port: 8080}]
{{- range $caller, $config := .Values.services }}
{{- range $callee := $config.calls }}
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ $caller }}-to-{{ $callee }}
spec:
  podSelector:
    matchLabels: {app: {{ $caller }}, project: shopshield}
  policyTypes: [Egress]
  egress:
    - to:
        - podSelector:
            matchLabels: {app: {{ $callee }}, project: shopshield}
      ports: [{protocol: TCP, port: 8080}]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ $callee }}-from-{{ $caller }}
spec:
  podSelector:
    matchLabels: {app: {{ $callee }}, project: shopshield}
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels: {app: {{ $caller }}, project: shopshield}
      ports: [{protocol: TCP, port: 8080}]
{{- end }}
{{- end }}
```

## Human bootstrap and first deployment

Run as the human cluster admin. The restricted Pod Security Admission labels apply to application pods. Monitoring uses its own namespace and user permissions.

```bash
kubectl create namespace shopshield
kubectl label namespace shopshield pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted pod-security.kubernetes.io/warn=restricted
helm lint charts/shopshield
helm template shopshield charts/shopshield -n shopshield
# Set these to a real published image prefix and successful CI commit.
export IMAGE_PREFIX=ghcr.io/YOUR_LOWERCASE_OWNER/shopshield
export IMAGE_TAG=YOUR_FULL_COMMIT_SHA
helm upgrade --install shopshield charts/shopshield -n shopshield \
  --set imagePrefix="$IMAGE_PREFIX" --set imageTag="$IMAGE_TAG" \
  --atomic --wait --timeout 10m --history-max 3
kubectl -n shopshield get deployments,services,pods,networkpolicies
kubectl -n shopshield port-forward service/gateway 8080:8080
```

In another terminal repeat the curl calls from chapter 3. Expect ten Ready application pods and a 3500-cent checkout. `--atomic` rolls back a failed upgrade but does not replace acceptance testing. Avoid `latest` tags; digest pinning and signature enforcement are future improvements, not features claimed here.
