"""Check the deployed application through its public gateway URL."""
import json
import os
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def smoke():
    base = os.environ['GATEWAY_URL'].rstrip('/')
    cart_id = 'ci' + uuid.uuid4().hex
    key = cart_id

    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = Request(base + path, data=data, headers={
            'Content-Type': 'application/json', 'Idempotency-Key': key})
        with urlopen(req, timeout=15) as response:
            return json.load(response)

    # Public-IP assignment can precede the load balancer becoming reachable.
    for attempt in range(20):
        try:
            products = request('/products')
            break
        except (URLError, HTTPError, TimeoutError) as error:
            print(f'Gateway {base}/products attempt {attempt + 1}/20 failed: {error}', flush=True)
            if attempt == 19:
                raise RuntimeError(
                    f'Public gateway {base} is unreachable or unhealthy after 20 attempts. '
                    'Check gateway endpoints, load balancer health and the custom subnet NSG '
                    '(public TCP 8080 must be allowed).'
                ) from error
            time.sleep(3)
    if len(products['products']) != 3:
        raise RuntimeError('Expected three catalog products')
    if len(request('/recommendations')['recommendations']) != 2:
        raise RuntimeError('Expected two recommendations')
    request('/cart', {'cart_id': cart_id, 'items': [{'sku': 'book', 'qty': 2}]})
    body = {'cart_id': cart_id, 'country': 'IN', 'token': 'demo-approved'}
    order = request('/checkout', body)
    if order['total_cents'] != 3500:
        raise RuntimeError('Checkout total differs from expected 3500 cents')
    if request('/checkout', body)['order_id'] != order['order_id']:
        raise RuntimeError('Checkout retry did not preserve the order ID')
    print('PASS: public gateway products, recommendations, checkout and idempotency')


if __name__ == '__main__':
    smoke()
