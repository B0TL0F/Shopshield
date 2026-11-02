from common import Problem, require
def route(method, path, body, headers):
    if (method, path) == ('POST', '/send'):
        require(isinstance(body.get('order_id'), str), 'order_id required')
        return {'accepted': True, 'channel': 'simulation', 'order_id': body['order_id']}
    raise Problem(404, 'route not found')
