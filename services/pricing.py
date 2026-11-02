from common import Problem, call, items
def route(method, path, body, headers):
    if (method, path) == ('POST', '/quote'):
        rows = items(body)
        prices = {p['sku']: p['price_cents'] for p in call('catalog', '/products')['products']}
        return {'currency': 'USD', 'total_cents': sum(prices[r['sku']] * r['qty'] for r in rows)}
    raise Problem(404, 'route not found')
