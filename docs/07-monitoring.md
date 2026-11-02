# Prometheus and Grafana

This small, self-hosted monitoring chart exposes application request metrics and availability. It does not install the Prometheus Operator, kube-state-metrics, node-exporter, log aggregation or managed Azure monitoring. Those are optional expansions with extra memory, permissions and cost. Prometheus scrapes ten stable Service DNS names, so this configuration deliberately assumes one replica per service.

## `monitoring/Chart.yaml`

```yaml file=monitoring/Chart.yaml
apiVersion: v2
name: shopshield-monitoring
description: Small self-hosted application monitoring lab
type: application
version: 0.1.0
appVersion: "0.1.0"
```

## `monitoring/values.yaml`

Release tags are selected from upstream releases. Review security advisories and scan these images before installing; version tags alone are not a security guarantee. [Prometheus releases](https://github.com/prometheus/prometheus/releases), [Grafana releases](https://github.com/grafana/grafana/releases).

```yaml file=monitoring/values.yaml
services: [gateway, catalog, cart, pricing, inventory, orders, payments, shipping, notifications, recommendations]
images:
  prometheus: prom/prometheus:v3.13.5
  grafana: grafana/grafana:13.2.4
```

## `monitoring/templates/stack.yaml`

The mounted ConfigMaps provision the datasource and dashboard automatically. Both data directories use emptyDir: data survives a container restart inside the same pod but is lost when the pod is replaced. A values or chart-version change triggers rollout. Bump the chart version when editing configuration inside this template so mounted configuration reloads. No persistent disks are created.

```yaml file=monitoring/templates/stack.yaml
apiVersion: v1
kind: ConfigMap
metadata: {name: prometheus-config}
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
      evaluation_interval: 15s
    rule_files: [/etc/prometheus/alerts.yml]
    scrape_configs:
      - job_name: shopshield
        static_configs:
{{- range .Values.services }}
          - targets: ['{{ . }}.shopshield.svc.cluster.local:8080']
            labels: {service: '{{ . }}'}
{{- end }}
  alerts.yml: |
    groups:
      - name: shopshield
        rules:
          - alert: ServiceUnavailable
            expr: up{job="shopshield"} == 0
            for: 1m
            labels: {severity: warning}
            annotations:
              summary: A ShopShield scrape target has been down for one minute
          - alert: HighErrorRatio
            expr: sum(rate(shop_requests_total{status=~"5.."}[5m])) / clamp_min(sum(rate(shop_requests_total[5m])), 0.001) > 0.05
            for: 2m
            labels: {severity: warning}
            annotations:
              summary: More than five percent of internal service requests return 5xx
---
apiVersion: v1
kind: ConfigMap
metadata: {name: grafana-config}
data:
  datasource.yaml: |
    apiVersion: 1
    datasources:
      - name: Prometheus
        uid: prometheus
        type: prometheus
        access: proxy
        url: http://prometheus:9090
        isDefault: true
  provider.yaml: |
    apiVersion: 1
    providers:
      - name: shopshield
        type: file
        options:
          path: /var/lib/grafana/dashboards
  dashboard.json: |
    {
      "uid": "shopshield", "title": "ShopShield services", "schemaVersion": 39,
      "version": 1, "refresh": "15s", "time": {"from": "now-15m", "to": "now"},
      "panels": [
        {"id": 1, "title": "Service scrape availability", "type": "timeseries",
         "gridPos": {"x": 0, "y": 0, "w": 24, "h": 8},
         "datasource": {"type": "prometheus", "uid": "prometheus"},
         "targets": [{"refId": "A", "expr": "up{job=\"shopshield\"}", "legendFormat": "{{`{{service}}`}}"}]},
        {"id": 2, "title": "Requests per second by service", "type": "timeseries",
         "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
         "datasource": {"type": "prometheus", "uid": "prometheus"},
         "targets": [{"refId": "A", "expr": "sum by(service)(rate(shop_requests_total[2m]))", "legendFormat": "{{`{{service}}`}}"}]},
        {"id": 3, "title": "Internal 5xx requests per second", "type": "timeseries",
         "gridPos": {"x": 12, "y": 8, "w": 12, "h": 8},
         "datasource": {"type": "prometheus", "uid": "prometheus"},
         "targets": [{"refId": "A", "expr": "sum by(service)(rate(shop_requests_total{status=~\"5..\"}[2m]))", "legendFormat": "{{`{{service}}`}}"}]}
      ]
    }
{{- range $name := list "prometheus" "grafana" }}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: {{ $name }}}
spec:
  replicas: 1
  strategy: {type: Recreate}
  selector:
    matchLabels: {app: {{ $name }}}
  template:
    metadata:
      labels: {app: {{ $name }}}
      annotations:
        config-checksum: {{ printf "%s%s" ($.Values | toJson) $.Chart.Version | sha256sum }}
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: {{ $name }}
          image: {{ index $.Values.images $name | quote }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: [ALL]}
          resources:
            requests: {cpu: 100m, memory: 128Mi}
            limits: {cpu: 500m, memory: 512Mi}
{{- if eq $name "prometheus" }}
          args:
            - --config.file=/etc/prometheus/prometheus.yml
            - --storage.tsdb.path=/prometheus
            - --storage.tsdb.retention.time=6h
            - --storage.tsdb.retention.size=256MB
          ports: [{name: http, containerPort: 9090}]
          readinessProbe:
            httpGet: {path: /-/ready, port: http}
          livenessProbe:
            httpGet: {path: /-/healthy, port: http}
          volumeMounts:
            - {name: data, mountPath: /prometheus}
            - {name: config, mountPath: /etc/prometheus}
{{- else }}
          env:
            - {name: GF_AUTH_ANONYMOUS_ENABLED, value: "false"}
            - {name: GF_ANALYTICS_REPORTING_ENABLED, value: "false"}
            - name: GF_SECURITY_ADMIN_PASSWORD
              valueFrom:
                secretKeyRef: {name: grafana-admin, key: password}
          ports: [{name: http, containerPort: 3000}]
          readinessProbe:
            httpGet: {path: /api/health, port: http}
          livenessProbe:
            httpGet: {path: /api/health, port: http}
          volumeMounts:
            - {name: data, mountPath: /var/lib/grafana}
            - {name: config, mountPath: /etc/grafana/provisioning/datasources/datasource.yaml, subPath: datasource.yaml}
            - {name: config, mountPath: /etc/grafana/provisioning/dashboards/provider.yaml, subPath: provider.yaml}
            - {name: config, mountPath: /var/lib/grafana/dashboards/shopshield.json, subPath: dashboard.json}
{{- end }}
            - {name: tmp, mountPath: /tmp}
      volumes:
        - name: data
          emptyDir: {}
        - name: tmp
          emptyDir: {}
        - name: config
          configMap: {name: {{ $name }}-config}
---
apiVersion: v1
kind: Service
metadata: {name: {{ $name }}}
spec:
  type: ClusterIP
  selector: {app: {{ $name }}}
  ports:
    - name: http
      port: {{ if eq $name "prometheus" }}9090{{ else }}3000{{ end }}
      targetPort: http
{{- end }}
```

## Install and verify as the human administrator

Generate a password in memory and pipe it to Kubernetes without committing it or putting it in shell history. Kubernetes Secrets are access-controlled objects, not an external secrets vault. The deployment CI identity cannot access this namespace.

```bash
kubectl create namespace monitoring
kubectl label namespace monitoring pod-security.kubernetes.io/enforce=restricted
python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' | \
  kubectl -n monitoring create secret generic grafana-admin --from-file=password=/dev/stdin
helm lint monitoring
helm upgrade --install monitoring monitoring -n monitoring --atomic --wait --timeout 10m
kubectl -n monitoring get pods,services
kubectl -n monitoring port-forward service/prometheus 9090:9090
```

In another terminal:

```bash
kubectl -n monitoring port-forward service/grafana 3000:3000
```

Open localhost:9090/targets: expect ten UP targets after DNS and scrape intervals settle. Open localhost:3000, sign in as `admin`. Retrieve your generated password locally with `kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.password}' | base64 -d`; avoid screen-sharing that output. Open the provisioned ShopShield dashboard. Send requests to gateway while its port-forward is running. Rates need at least two scrapes and some traffic; missing series before the first business request are expected.

PromQL examples:

```promql
up{job="shopshield"}
sum by(service)(rate(shop_requests_total[2m]))
sum by(service)(rate(shop_request_duration_seconds_sum[2m])) / clamp_min(sum by(service)(rate(shop_requests_total[2m])), 0.001)
```

The last query is mean duration, not p95. For percentiles add histogram buckets later. Internal requests count each downstream hop; the gateway series represents client-facing request volume.

Scale catalog to zero and observe `ServiceUnavailable` become pending then firing under Prometheus Alerts; restore it afterward. Alerts are visible in Prometheus only. There is no Alertmanager or email/Slack delivery configured. Monitoring namespace pods use Kubernetes default networking; application namespace policies enforce the service restrictions. Restrict monitoring egress/ingress as a follow-up exercise.
