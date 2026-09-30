"""A stand-in for the Shibboleth SP's login script.

WEKO is not the thing that speaks SAML.  The SP does, in nginx, and what
reaches WEKO is an ordinary POST of the attributes the IdP released --
``nginx/login.py`` is the script that makes it.  So a test does not need
an IdP to exercise the login that follows it; it needs to stand where
that script stands and send what it sends.

Which is the whole of this file.  ``e2ectl`` copies it into the **nginx**
container and runs it there, because that is where ``login.py`` runs and
because WEKO checks where the POST came from:

    @shib_sp_source_required          # weko_accounts/views.py, 2.1.0
    def shib_sp_login():
        allowed = config['WEKO_ACCOUNTS_SHIB_SP_ALLOWED_ADDRS']
        if request.remote_addr not in allowed:
            abort(403)

Standing in the right place is the point.  Nothing here widens that
list, and nothing here should: an instance that accepts these attributes
from anywhere is an instance anyone can log into as anyone.

``POST /weko/shib/login`` answers with a path rather than a redirect, and
the session is made by whoever *follows* it -- so this prints the path
and the caller's own browser walks in with it.

The attributes go out under both the names the SP's nginx configuration
uses (``eppn``, ``mail``) and the keys WEKO falls back to when no
attribute mapping is set (``SHIB_ATTR_EPPN``, ``SHIB_ATTR_MAIL``).  A
real SP sends one of them, decided by ``shib_fastcgi_params``; sending
both means the stand-in works whichever way an instance is mapped.

This runs under the nginx container's Python 3, with the ``requests``
that ``login.py`` already needs.
"""

from __future__ import print_function

import json
import sys
import uuid

MARKER = 'WEKO_E2E_SHIB: '
"""Prefix of the one line ``e2ectl`` reads back."""

LOGIN_PATH = '/weko/shib/login'
"""Where the SP's script posts what the IdP released."""

FASTCGI_NAMES = {
    'eppn': 'eppn',
    'mail': 'mail',
    'user_name': 'DisplayName',
    'is_member_of': 'isMemberOf',
    'organization': 'jao',
}
"""What the SP's nginx configuration calls each attribute."""

CONFIG_NAMES = {
    'eppn': 'SHIB_ATTR_EPPN',
    'mail': 'SHIB_ATTR_MAIL',
    'user_name': 'SHIB_ATTR_USER_NAME',
    'is_member_of': 'SHIB_ATTR_IS_MEMBER_OF',
    'organization': 'SHIB_ATTR_ORGANIZATION',
    'role_authority_name': 'SHIB_ATTR_ROLE_AUTHORITY_NAME',
    'ip_range_flag': 'SHIB_ATTR_SITE_USER_WITHIN_IP_RANGE_FLAG',
}
"""What WEKO calls each attribute when no mapping has been configured."""


def form_data(attributes, session_id):
    """Return the form the SP's script would post.

    :param attributes: ``{'eppn': ..., 'mail': ..., ...}``
    :param session_id: the SP's session identifier, which WEKO caches
        the attributes under and hands back in the URL
    """
    data = {'Shib-Session-ID': session_id}
    for key, value in attributes.items():
        if value is None:
            continue
        for names in (FASTCGI_NAMES, CONFIG_NAMES):
            if key in names:
                data[names[key]] = value
    return data


def login(base_url, attributes, session_id=None, next_url='/'):
    """Post the attributes the way the SP's script does.

    :return: ``{'status': ..., 'next': ..., 'session_id': ...}`` where
        ``next`` is the path whoever wants the session must follow
    """
    import requests

    session_id = session_id or '_{0}'.format(uuid.uuid4().hex)
    url = '{0}{1}?next={2}'.format(base_url.rstrip('/'), LOGIN_PATH, next_url)
    response = requests.post(url, data=form_data(attributes, session_id),
                             verify=False, timeout=120)
    answer = {'status': response.status_code, 'session_id': session_id,
              'next': None, 'said': ''}
    body = (response.text or '').strip()
    if response.ok and body.startswith('/'):
        answer['next'] = body
    else:
        # A page rather than a path: WEKO refused, and the page says why.
        answer['said'] = body[:400]
    return answer


def main(argv):
    """Log in as the attributes given on the command line."""
    import urllib3

    urllib3.disable_warnings()
    base_url = argv[0]
    attributes = json.loads(argv[1])
    session_id = argv[2] if len(argv) > 2 else None
    print(MARKER + json.dumps(login(base_url, attributes, session_id)))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as error:  # the caller wants the reason, not a trace
        print(MARKER + json.dumps({'status': 0, 'next': None,
                                   'said': str(error)}))
        sys.exit(1)
