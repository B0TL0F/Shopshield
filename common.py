import importlib
import json
import os
import sys
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

SERVICE = os.environ.get('SERVICE', 'gateway')
COUNTS = Counter()
SECONDS = 0.0
METRIC_LOCK = threading.Lock()

class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

def require(ok, message):
    if not ok:
        raise Problem(400, message)

def items(body):
    rows = body.get('items')
    require(isinstance(rows, list) and 0 < len(rows) <= 20, 'items must contain 1..20 entries')
    for row in rows:
        require(isinstance(row, dict), 'item must be an object')
        require(row.get('sku') in ('book', 'mug', 'shirt'), 'unknown sku')
        require(type(row.get('qty')) is int and 1 <= row['qty'] <= 10, 'qty must be 1..10')
    require(len({r['sku'] for r in rows}) == len(rows), 'duplicate sku')
    return rows

def call(name, path, body=None, headers=None):
    base = os.environ.get(name.upper() + '_URL', 'http://' + name + ':8080')
    data = None if body is None else json.dumps(body).encode()
    req = Request(base + path, data=data, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urlopen(req, timeout=4) as response:
            return json.load(response)
    except HTTPError as error:
        raise Problem(error.code, name + ': ' + error.read(4096).decode()) from error
    except (URLError, TimeoutError) as error:
        raise Problem(503, name + ' unavailable') from error

def serve(route):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print(json.dumps({'service': SERVICE, 'event': 'http', 'message': fmt % args}), flush=True)

        def respond(self, status, value, content_type='application/json'):
            raw = value.encode() if isinstance(value, str) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def handle_request(self):
            global SECONDS
            path = urlsplit(self.path).path
            if path == '/health':
                self.respond(200, {'service': SERVICE, 'status': 'ok'})
                return
            if path == '/metrics':
                with METRIC_LOCK:
                    lines = ['# TYPE shop_requests_total counter']
                    lines += [f'shop_requests_total{{service="{SERVICE}",status="{s}"}} {c}' for s, c in COUNTS.items()]
                    lines += ['# TYPE shop_request_duration_seconds_sum counter', f'shop_request_duration_seconds_sum{{service="{SERVICE}"}} {SECONDS}']
                self.respond(200, '\n'.join(lines) + '\n', 'text/plain; version=0.0.4')
                return
            started = time.monotonic()
            status = 200
            try:
                length = int(self.headers.get('Content-Length', '0'))
                require(0 <= length <= 16384, 'body too large')
                body = json.loads(self.rfile.read(length)) if length else {}
                require(isinstance(body, dict), 'body must be an object')
                result = route(self.command, path, body, self.headers)
            except Problem as error:
                status, result = error.status, {'error': error.message}
            except (ValueError, KeyError, TypeError):
                status, result = 400, {'error': 'invalid input'}
            except Exception as error:
                print(json.dumps({'event': 'exception', 'type': type(error).__name__}), flush=True)
                status, result = 500, {'error': 'internal error'}
            with METRIC_LOCK:
                COUNTS[str(status)] += 1
                SECONDS += time.monotonic() - started
            self.respond(status, result)
        do_GET = handle_request
        do_POST = handle_request
    server = ThreadingHTTPServer((os.environ.get('BIND_HOST', '0.0.0.0'), int(os.environ.get('PORT', '8080'))), Handler)
    server.daemon_threads = True
    server.serve_forever()

if __name__ == '__main__':
    sys.modules['common'] = sys.modules[__name__]
    module = importlib.import_module('service' if os.environ.get('CONTAINER') else 'services.' + SERVICE)
    serve(module.route)
