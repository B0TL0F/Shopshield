from common import Problem, items
STOCK = {'book': 10, 'mug': 5, 'shirt': 3}
def route(method, path, body, headers):
    if (method, path) == ('POST', '/check'):
        rows = items(body)
        if any(r['qty'] > STOCK[r['sku']] for r in rows):
            raise Problem(409, 'insufficient demonstration stock')
        return {'available': True}
    raise Problem(404, 'route not found')
