# Application source

The following source files are also provided as actual Python files in [the application](../README.md), with a local launcher. Each service has its own module and is designed for its own container image, Kubernetes Deployment and Service. Shared transport code avoids copying HTTP handling ten times. The application uses only the Python standard library.

## `common.py`

Requests are bounded to 16 KiB, downstream calls time out, and metrics use bounded status labels. Health checks measure process health, so a downstream outage does not restart every service.

```python file=common.py
import importlib
import json
import os
import sys
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

SERVICE = os.environ.get('SERVICE', 'gateway')
COUNTS = Counter()
SECONDS = 0.0
METRIC_LOCK = threading.Lock()

class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

def require(ok, message):
    if not ok:
        raise Problem(400, message)

def items(body):
    rows = body.get('items')
    require(isinstance(rows, list) and 0 < len(rows) <= 20, 'items must contain 1..20 entries')
    for row in rows:
        require(isinstance(row, dict), 'item must be an object')
        require(row.get('sku') in ('book', 'mug', 'shirt'), 'unknown sku')
        require(type(row.get('qty')) is int and 1 <= row['qty'] <= 10, 'qty must be 1..10')
    require(len({r['sku'] for r in rows}) == len(rows), 'duplicate sku')
    return rows

def call(name, path, body=None, headers=None):
    base = os.environ.get(name.upper() + '_URL', 'http://' + name + ':8080')
    data = None if body is None else json.dumps(body).encode()
    req = Request(base + path, data=data, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urlopen(req, timeout=4) as response:
            return json.load(response)
    except HTTPError as error:
        raise Problem(error.code, name + ': ' + error.read(4096).decode()) from error
    except (URLError, TimeoutError) as error:
        raise Problem(503, name + ' unavailable') from error

def serve(route):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print(json.dumps({'service': SERVICE, 'event': 'http', 'message': fmt % args}), flush=True)

        def respond(self, status, value, content_type='application/json'):
            raw = value.encode() if isinstance(value, str) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def handle_request(self):
            global SECONDS
            path = urlsplit(self.path).path
            if path == '/health':
                self.respond(200, {'service': SERVICE, 'status': 'ok'})
                return
            if path == '/metrics':
                with METRIC_LOCK:
                    lines = ['# TYPE shop_requests_total counter']
                    lines += [f'shop_requests_total{{service="{SERVICE}",status="{s}"}} {c}' for s, c in COUNTS.items()]
                    lines += ['# TYPE shop_request_duration_seconds_sum counter', f'shop_request_duration_seconds_sum{{service="{SERVICE}"}} {SECONDS}']
                self.respond(200, '\n'.join(lines) + '\n', 'text/plain; version=0.0.4')
                return
            started = time.monotonic()
            status = 200
            try:
                length = int(self.headers.get('Content-Length', '0'))
                require(0 <= length <= 16384, 'body too large')
                body = json.loads(self.rfile.read(length)) if length else {}
                require(isinstance(body, dict), 'body must be an object')
                result = route(self.command, path, body, self.headers)
            except Problem as error:
                status, result = error.status, {'error': error.message}
            except (ValueError, KeyError, TypeError):
                status, result = 400, {'error': 'invalid input'}
            except Exception as error:
                print(json.dumps({'event': 'exception', 'type': type(error).__name__}), flush=True)
                status, result = 500, {'error': 'internal error'}
            with METRIC_LOCK:
                COUNTS[str(status)] += 1
                SECONDS += time.monotonic() - started
            self.respond(status, result)
        do_GET = handle_request
        do_POST = handle_request
    server = ThreadingHTTPServer((os.environ.get('BIND_HOST', '0.0.0.0'), int(os.environ.get('PORT', '8080'))), Handler)
    server.daemon_threads = True
    server.serve_forever()

if __name__ == '__main__':
    sys.modules['common'] = sys.modules[__name__]
    module = importlib.import_module('service' if os.environ.get('CONTAINER') else 'services.' + SERVICE)
    serve(module.route)
```

## `services/catalog.py`

```python file=services/catalog.py
from common import Problem
PRODUCTS = [
    {'sku': 'book', 'name': 'DevSecOps notebook', 'price_cents': 1500},
    {'sku': 'mug', 'name': 'Kubernetes mug', 'price_cents': 1200},
    {'sku': 'shirt', 'name': 'Ship securely shirt', 'price_cents': 2500},
]
def route(method, path, body, headers):
    if (method, path) == ('GET', '/products'):
        return {'products': PRODUCTS}
    raise Problem(404, 'route not found')
```

## `services/pricing.py`

Prices come from catalog; the caller cannot choose them. Amounts use integer cents.

```python file=services/pricing.py
from common import Problem, call, items
def route(method, path, body, headers):
    if (method, path) == ('POST', '/quote'):
        rows = items(body)
        prices = {p['sku']: p['price_cents'] for p in call('catalog', '/products')['products']}
        return {'currency': 'USD', 'total_cents': sum(prices[r['sku']] * r['qty'] for r in rows)}
    raise Problem(404, 'route not found')
```

## `services/inventory.py`

This is a fixed stock check, not a reservation system: it does not decrement stock or promise transactional inventory.

```python file=services/inventory.py
from common import Problem, items
STOCK = {'book': 10, 'mug': 5, 'shirt': 3}
def route(method, path, body, headers):
    if (method, path) == ('POST', '/check'):
        rows = items(body)
        if any(r['qty'] > STOCK[r['sku']] for r in rows):
            raise Problem(409, 'insufficient demonstration stock')
        return {'available': True}
    raise Problem(404, 'route not found')
```

## `services/cart.py`

```python file=services/cart.py
import threading
from common import Problem, items, require
CARTS = {}
LOCK = threading.Lock()
def route(method, path, body, headers):
    if (method, path) == ('POST', '/cart'):
        rows = items(body)
        cart_id = body.get('cart_id')
        require(isinstance(cart_id, str) and cart_id.isalnum() and len(cart_id) <= 64, 'alphanumeric cart_id required')
        with LOCK:
            if cart_id not in CARTS and len(CARTS) >= 1000:
                raise Problem(503, 'demo capacity reached')
            CARTS[cart_id] = rows
        return {'cart_id': cart_id, 'items': rows}
    if method == 'GET' and path.startswith('/cart/'):
        with LOCK:
            rows = CARTS.get(path.removeprefix('/cart/'))
        if rows is None:
            raise Problem(404, 'cart not found')
        return {'items': rows}
    raise Problem(404, 'route not found')
```

## `services/payments.py`

Use only the two demonstration tokens. No card data or real transfers.

```python file=services/payments.py
import uuid
from common import Problem, require
def route(method, path, body, headers):
    if (method, path) == ('POST', '/authorize'):
        require(type(body.get('total_cents')) is int and body['total_cents'] > 0, 'positive amount required')
        require(body.get('token') in ('demo-approved', 'demo-declined'), 'use a demo token')
        if body['token'] == 'demo-declined':
            raise Problem(402, 'simulated payment declined')
        return {'authorization': 'sim-' + uuid.uuid4().hex, 'simulated': True}
    raise Problem(404, 'route not found')
```

## `services/shipping.py`

```python file=services/shipping.py
from common import Problem, require
def route(method, path, body, headers):
    if (method, path) == ('POST', '/quote'):
        require(body.get('country') in ('IN', 'US', 'GB'), 'supported country: IN, US, GB')
        return {'shipping_cents': 500, 'estimated_days': 5, 'simulated': True}
    raise Problem(404, 'route not found')
```

## `services/notifications.py`

```python file=services/notifications.py
from common import Problem, require
def route(method, path, body, headers):
    if (method, path) == ('POST', '/send'):
        require(isinstance(body.get('order_id'), str), 'order_id required')
        return {'accepted': True, 'channel': 'simulation', 'order_id': body['order_id']}
    raise Problem(404, 'route not found')
```

## `services/recommendations.py`

```python file=services/recommendations.py
from common import Problem, call
def route(method, path, body, headers):
    if (method, path) == ('GET', '/recommendations'):
        return {'recommendations': call('catalog', '/products')['products'][:2]}
    raise Problem(404, 'route not found')
```

## `services/orders.py`

A lock serializes this single-replica exercise. Successful retries return the same order; changing input with a used key returns 409. Failed attempts are not cached. Pod restart loses orders and keys. A real system needs durable idempotency, inventory reservations and compensation. Notification failure is recorded without repeating an already authorized simulated payment.

```python file=services/orders.py
import json
import threading
import uuid
from common import Problem, call, require
ORDERS = {}
LOCK = threading.Lock()
def route(method, path, body, headers):
    if (method, path) != ('POST', '/checkout'):
        raise Problem(404, 'route not found')
    key = headers.get('Idempotency-Key', '')
    require(1 <= len(key) <= 64, 'Idempotency-Key required, max 64 characters')
    cart_id = body.get('cart_id', '')
    require(isinstance(cart_id, str) and cart_id.isalnum() and len(cart_id) <= 64, 'alphanumeric cart_id required')
    require(body.get('country') in ('IN', 'US', 'GB'), 'supported country required')
    require(body.get('token') in ('demo-approved', 'demo-declined'), 'demo token required')
    fingerprint = json.dumps(body, sort_keys=True)
    with LOCK:
        if key in ORDERS:
            previous, order = ORDERS[key]
            if previous != fingerprint:
                raise Problem(409, 'idempotency key reused with different input')
            return order
        if len(ORDERS) >= 1000:
            raise Problem(503, 'demo capacity reached')
        cart = call('cart', '/cart/' + cart_id)
        call('inventory', '/check', cart)
        price = call('pricing', '/quote', cart)
        shipping = call('shipping', '/quote', {'country': body['country']})
        total = price['total_cents'] + shipping['shipping_cents']
        payment = call('payments', '/authorize', {'total_cents': total, 'token': body['token']})
        order = {'order_id': uuid.uuid4().hex, 'total_cents': total, 'currency': 'USD', 'payment': payment, 'simulated': True}
        try:
            order['notification'] = call('notifications', '/send', {'order_id': order['order_id']})
        except Problem:
            order['notification'] = {'accepted': False}
        ORDERS[key] = (fingerprint, order)
        return order
```

## `services/gateway.py`

The gateway is a JSON API, not a browser storefront. It forwards only explicit routes, not arbitrary URLs.

```python file=services/gateway.py
from common import Problem, call
ROUTES = {
    ('GET', '/products'): 'catalog',
    ('GET', '/recommendations'): 'recommendations',
    ('POST', '/cart'): 'cart',
    ('POST', '/checkout'): 'orders',
}
def route(method, path, body, headers):
    target = ROUTES.get((method, path))
    if target is None:
        raise Problem(404, 'route not found')
    return call(target, path, body if method == 'POST' else None,
                {'Idempotency-Key': headers.get('Idempotency-Key', '')})
```

## `tests/integration.py`

Run from the repository root: `python tests/integration.py`. It starts all ten processes locally, checks real HTTP interactions and terminates them. No Azure or Docker required.

```python file=tests/integration.py
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
```
