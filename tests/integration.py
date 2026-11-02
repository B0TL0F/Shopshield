import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
ROOT = Path(__file__).resolve().parents[1]
NAMES = ['gateway', 'catalog', 'cart', 'pricing', 'inventory', 'orders', 'payments', 'shipping', 'notifications', 'recommendations']
PORTS = {name: 18080 + i for i, name in enumerate(NAMES)}
def request(path, body=None, key='test1'):
    data = None if body is None else json.dumps(body).encode()
    req = Request(f'http://127.0.0.1:{PORTS["gateway"]}' + path, data=data,
                  headers={'Content-Type': 'application/json', 'Idempotency-Key': key})
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)
processes = []
try:
    for name in NAMES:
        env = {**os.environ, 'SERVICE': name, 'PORT': str(PORTS[name]), 'BIND_HOST': '127.0.0.1',
               **{n.upper() + '_URL': f'http://127.0.0.1:{p}' for n, p in PORTS.items()}}
        env.pop('CONTAINER', None)
        processes.append(subprocess.Popen([sys.executable, 'common.py'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL))
    for name in NAMES:
        for attempt in range(100):
            try:
                with urlopen(f'http://127.0.0.1:{PORTS[name]}/health', timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                time.sleep(.1)
        else:
            raise AssertionError(name + ' failed to start')
    assert len(request('/products')[1]['products']) == 3
    assert len(request('/recommendations')[1]['recommendations']) == 2
    assert request('/cart', {'cart_id': 'demo', 'items': [{'sku': 'book', 'qty': 2}]})[0] == 200
    body = {'cart_id': 'demo', 'country': 'IN', 'token': 'demo-approved'}
    status, order = request('/checkout', body)
    assert status == 200 and order['total_cents'] == 3500, (status, order)
    assert request('/checkout', body)[1]['order_id'] == order['order_id']
    assert request('/checkout', {**body, 'country': 'US'})[0] == 409
    assert request('/checkout', {**body, 'token': 'demo-declined'}, 'decline')[0] == 402
    assert request('/cart', {'cart_id': 'bad', 'items': [{'sku': 'book', 'qty': -1}]})[0] == 400
    request('/cart', {'cart_id': 'stock', 'items': [{'sku': 'shirt', 'qty': 10}]})
    assert request('/checkout', {**body, 'cart_id': 'stock'}, 'stock')[0] == 409
    assert request('/missing')[0] == 404
    with urlopen(f'http://127.0.0.1:{PORTS["gateway"]}/metrics') as response:
        assert b'shop_requests_total' in response.read()
    print('PASS: ten-service checkout, idempotency, decline, validation, stock, metrics')
finally:
    for process in processes:
        process.terminate()
    for process in processes:
        process.wait(timeout=10)
