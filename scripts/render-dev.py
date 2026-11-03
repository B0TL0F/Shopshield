"""Validate service wiring and render selected dev workloads with CI image tags.

Source YAML stays unchanged. No cluster operations are performed here.
Requires PyYAML. Paths are relative to the repository root, independent of cwd.
"""
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('gateway', 'catalog', 'cart', 'pricing', 'inventory', 'orders',
         'payments', 'shipping', 'notifications', 'recommendations')


def render():
    revision = os.environ['REVISION']
    prefix = os.environ['IMAGE_PREFIX'].lower()
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('REVISION must be the full 40-character CI commit SHA')
    if not re.fullmatch(r'ghcr\.io/[a-z0-9_.-]+/shopshield', prefix):
        raise ValueError('IMAGE_PREFIX must be ghcr.io/<owner>/shopshield')
    selection = os.environ.get('SELECTED_SERVICES', 'all').strip()
    selected = list(NAMES) if selection == 'all' else [s.strip() for s in selection.split(',')]
    if not selected or any(s not in NAMES for s in selected) or len(selected) != len(set(selected)):
        raise ValueError('Choose all or a comma-separated list of distinct known service names')

    workloads = []
    for name in NAMES:
        folder = ROOT / 'k8s' / 'dev' / 'services' / name
        deployment = yaml.safe_load((folder / 'deployment.yaml').read_text())
        service = yaml.safe_load((folder / 'service.yaml').read_text())
        if deployment['kind'] != 'Deployment' or service['kind'] != 'Service':
            raise ValueError(f'{name}: incorrect resource kinds')
        for resource in (deployment, service):
            if resource['metadata']['name'] != name or resource['metadata']['namespace'] != 'shopshield':
                raise ValueError(f'{name}: incorrect resource name or namespace')
        pod = deployment['spec']['template']
        selector = service['spec']['selector']
        if selector != deployment['spec']['selector']['matchLabels']:
            raise ValueError(f'{name}: Service and Deployment selectors differ')
        if any(pod['metadata']['labels'].get(k) != v for k, v in selector.items()):
            raise ValueError(f'{name}: selector does not match pod labels')
        expected_type = 'LoadBalancer' if name == 'gateway' else 'ClusterIP'
        if service['spec']['type'] != expected_type:
            raise ValueError(f'{name}: expected {expected_type} Service')
        container = pod['spec']['containers'][0]
        target = service['spec']['ports'][0]['targetPort']
        if not any(p['name'] == target and p['containerPort'] == 8080 for p in container['ports']):
            raise ValueError(f'{name}: Service targetPort does not match container port')
        container['image'] = f'{prefix}-{name}:{revision}'
        if name in selected:
            workloads.extend([deployment, service])

    output = Path(os.environ.get('OUTPUT_PATH', 'dev-workloads.yaml'))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump_all(workloads, sort_keys=False))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as handle:
            handle.write('services=' + ' '.join(selected) + '\n')
            handle.write('full_deploy=' + str(set(selected) == set(NAMES)).lower() + '\n')
    print(f'Rendered {len(selected)} services at {revision} into {output}')


if __name__ == '__main__':
    render()
