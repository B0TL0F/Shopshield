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
