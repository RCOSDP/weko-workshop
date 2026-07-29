#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WEKO3 の Shibboleth ログインを、ブラウザの代わりに一通り実行して確認する。
Drive the whole WEKO3 Shibboleth login the way a browser would, to verify it end to end.

たどる経路 / the path it walks:
  1. GET  https://<tenant>/weko/shib/sp/login   -> /secure/login.py へリダイレクト
  2. GET  /secure/login.py                      -> shibd が IdP の SSO へリダイレクト
  3. POST IdP のログインフォーム                -> SAML Response の自動 POST フォームが返る
  4. POST https://<tenant>/Shibboleth.sso/SAML2/POST -> SP セッション成立、/secure/login.py へ戻る
  5. GET  /secure/login.py (今度は属性つき)     -> login.py が /weko/shib/login へ POST し、
                                                   WEKO のアカウント紐付け画面へ
  6. POST 紐付け (既存 WEKO アカウント) または GET /weko/auto/login (新規作成)
  7. GET  /  -> ログイン済みか確認

依存ライブラリなし (標準ライブラリのみ)。TLS は同梱 CA の自己署名なので検証しない。
No third-party dependencies (standard library only). TLS is not verified because the certificates come
from the bundled self-signed CA.

Usage:
  python3 check-shib-login.py
  python3 check-shib-login.py --host tenant1.localhost --user teacher --password teacher123 --new-user
"""
import argparse
import html as html_mod
import http.client
import http.cookiejar
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------------------------
# *.localhost が ::1 にしか解決されない環境でも kind の公開ポート (127.0.0.1:443) に届くように、
# 接続先だけ 127.0.0.1 に固定しつつ SNI と Host ヘッダは本来のホスト名のままにする。
# curl --resolve と同じことを標準ライブラリでやっている。
# So that requests still reach kind's published port (127.0.0.1:443) on hosts where *.localhost only
# resolves to ::1, pin the connection target to 127.0.0.1 while keeping SNI and the Host header set to
# the real host name. This is the standard-library equivalent of curl --resolve.
# ---------------------------------------------------------------------------------------------
class PinnedHTTPSConnection(http.client.HTTPSConnection):
    resolve_to = None

    def connect(self):
        if not self.resolve_to:
            return super().connect()
        # self.host はポートを除いたホスト名。Host ヘッダも SNI もこれのままにしたいので、
        # 差し替えるのは connect 先のアドレスだけ。
        # self.host is the host name without the port. Both the Host header and SNI must keep it, so
        # only the address we connect to is swapped.
        server_hostname = self.host
        self.sock = self._create_connection(
            (self.resolve_to, self.port or 443), self.timeout, self.source_address)
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname)


class PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, context, resolve_to):
        super().__init__(context=context)
        self._resolve_to = resolve_to

    def https_open(self, req):
        def build(host, **kw):
            kw.pop('context', None)
            conn = PinnedHTTPSConnection(host, context=self._context, **kw)
            conn.resolve_to = self._resolve_to
            return conn
        return self.do_open(build, req)


FORM_RE = re.compile(r'<form\b[^>]*>.*?</form>', re.I | re.S)
FORM_TAG_RE = re.compile(r'<form\b[^>]*>', re.I)
INPUT_RE = re.compile(r'<input\b[^>]*>', re.I)
# 引用符つき/なしの両方を取る。IdP の自動 POST フォームは action も value も HTML エスケープされて
# 出てくる (https&#x3a;&#x2f;&#x2f;... / base64 の "=" など) ので、取り出したあとに必ず unescape する。
# Handles quoted and unquoted values. The IdP's auto-POST form HTML-escapes both the action and the
# values (https&#x3a;&#x2f;&#x2f;..., the "=" padding in base64, ...), so everything is unescaped after
# extraction.
ATTR_RE = re.compile(r'([\w:.-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.I)


def _attrs(tag):
    out = {}
    for name, dq, sq, bare in ATTR_RE.findall(tag):
        value = dq if dq else (sq if sq else bare)
        out[name.lower()] = html_mod.unescape(value)
    return out


def parse_forms(body):
    """<form> を (action, {name: value}) の一覧にする / turn <form>s into (action, {name: value})."""
    forms = []
    for chunk in FORM_RE.findall(body):
        tag = FORM_TAG_RE.match(chunk)
        action = _attrs(tag.group(0)).get('action', '') if tag else ''
        fields = {}
        for itag in INPUT_RE.findall(chunk):
            attrs = _attrs(itag)
            name = attrs.get('name')
            if name:
                fields[name] = attrs.get('value', '')
        forms.append((action, fields))
    return forms


class Browser:
    def __init__(self, resolve_to):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            PinnedHTTPSHandler(ctx, resolve_to),
        )
        self.opener.addheaders = [('User-Agent', 'weko-shib-check/1.0')]

    def open(self, url, data=None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        try:
            resp = self.opener.open(url, body, timeout=60)
        except urllib.error.HTTPError as e:
            resp = e
        html = resp.read().decode('utf-8', 'replace')
        return resp.status, resp.geturl(), html


def fail(step, detail):
    print('  NG  %s' % step)
    print('      %s' % detail.replace('\n', '\n      ')[:1500])
    sys.exit(1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--host', default='tenant1.localhost', help='WEKO3 のホスト / the WEKO3 host')
    p.add_argument('--user', default='admin', help='IdP のログイン ID / the IdP login id')
    p.add_argument('--password', default='admin123')
    p.add_argument('--weko-account', default='admin@example.org',
                   help='紐付ける既存 WEKO アカウント / the existing WEKO account to link to')
    p.add_argument('--weko-password', default='adminpass123')
    p.add_argument('--new-user', action='store_true',
                   help='既存アカウントに紐付けず新規 WEKO ユーザを作る / create a new WEKO user instead')
    p.add_argument('--resolve', default='127.0.0.1',
                   help='全ホスト名の接続先 IP / the IP every host name connects to')
    args = p.parse_args()

    base = 'https://%s' % args.host
    b = Browser(args.resolve)

    print('== 1) %s/weko/shib/sp/login' % base)
    status, url, html = b.open(base + '/weko/shib/sp/login?next=%2F')
    print('  -> %s %s' % (status, url))
    if status != 200:
        fail('the SP login entry point did not return 200', html)
    if '/idp/' not in url and 'SAMLRequest' not in html:
        fail('did not reach the IdP (shibd may not have redirected)', html)

    # IdP はログインフォームの前後に JavaScript 前提の中間ページ (localStorage の読み書き) を挟む。
    # ブラウザではない以上そこは素通しするしかないので、SAMLResponse が出るまでフォームを送り続ける。
    # The IdP wraps the login form in JavaScript-driven intermediate pages (localStorage read/write).
    # We are not a browser, so just submit them as-is and keep going until a SAMLResponse appears.
    print('== 2) IdP login form (%s / %s)' % (args.user, args.password))
    creds_sent = False
    for _ in range(8):
        forms = parse_forms(html)
        if any('SAMLResponse' in f for _a, f in forms):
            break
        login_form = next(((a, f) for a, f in forms if 'j_username' in f or 'j_password' in f), None)
        if login_form and creds_sent:
            fail('the IdP showed the login form again (wrong credentials?)', html)
        if login_form:
            action, fields = login_form
            fields['j_username'] = args.user
            fields['j_password'] = args.password
            creds_sent = True
            print('  submitting the credentials')
        elif forms:
            action, fields = forms[-1]
            print('  passing through an intermediate IdP page')
        else:
            fail('the IdP page has no form', html)
        fields['_eventId_proceed'] = ''
        status, url, html = b.open(urllib.parse.urljoin(url, action), fields)
        print('  -> %s %s' % (status, url))
    if not creds_sent:
        fail('never reached the IdP login form', html)

    print('== 3) SAML Response -> SP ACS')
    forms = parse_forms(html)
    saml = next(((a, f) for a, f in forms if 'SAMLResponse' in f), None)
    if not saml:
        fail('the IdP did not return a SAMLResponse (bad credentials or attribute release?)', html)
    action, fields = saml
    acs = urllib.parse.urljoin(url, action)
    print('  ACS = %s' % acs)
    status, url, html = b.open(acs, fields)
    print('  -> %s %s' % (status, url))
    if status != 200:
        fail('the assertion was rejected by the SP', html)

    print('== 4) WEKO account linking')
    if '/weko/confim/user' in html or 'WEKO_ATTR_ACCOUNT' in html:
        if args.new_user:
            print('  -> creating a new WEKO user (auto/login)')
            status, url, html = b.open(base + '/weko/auto/login')
        else:
            forms = parse_forms(html)
            action, fields = next((a, f) for a, f in forms if 'WEKO_ATTR_ACCOUNT' in f)
            fields['WEKO_ATTR_ACCOUNT'] = args.weko_account
            fields['WEKO_ATTR_PWD'] = args.weko_password
            print('  -> linking to the existing account %s' % args.weko_account)
            status, url, html = b.open(urllib.parse.urljoin(url, action), fields)
        print('  -> %s %s' % (status, url))
    else:
        print('  -> already linked, logged in directly')

    print('== 5) confirming the session')
    status, url, html = b.open(base + '/')
    names = sorted({c.name for c in self_cookies(b)})
    print('  -> %s %s' % (status, url))
    print('  cookies: %s' % ', '.join(names))
    if not any(n.startswith('_shibsession_') for n in names):
        fail('no Shibboleth SP session cookie', 'cookies=%s' % names)
    if 'session' not in names:
        fail('no WEKO (Flask) session cookie', 'cookies=%s' % names)
    if '/logout' not in html and 'logout' not in html.lower():
        fail('the top page does not look logged in (no logout link)', html[:1500])

    print('')
    print('OK: %s logged in to %s through the Shibboleth IdP' % (args.user, args.host))


def self_cookies(b):
    return list(b.jar)


if __name__ == '__main__':
    main()
