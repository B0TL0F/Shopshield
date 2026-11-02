from common import Problem, call
def route(method, path, body, headers):
    if (method, path) == ('GET', '/recommendations'):
        return {'recommendations': call('catalog', '/products')['products'][:2]}
    raise Problem(404, 'route not found')
