"""A stand-in for an ARK server, so the ARK suite can run anywhere.

Minting an ARK means calling an ARK server, and most environments do not
have one.  ``e2ectl ark-stub enable`` copies this into the ``web``
container and runs it on the loopback interface there, which is where
WEKO mints from, so nothing has to be reachable over the network and no
account anywhere is needed.

It answers the two endpoints ``weko_workflow.utils`` talks to:

``POST /login``
    ``{"token": "..."}``, for the password flow.
``POST /mint``
    ``{"data": {"ark": "ark:/<naan>/<shoulder><n>"}}``, built from the
    ``naan`` and ``shoulder`` of the request, so the ARK that comes back
    is the one the settings asked for.

Every mint is appended to a log file, so a run can be told apart from a
stale ARK left by an earlier one.

This runs under the container's Python 3.6: keep it to what 3.6 accepts,
and to the standard library.
"""

from __future__ import print_function

import json
import os
import sys
import threading
from datetime import datetime

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:  # pragma: no cover - python 2, not expected
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

TOKEN = 'weko-e2e-ark-stub-token'
LOG_PATH = '/tmp/weko-e2e-ark-stub.log'

_counter = {'n': 0}
_lock = threading.Lock()


def _next_suffix():
    """Return a mint number that no other mint of this process reuses."""
    with _lock:
        _counter['n'] += 1
        return _counter['n']


class Handler(BaseHTTPRequestHandler):
    """The two endpoints WEKO asks an ARK server for."""

    def _reply(self, status, payload):
        """Send one JSON response."""
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        """Return the request body, parsed, or an empty dict."""
        length = int(self.headers.get('Content-Length') or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except ValueError:
            return {}

    def do_POST(self):  # noqa: N802 - the name BaseHTTPRequestHandler wants
        """Answer a login or a mint."""
        request = self._body()
        if self.path.rstrip('/').endswith('login'):
            self._reply(200, {'token': TOKEN})
            return
        if not self.path.rstrip('/').endswith('mint'):
            self._reply(404, {'error': 'no such endpoint'})
            return

        naan = str(request.get('naan') or '99999')
        shoulder = str(request.get('shoulder') or 'fk4')
        ark = 'ark:/{0}/{1}{2:05d}'.format(naan, shoulder, _next_suffix())
        _log('mint url={0} -> {1}'.format(request.get('url'), ark))
        self._reply(200, {'data': {'ark': ark}})

    def log_message(self, fmt, *args):
        """Send the access log to the file rather than to stderr."""
        _log('access ' + (fmt % args))


def _log(line):
    """Append one line to the stub's log."""
    try:
        with open(LOG_PATH, 'a') as handle:
            handle.write('{0} {1}\n'.format(datetime.now().isoformat(), line))
    except IOError:
        pass


def main(port):
    """Serve until killed."""
    _log('started on port {0} (pid {1})'.format(port, os.getpid()))
    HTTPServer(('127.0.0.1', port), Handler).serve_forever()


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8899)
