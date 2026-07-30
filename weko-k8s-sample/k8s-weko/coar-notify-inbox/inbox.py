#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""COAR Notify / LDN の inbox（検証用の最小実装）。
A minimal LDN (Linked Data Notifications) inbox for verifying COAR Notify.

WEKO3 の weko-notifications は「送信側と閲覧側」しか持たない。inbox 本体は外部サービスであり、
既定では WEKO_NOTIFICATIONS_INBOX_ADDRESS = "http://inbox:8080" を向いている。これはその宛先を
クラスタ内に用意するためのもので、本番の inbox の代替物である（永続化しない = 再起動で消える）。

WEKO3's weko-notifications only implements the sender and the reader side. The inbox itself is an
external service, and the default WEKO_NOTIFICATIONS_INBOX_ADDRESS is "http://inbox:8080". This
provides that endpoint inside the cluster; it stands in for the real inbox and keeps everything in
memory (a restart loses the notifications).

実装しているのは py-ldnlib 0.1.3 が実際に使う分だけ。ldnlib/sender.py と consumer.py から:
Only what py-ldnlib 0.1.3 actually uses is implemented. From ldnlib/sender.py and consumer.py:

  POST <inbox>          Content-Type: application/ld+json、2xx を返すこと
                        (Sender.__post_message が raise_for_status する)
                        Content-Type: application/ld+json; must answer 2xx
                        (Sender.__post_message calls raise_for_status)
  GET  <inbox>          Accept: application/ld+json。rdflib でパースされ ldp:contains の
                        オブジェクトが通知 IRI のリストになる (Consumer.notifications)
                        Parsed with rdflib; the objects of ldp:contains become the list of
                        notification IRIs (Consumer.notifications)
  GET  <inbox>/<slug>   通知そのもの (Consumer.notification)
                        The notification itself (Consumer.notification)
  OPTIONS <inbox>       Accept-Post ヘッダ (Sender が Graph を送るときだけ見る)
                        The Accept-Post header (only consulted when the Sender posts a Graph)
  HEAD  /               ldp#inbox の Link ヘッダ (BaseLDN.discover 用)
                        The ldp#inbox Link header (for BaseLDN.discover)

WEKO 側の絞り込み: weko_notifications/views.py の /api/notifications は
?target=<THEME_SITEURL>/users/<id> を付けて GET する。通知の target.id と突き合わせる。
Filtering on the WEKO side: /api/notifications in weko_notifications/views.py issues the GET with
?target=<THEME_SITEURL>/users/<id>, which is matched against the notification's target.id.
"""
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

JSONLD = "application/ld+json"
# 通知 IRI の組み立てに使うベース URL。weko_notifications/views.py は返ってきた IRI に対して
# inbox_url() -> inbox_url(_external=True) の文字列置換をかけるので、ここは WEKO が設定している
# WEKO_NOTIFICATIONS_INBOX_ADDRESS + _ENDPOINT と完全に一致していなければならない。
# The base URL the notification IRIs are built from. views.py string-replaces inbox_url() with
# inbox_url(_external=True) on the returned IRIs, so this must match WEKO's configured
# WEKO_NOTIFICATIONS_INBOX_ADDRESS + _ENDPOINT exactly.
BASE = os.environ.get("INBOX_BASE_URL", "http://inbox:8080/inbox").rstrip("/")
INBOX_PATH = (urlparse(BASE).path or "/inbox").rstrip("/")
# 変数名に注意: Service を "inbox" という名前で作ると、Kubernetes が同じ名前空間の全 Pod に
# Docker link 形式の環境変数を注入する (INBOX_PORT=tcp://10.96.x.x:8080 など)。つまり
# INBOX_PORT は使えない。LISTEN_PORT のように衝突しない名前にすること。
# Mind the variable name: naming the Service "inbox" makes Kubernetes inject Docker-link style
# variables into every Pod in the namespace (INBOX_PORT=tcp://10.96.x.x:8080 and friends), so
# INBOX_PORT is unusable here. Use a non-colliding name such as LISTEN_PORT.
PORT = int(os.environ.get("LISTEN_PORT", "8080"))

# 受信した通知。検証用なのでメモリのみ / received notifications, in memory only (this is for testing)
STORE = {}
ORDER = []


def slug_for(payload):
    """通知 ID から URL に使える slug を作る / build a URL-safe slug from the notification id."""
    raw = str(payload.get("id") or "")
    s = re.sub(r"[^A-Za-z0-9._-]", "-", raw).strip("-")
    return s or uuid.uuid4().hex


def type_of(payload):
    t = payload.get("type")
    return ", ".join(t) if isinstance(t, list) else str(t)


class Handler(BaseHTTPRequestHandler):
    server_version = "weko-ldn-inbox/1.0"
    protocol_version = "HTTP/1.1"

    def _send(self, code, body=b"", ctype=JSONLD, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, code, obj, extra=None):
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(code, body, JSONLD, extra)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---- LDN の発見 / LDN discovery ----
    def do_OPTIONS(self):
        self._send(204, b"", JSONLD,
                   {"Accept-Post": JSONLD, "Allow": "GET, HEAD, POST, OPTIONS"})

    def do_HEAD(self):
        self._send(200, b"", JSONLD,
                   {"Link": '<%s>; rel="http://www.w3.org/ns/ldp#inbox"' % BASE})

    # ---- 受信 / receiving ----
    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if path != INBOX_PATH:
            return self._json(404, {"error": "not an inbox: %s" % path})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:
            return self._json(400, {"error": "invalid JSON: %s" % exc})
        if not isinstance(payload, dict):
            return self._json(400, {"error": "the payload must be a JSON object"})

        slug = slug_for(payload)
        payload["_received"] = datetime.now(timezone.utc).isoformat()
        if slug not in STORE:
            ORDER.append(slug)
        STORE[slug] = payload
        location = "%s/%s" % (BASE, slug)

        # kubectl logs でそのまま読めるように、受信内容を丸ごと出す
        # Dump the whole notification so that kubectl logs shows it directly
        print("[RECV] type=%s target=%s object=%s -> %s"
              % (type_of(payload),
                 (payload.get("target") or {}).get("id"),
                 (payload.get("object") or {}).get("id"),
                 location), flush=True)
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)

        self._send(201, b"", JSONLD, {"Location": location})

    # ---- 閲覧 / reading ----
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/health":
            return self._send(200, b'{"status":"ok"}', "application/json")

        if path == INBOX_PATH:
            target = parse_qs(parsed.query).get("target", [None])[0]
            slugs = [s for s in ORDER
                     if not target
                     or (STORE[s].get("target") or {}).get("id") == target]
            # ldp:contains のオブジェクトが通知 IRI になる。rdflib でパースできる JSON-LD なら
            # 形は自由なので、最小のコンテナ表現にしている。
            # The objects of ldp:contains become the notification IRIs. Any JSON-LD rdflib can parse
            # works, so this is the smallest container representation that does the job.
            return self._json(200, {
                "@context": {"ldp": "http://www.w3.org/ns/ldp#"},
                "@id": BASE,
                "@type": "ldp:Container",
                "ldp:contains": [{"@id": "%s/%s" % (BASE, s)} for s in slugs],
            })

        if path.startswith(INBOX_PATH + "/"):
            slug = path[len(INBOX_PATH) + 1:]
            if slug in STORE:
                return self._json(200, STORE[slug])
            return self._json(404, {"error": "no such notification: %s" % slug})

        if path == "/":
            return self._send(200, self._index_html(), "text/html; charset=utf-8")

        return self._json(404, {"error": "not found: %s" % path})

    def _index_html(self):
        """ブラウザで中身を見るための一覧 / a listing so the contents can be read in a browser."""
        rows = []
        for slug in reversed(ORDER):
            p = STORE[slug]
            rows.append(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                "<td><a href=\"%s/%s\">%s</a></td></tr>"
                % (p.get("_received", ""), type_of(p),
                   (p.get("target") or {}).get("id", ""),
                   ((p.get("object") or {}).get("name") or ""),
                   INBOX_PATH, slug, slug))
        return ("<!doctype html><meta charset=utf-8><title>WEKO LDN inbox</title>"
                "<style>body{font-family:sans-serif;margin:2rem}"
                "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.3rem .6rem}"
                "</style><h1>WEKO LDN inbox</h1>"
                "<p>base = <code>%s</code> / %d notification(s)</p>"
                "<table><tr><th>received</th><th>type</th><th>target</th>"
                "<th>object</th><th>id</th></tr>%s</table>"
                % (BASE, len(ORDER), "".join(rows))).encode("utf-8")


if __name__ == "__main__":
    print("weko-ldn-inbox listening on :%d (base=%s, path=%s)"
          % (PORT, BASE, INBOX_PATH), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
