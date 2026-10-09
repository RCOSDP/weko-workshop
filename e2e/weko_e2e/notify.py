"""COAR Notify: what the instance announces, and what reached the inbox.

WEKO is only the *sender*.  A workflow event -- an item offered for
approval, an item approved -- becomes a COAR Notify message and is POSTed
to an LDN inbox, which in a stack from ``install.sh`` is a container of
its own; the inbox stores it and WEKO reads it back for the user it was
addressed to at ``GET /api/notifications``.

So this module works the way a COAR Notify client would: it asks the site
top page where the inbox is, and then asks WEKO, as a logged in user, what
that user has been sent.  Nothing here reaches into the inbox container.

The notification URLs WEKO hands back are built from ``THEME_SITEURL``,
which is what the *instance* calls itself and need not be the address the
run is testing -- a default stack calls itself ``weko3.example.org`` while
answering on ``localhost`` -- so a notification is fetched by its path
from the instance under test rather than from the URL as written.
"""

import re
import time
from urllib.parse import urlparse

import requests

API_PATH = '/api/notifications'
"""Where WEKO offers a logged in user the notifications addressed to them."""

LINK_REL = 'http://www.w3.org/ns/ldp#inbox'
"""The link relation an LDN sender follows to find a target's inbox."""

CONTEXT = [
    'https://www.w3.org/ns/activitystreams',
    'https://coar-notify.net',
]
"""The ``@context`` every COAR Notify message carries."""

OFFER_ENDORSE = ['Offer', 'coar-notify:EndorsementAction']
ANNOUNCE_ENDORSE = ['Announce', 'coar-notify:EndorsementAction']
ANNOUNCE_INGEST = ['Announce', 'coar-notify:IngestAction']
REJECT = ['Reject']
"""The patterns WEKO sends: offered for approval, approved, registered,
rejected.  A deletion carries the same pattern with ``Delete`` after it."""

USER_URI = re.compile(r'/users/\d+$')
"""What the ``id`` of a person WEKO addresses looks like."""


def announced_inbox(session, settings):
    """Return the inbox the instance announces, or None.

    LDN discovery: a consumer asks the target for the ``ldp#inbox`` link.
    WEKO adds it to **HEAD of the site top page only** -- a GET does not
    carry it -- so that is what is asked.

    :param session: a :mod:`requests` session; it need not be logged in
    :return: the inbox URL the instance published, or None
    """
    response = session.head(settings.url('/'), timeout=60)
    return (response.links.get(LINK_REL) or {}).get('url')


PROBE_PATH = '/inbox/weko-e2e-no-such-notification'
"""A notification id no inbox has, for asking whether one is there.

The inbox answers JSON even when it has nothing -- an id it does not know
is a 404 with a body of its own -- while the 404 of a site that is not
serving an inbox at all is a page.  That is the difference this looks
for, because an announced inbox is only a `Link:` header and says
nothing about whether anything is behind it.
"""


def inbox_answers(session, settings):
    """Return whether something is serving the announced inbox path.

    :param session: a :mod:`requests` session; it need not be logged in
    """
    try:
        response = session.get(settings.url(PROBE_PATH), timeout=60)
    except requests.RequestException:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and 'detail' in body


def notifications(session, settings):
    """Return the notification URLs addressed to a session's user.

    Newest first, and at most the 50 the inbox returns in one page.

    :param session: a session logged in as the user whose notifications
        these are
    :raise AssertionError: when WEKO does not answer with the list
    """
    response = session.get(settings.url(API_PATH), timeout=60)
    assert response.status_code == 200, \
        'GET {0} answered {1}: {2}'.format(
            API_PATH, response.status_code, response.text[:200])
    return response.json().get('notifications') or []


def fetch(session, settings, url):
    """Return one notification, read from the instance under test.

    :param url: the notification URL as WEKO wrote it, whose host is the
        instance's own ``THEME_SITEURL``
    :return: the payload
    :raise AssertionError: when the inbox does not hand it over
    """
    path = urlparse(url).path
    response = session.get(settings.url(path), timeout=60)
    assert response.status_code == 200, \
        'the inbox answered {0} for {1}'.format(response.status_code, path)
    return response.json()


def is_about(payload, activity_id):
    """Return whether a notification is about one workflow activity.

    Every notification WEKO sends about an activity carries the URL of
    that activity's detail page as its ``context``, which is the only
    thing in the payload that names the run's own activity.
    """
    context = (payload.get('context') or {}).get('id') or ''
    return context.rstrip('/').endswith(str(activity_id))


def wait_for(session, settings, activity_id, activity_type, timeout,
             seen=(), interval=3):
    """Wait for one notification about an activity, and return it.

    WEKO sends the notification while it is finishing the action, so it
    is usually there by the time the screen comes back -- but the inbox
    is a separate service and this does not depend on that.

    :param seen: the notification URLs that were in the inbox *before*
        the action; only what arrived after them is fetched, so an
        instance with a long history costs one request per new
        notification rather than one per notification it holds
    :param activity_type: the COAR Notify ``type`` to wait for, e.g.
        :data:`OFFER_ENDORSE`
    :return: the payload, or None when none arrived within *timeout*
    """
    known = set(seen)
    deadline = time.time() + timeout
    while True:
        for url in notifications(session, settings):
            if url in known:
                continue
            known.add(url)
            payload = fetch(session, settings, url)
            if is_about(payload, activity_id) \
                    and payload.get('type') == activity_type:
                return payload
        if time.time() >= deadline:
            return None
        time.sleep(interval)


def summary(payload):
    """Return one line describing a notification, for a run's output."""
    return '{0} {1} -> {2} about {3!r} ({4})'.format(
        payload.get('id'),
        '+'.join(payload.get('type') or []),
        (payload.get('target') or {}).get('id'),
        (payload.get('object') or {}).get('name'),
        (payload.get('object') or {}).get('id'))
