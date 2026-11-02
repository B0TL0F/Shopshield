import uuid
from common import Problem, require
def route(method, path, body, headers):
    if (method, path) == ('POST', '/authorize'):
        require(type(body.get('total_cents')) is int and body['total_cents'] > 0, 'positive amount required')
        require(body.get('token') in ('demo-approved', 'demo-declined'), 'use a demo token')
        if body['token'] == 'demo-declined':
            raise Problem(402, 'simulated payment declined')
        return {'authorization': 'sim-' + uuid.uuid4().hex, 'simulated': True}
    raise Problem(404, 'route not found')
