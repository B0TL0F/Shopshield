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
