from common import Problem, require
def route(method, path, body, headers):
    if (method, path) == ('POST', '/quote'):
        require(body.get('country') in ('IN', 'US', 'GB'), 'supported country: IN, US, GB')
        return {'shipping_cents': 500, 'estimated_days': 5, 'simulated': True}
    raise Problem(404, 'route not found')
