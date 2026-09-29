"""A stand-in for a browser's Web Push subscription.

A Web Push subscription is an endpoint the sender POSTs an encrypted
payload to, together with the keys it is encrypted for.  A real one comes
from a browser's push service -- Google's or Mozilla's -- which a run
against a local stack cannot reach and should not depend on.

``e2ectl webpush-stub enable`` copies this into the ``inbox`` container
and runs it on the loopback interface there, which is where the inbox
sends from, and it plays the part a browser would: it holds a
subscription key pair of its own, registers itself with the inbox the way
WEKO's notification settings screen registers a real subscription, and
decrypts what arrives so a test can read what the user would have been
shown.

``GET /subscription``
    the subscription as the inbox knows it, keys included.
``POST /subscribe``
    ``{"target": "<user uri>", "language": "en", "displayname": "..."}``;
    registers this subscription and that user profile with the inbox.
``POST /unsubscribe``
    takes the subscription away again.
``GET /received``
    every push that has arrived, decrypted, newest last.
``POST /push``
    where the inbox delivers; the payload is decrypted and recorded.

Running it with ``--stop`` stops whatever copy of it is already serving
in the container, which is how ``e2ectl`` takes it down: the inbox's
image carries no ``pkill``.

This runs under the inbox container's Python 3.12, and uses the
``cryptography`` and ``http_ece`` that are already there because the
inbox sends Web Push with them.
"""

import base64
import json
import os
import sys
import threading
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

# ``cryptography`` and ``http_ece`` are imported where they are used
# rather than here, so that ``e2ectl`` -- which runs outside the
# container and has neither -- can still read the paths below.

INBOX = 'http://127.0.0.1:8080'
"""Where the inbox answers, from inside its own container."""

LOG_PATH = '/tmp/weko-e2e-push-stub.log'
STATE_PATH = '/tmp/weko-e2e-push-stub.json'
"""Where the subscription is written, so a caller can read it back."""

PUSH_PATH = '/push'
"""The path the inbox delivers to; everything else is control."""


def _b64(raw):
    """Return base64url without padding, as Web Push spells its keys."""
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def _unb64(text):
    """Return the bytes of a base64url string that may have lost padding."""
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


class Subscription(object):
    """The keys a browser would have generated, and what arrived for them."""

    def __init__(self, port):
        """Generate the subscription this stub stands for."""
        from cryptography.hazmat.primitives.asymmetric import ec

        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.auth = _b64(os.urandom(16))
        self.endpoint = 'http://127.0.0.1:{0}{1}'.format(port, PUSH_PATH)
        self.received = []
        self._lock = threading.Lock()

    @property
    def p256dh(self):
        """Return the public key the payload is encrypted for."""
        from cryptography.hazmat.primitives import serialization

        return _b64(self.private_key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint))

    def as_dict(self):
        """Return the subscription the way the browser hands it over."""
        return {
            'endpoint': self.endpoint,
            'expirationTime': None,
            'keys': {'p256dh': self.p256dh, 'auth': self.auth},
        }

    def record(self, body):
        """Decrypt one delivered push and remember what it said."""
        import http_ece

        payload = http_ece.decrypt(
            body, private_key=self.private_key,
            auth_secret=_unb64(self.auth), version='aes128gcm')
        entry = {'at': datetime.now().isoformat(timespec='seconds'),
                 'payload': json.loads(payload.decode('utf-8'))}
        with self._lock:
            self.received.append(entry)
        _log('push {0}'.format(json.dumps(entry['payload'])))
        return entry

    def snapshot(self):
        """Return what has arrived so far."""
        with self._lock:
            return list(self.received)


def _post(path, payload):
    """POST one JSON body to the inbox and return its status."""
    request = urllib.request.Request(
        INBOX + path, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


class Handler(BaseHTTPRequestHandler):
    """The endpoints the tool and the inbox talk to."""

    subscription = None

    def _reply(self, status, payload):
        """Send one JSON response."""
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        """Return the request body, raw."""
        length = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(length) if length else b''

    def do_GET(self):  # noqa: N802 - the name BaseHTTPRequestHandler wants
        """Answer for the subscription, or for what has arrived."""
        path = self.path.rstrip('/')
        if path.endswith('/subscription'):
            self._reply(200, self.subscription.as_dict())
        elif path.endswith('/received'):
            self._reply(200, {'received': self.subscription.snapshot()})
        else:
            self._reply(404, {'error': 'no such endpoint'})

    def do_POST(self):  # noqa: N802 - the name BaseHTTPRequestHandler wants
        """Take a delivered push, or a request to (un)subscribe."""
        path = self.path.rstrip('/')
        body = self._body()
        if path.endswith(PUSH_PATH):
            try:
                self.subscription.record(body)
            except Exception as error:  # the payload is the thing under test
                _log('undecryptable push: {0}'.format(error))
                self._reply(400, {'error': str(error)})
                return
            self._reply(201, {})
            return

        request = json.loads(body.decode('utf-8')) if body else {}
        if path.endswith('/subscribe'):
            self._reply(200, self._subscribe(request))
        elif path.endswith('/unsubscribe'):
            self._reply(200, {'unsubscribe': _post(
                '/unsubscribe', {'endpoint': self.subscription.endpoint})})
        else:
            self._reply(404, {'error': 'no such endpoint'})

    def _subscribe(self, request):
        """Register this subscription, the way the settings screen does.

        WEKO posts the subscription and the user's profile together; the
        profile is what the inbox renders the message in the language of,
        and it has no push to send without it.
        """
        target = request['target']
        payload = self.subscription.as_dict()
        payload['target'] = target
        return {
            'subscribe': _post('/subscribe', payload),
            'userprofile': _post('/userprofile', {
                'uri': target,
                'displayname': request.get('displayname') or 'WEKO E2E',
                'language': request.get('language') or 'en',
                'timezone': request.get('timezone') or 'GMT+9:00',
            }),
        }

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


def stop():
    """Stop any copy of this stub already serving in this container.

    The inbox's image has neither ``pkill`` nor ``ps``, so the processes
    are found by reading ``/proc``.  A process that ends while this is
    looking at it is not an error; nor is there being none.

    :return: the pids that were asked to stop
    """
    import signal

    marker = os.path.basename(__file__).encode('utf-8')
    stopped = []
    for entry in os.listdir('/proc'):
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        try:
            with open('/proc/{0}/cmdline'.format(entry), 'rb') as handle:
                if marker not in handle.read():
                    continue
            os.kill(int(entry), signal.SIGTERM)
        except OSError:
            continue
        stopped.append(int(entry))
    return stopped


def main(port):
    """Serve until killed."""
    Handler.subscription = Subscription(port)
    with open(STATE_PATH, 'w') as handle:
        json.dump(Handler.subscription.as_dict(), handle)
    _log('started on port {0} (pid {1})'.format(port, os.getpid()))
    HTTPServer(('127.0.0.1', port), Handler).serve_forever()


if __name__ == '__main__':
    if '--stop' in sys.argv:
        print(json.dumps({'stopped': stop()}))
    else:
        main(int(sys.argv[1]) if len(sys.argv) > 1 else 8901)
