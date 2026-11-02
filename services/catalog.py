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
