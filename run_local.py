"""Run all ten services without Docker. Stop them together with Ctrl+C."""

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
SERVICES = [
    'gateway', 'catalog', 'cart', 'pricing', 'inventory',
    'orders', 'payments', 'shipping', 'notifications', 'recommendations',
]
PORTS = {name: 8080 + index for index, name in enumerate(SERVICES)}


def main():
    processes = []
    try:
        for name in SERVICES:
            env = {
                **os.environ,
                'SERVICE': name,
                'PORT': str(PORTS[name]),
                'BIND_HOST': '127.0.0.1',
                'PYTHONUNBUFFERED': '1',
                **{
                    service.upper() + '_URL': f'http://127.0.0.1:{port}'
                    for service, port in PORTS.items()
                },
            }
            env.pop('CONTAINER', None)
            process = subprocess.Popen([sys.executable, 'common.py'], cwd=ROOT, env=env)
            processes.append((name, process))

        for name, process in processes:
            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f'{name} exited; check whether port {PORTS[name]} is already in use')
                try:
                    with urlopen(f'http://127.0.0.1:{PORTS[name]}/health', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(f'{name} did not become healthy')

        print('\nShopShield is ready: http://127.0.0.1:8080/products', flush=True)
        print('This is a JSON API. Press Ctrl+C to stop all ten services.\n', flush=True)
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f'{name} exited unexpectedly')
            time.sleep(0.5)
    except KeyboardInterrupt:
        print('\nStopping ShopShield...', flush=True)
    finally:
        for _, process in processes:
            if process.poll() is None:
                process.terminate()
        for _, process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
