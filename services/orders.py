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
