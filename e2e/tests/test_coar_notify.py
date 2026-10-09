"""Optional suite: the workflow is announced over COAR Notify.

Not part of the base flow, because it needs an LDN inbox for WEKO to send
to and a second account for WEKO to send about.  Ask for it by name::

    WEKO_E2E_SUITES=coarnotify python -m pytest
    python -m pytest --suite coarnotify

A stack from ``install.sh`` has both: the ``inbox`` service is the LDN
inbox, ``WEKO_NOTIFICATIONS`` is on in ``scripts/instance.cfg``, and
``repoadmin@example.org`` is the repository administrator every approval
request goes to.  Nothing has to be configured; where the account is a
different one, set ``WEKO_E2E_APPROVER_EMAIL`` and
``WEKO_E2E_APPROVER_PASSWORD``.

The suite walks the loop the feature exists for, with the two accounts on
the two ends of it:

    the registrant sends the item for approval
        -> the approver is sent Offer + EndorsementAction
    the approver approves it
        -> the registrant is sent Announce + EndorsementAction

Both are read back the way a user reads them, through
``GET /api/notifications``, and then fetched from the inbox and checked
field by field.  **Who receives what is the point**: WEKO leaves the
person who acted out of the notification about their own action, so a run
in which one account did everything would prove nothing -- which is why
the approver here is somebody else.
"""

import json
import os
import re
import time
import uuid

import pytest

from weko_e2e import flow, notify, ui
from weko_e2e.cli import (push_received, push_stub,  # noqa: I100
                          push_subscribe, push_unsubscribe)
from weko_e2e.client import WekoClient, WekoError

pytestmark = pytest.mark.suite('coarnotify')

VAPID_KEY_PATH = '/inbox/subscription/vapid-public-key'
"""Where a browser asks for the key it has to subscribe with."""

SERVICE_WORKER_PATH = '/static/gen/sw.js'
"""The script that receives a Web Push and shows it."""

PUSH_TEMPLATES = os.path.join(
    'modules', 'weko-notifications', 'weko_notifications', 'templates',
    'weko_notifications', 'push.json')
"""The message texts WEKO registers with the inbox, in the checkout.

The inbox renders a push from these, so they are what a delivered push
has to say; reading them is how this suite knows the text it should see
without writing that text down a second time.
"""


@pytest.fixture(scope='module', autouse=True)
def inbox_is_there(settings, visitor):
    """Skip the suite where the announced inbox is not serving anything.

    WEKO announces an inbox whether or not one is deployed -- the
    ``Link:`` header is built from configuration -- so the announcement
    passing says nothing about whether a sender could reach it.  Where
    nothing is there, every step after the second fails on a 500 from
    WEKO, which is a true answer to the wrong question.
    """
    if not notify.inbox_answers(visitor, settings):
        pytest.skip(
            'nothing is serving {0} on this instance, so there is no LDN '
            'inbox for WEKO to send to or read from. A stack from '
            'install.sh has one; on a cluster it is a service to deploy '
            '-- see deploy/coar-notify-inbox in the repository this came '
            'from'.format(notify.PROBE_PATH.rsplit('/', 1)[0]))


@pytest.fixture(scope='module')
def approver_settings(settings):
    """Return the settings, with the approver's credentials."""
    return settings.as_account(settings.approver_email,
                               settings.approver_password)


@pytest.fixture(scope='module')
def approver(approver_settings):
    """Return a logged in HTTP client for the account that approves.

    :raise AssertionError: when that account cannot log in, which is what
        an instance whose approver is somebody else looks like
    """
    try:
        return WekoClient(approver_settings).login()
    except WekoError as error:
        raise AssertionError(
            '{0}. The approver is the account the approval request is sent '
            'to; set WEKO_E2E_APPROVER_EMAIL and '
            'WEKO_E2E_APPROVER_PASSWORD to one this instance has.'.format(
                error))


@pytest.fixture(scope='module')
def approver_page(browser, approver_settings):
    """Return a browser page logged in as the approver.

    Its own browsing context: the run's own page is logged in as the
    registrant and the approval has to be somebody else's doing.
    """
    page = ui.new_page(browser, approver_settings)
    ui.login(page, approver_settings)
    yield page
    page.context.close()


# -- what the instance publishes -------------------------------------------

def test_01_login(page, settings):
    """Log in to the instance as the registrant."""
    ui.login(page, settings)


def test_02_the_instance_announces_its_inbox(client, settings, flow_state):
    """The site announces where its LDN inbox is.

    This is COAR Notify discovery: a sender asks the target for its
    ``ldp#inbox`` link.  WEKO puts it on a HEAD of the top page and not
    on a GET, so that is what is asked for here.
    """
    inbox = notify.announced_inbox(client.session, settings)
    assert inbox, (
        'the site top page carries no {0!r} link, so nothing can discover '
        'this instance\'s inbox. WEKO adds it when WEKO_NOTIFICATIONS is '
        'on; check scripts/instance.cfg.'.format(notify.LINK_REL))
    assert inbox.rstrip('/').endswith('/inbox'), \
        'the announced inbox {0!r} is not an inbox endpoint'.format(inbox)
    flow_state['inbox'] = inbox
    print('announced inbox: {0}'.format(inbox))


def test_03_notifications_are_not_public(visitor, settings):
    """A visitor who has not logged in is told nothing.

    Notifications are addressed to a person, so the API answers 401
    rather than handing out somebody's.
    """
    response = visitor.get(settings.url(notify.API_PATH), timeout=60)
    assert response.status_code == 401, \
        'a visitor gets {0} from {1}, not the 401 a private list owes ' \
        'them'.format(response.status_code, notify.API_PATH)


def test_04_the_approver_can_read_their_notifications(approver, settings):
    """The account that will be notified can read its own notifications."""
    before = notify.notifications(approver.session, settings)
    print('the approver ({0}) holds {1} notification(s) already'.format(
        settings.approver_email, len(before)))


# -- the flow --------------------------------------------------------------

def test_05_set_up(client, settings, record, flow_state):
    """Create the index, the flow and the workflow this run registers with."""
    flow_state['index_id'] = flow.set_up_index(client, settings, record)
    item_type_id, _, _ = flow.set_up_workflow(client, settings, record)
    flow_state['item_type_id'] = item_type_id


def test_06_send_the_item_for_approval(page, client, approver, settings,
                                       record, flow_state, shot):
    """Register an item and walk it up to the approval step.

    Moving on from the identifier grant is what puts the activity on the
    approval action, and that is where WEKO offers it to the approvers --
    so the inbox is looked at as it is beforehand, first.
    """
    flow_state['approver_knew'] = set(
        notify.notifications(approver.session, settings))
    flow_state['registrant_knew'] = set(
        notify.notifications(client.session, settings))

    flow_state['activity_id'] = flow.start_activity(page, settings, record)
    flow.upload_sample_file(page, settings)
    flow.fill_required_metadata(page, settings, flow_state['item_type_id'])
    flow.leave_metadata_screen(page, settings)

    flow.designate_index(page, settings)
    flow.leave_item_link(page, settings)
    flow.choose_identifier_grant(page, settings, value='0')

    assert ui.current_step(page) == ui.APPROVAL
    shot(page, '01-awaiting-approval')


def test_07_the_approver_is_offered_the_item(approver, settings, flow_state):
    """The approver is sent an Offer + EndorsementAction about the item.

    That is the COAR Notify pattern for "please endorse this": the
    request for approval the registrant has just made.
    """
    offer = notify.wait_for(
        approver.session, settings, flow_state['activity_id'],
        notify.OFFER_ENDORSE, timeout=settings.notify_timeout,
        seen=flow_state['approver_knew'])
    assert offer, (
        'nothing was offered to {0} about {1} within {2} s. WEKO sends it '
        'when the activity reaches the approval action; check that the '
        'inbox service is up, that WEKO_NOTIFICATIONS is on, and that this '
        'account is the one the approval requests go to.'.format(
            settings.approver_email, flow_state['activity_id'],
            settings.notify_timeout))
    print('offered: {0}'.format(notify.summary(offer)))
    flow_state['offer'] = offer

    _check_shape(offer, settings)
    assert notify.USER_URI.search(offer['target']['id'] or ''), \
        'the offer is addressed to {0!r}, which is not a person'.format(
            offer['target']['id'])
    assert offer['target']['type'] == 'Person', \
        'the offer is addressed to a {0!r}, not a Person'.format(
            offer['target']['type'])


# -- web push, when this environment can deliver one -----------------------

def test_08_the_instance_can_send_a_web_push(client, settings, flow_state):
    """A Web Push can be signed here, and something is listening for one.

    Skipped unless this environment has the stand-in browser running.  A
    real subscription comes from Google's or Mozilla's push service,
    which a run against a local stack cannot reach; and the inbox signs
    nothing without a VAPID key, which the shipped compose file leaves
    empty.  ``e2ectl webpush-stub enable`` is what puts both in place.
    """
    if not settings.can_exec:
        pytest.skip(
            'the web push stand-in runs in the inbox container, and '
            'nothing here can run a command in it: set WEKO_E2E_REPO to '
            'the WEKO checkout, or WEKO_E2E_EXEC to a command that '
            'reaches the containers')
    subscription = push_stub(settings, '/subscription')
    if not subscription:
        pytest.skip(
            'no web push stand-in is running; "e2ectl webpush-stub enable" '
            'generates a VAPID key pair for the inbox and runs a browser '
            'of its own for it to send to')
    flow_state['push_stub'] = subscription
    print('stand-in subscription: {0}'.format(subscription['endpoint']))

    response = client.session.get(settings.url(VAPID_KEY_PATH), timeout=60)
    assert response.status_code == 200, \
        'the inbox answered {0} for {1}'.format(
            response.status_code, VAPID_KEY_PATH)
    key = response.text.strip()
    assert key, (
        'the inbox publishes no VAPID public key, so no browser can '
        'subscribe and nothing it was sent could be signed')
    print('VAPID public key: {0}...'.format(key[:16]))


def test_09_the_registrant_subscribes_to_web_push(settings, flow_state):
    """The registrant's browser subscribes, as the settings screen does.

    WEKO registers a subscription and the user's profile together -- the
    profile is what the inbox picks the language of the message by -- so
    the stand-in registers both.
    """
    _require_web_push(flow_state)
    # The offer names the registrant as the one who asked for approval.
    target = flow_state['offer']['actor']['id']
    answer = push_subscribe(settings, target)
    assert answer, 'the web push stand-in stopped answering'
    assert answer.get('subscribe') in (200, 201), \
        'the inbox refused the subscription: {0}'.format(answer)
    assert answer.get('userprofile') in (200, 201), \
        'the inbox refused the user profile: {0}'.format(answer)
    flow_state['push_target'] = target
    flow_state['pushed_before'] = len(push_received(settings))
    print('subscribed for {0}'.format(target))


def test_10_the_approver_approves(page, approver, approver_page, settings,
                                  record, flow_state, shot):
    """The approver, not the registrant, approves the item.

    WEKO leaves the person who acted out of the notification about their
    own action, so the announcement that follows only has somebody to go
    to because the approval is somebody else's.
    """
    activity_id = flow_state['activity_id']
    # The registrant moves off the activity screen first: WEKO holds the
    # activity for the window that has it open, and lets go on unload.
    ui.leave_activity(page, settings)
    # And the approver lets go of anything an earlier run left them
    # holding, which WEKO would otherwise refuse to open this one over.
    approver.release_user_lock(activity_id)

    approver_page.goto(
        settings.url('/workflow/activity/detail/{0}'.format(activity_id)))
    approver_page.wait_for_load_state('networkidle')
    approver_page.wait_for_timeout(3000)
    ui.force_unlock(approver_page)

    assert ui.current_step(approver_page) == ui.APPROVAL, (
        'the approver ({0}) is not being shown the approval screen of {1}, '
        'but "{2}"'.format(settings.approver_email, activity_id,
                           ui.current_step(approver_page)))
    shot(approver_page, '02-approver-screen')

    flow_state['recid'] = flow.approve(approver_page)
    record('item', flow_state['recid'], settings.item_title)
    shot(approver_page, '03-approved')


def test_11_the_registrant_is_told_it_was_approved(client, settings,
                                                   flow_state):
    """The registrant is sent an Announce + EndorsementAction.

    The other half of the loop: the endorsement that was offered has
    happened, and the person who asked for it is told so.
    """
    announcement = notify.wait_for(
        client.session, settings, flow_state['activity_id'],
        notify.ANNOUNCE_ENDORSE, timeout=settings.notify_timeout,
        seen=flow_state['registrant_knew'])
    assert announcement, (
        'nothing was announced to {0} about {1} within {2} s, although the '
        'item was approved.'.format(
            settings.email, flow_state['activity_id'],
            settings.notify_timeout))
    print('announced: {0}'.format(notify.summary(announcement)))
    flow_state['announcement'] = announcement

    _check_shape(announcement, settings)
    assert announcement['object']['id'].rstrip('/').endswith(
        '/records/{0}'.format(flow_state['recid'])), \
        'the announcement points at {0!r}, not at the record {1} the ' \
        'activity registered'.format(announcement['object']['id'],
                                     flow_state['recid'])
    # The person the item was offered to is the person who endorsed it.
    endorser = flow_state['offer']['target']['id']
    assert announcement['actor']['id'] == endorser, \
        'the announcement names {0!r} as the actor, but the offer went to ' \
        '{1!r}'.format(announcement['actor']['id'], endorser)
    assert announcement['target']['id'] != announcement['actor']['id'], \
        'the announcement was sent to the person who made it'


def test_12_the_approval_arrives_as_a_web_push(settings, flow_state):
    """The announcement reaches the browser as a Web Push, in words.

    The payload is encrypted for the subscription's own keys, so what the
    stand-in decrypts is what the user's browser would have been shown --
    and it has to be what ``push.json`` says, rendered with this item and
    this approver.
    """
    _require_web_push(flow_state)
    notification = flow_state['announcement']
    push = _wait_for_push(settings, notification['id'],
                          settings.notify_timeout)
    assert push, (
        'the inbox sent no web push for {0} within {1} s, although the '
        'announcement reached it. Check the inbox log: it sends in a '
        'background task and only writes the failure down.'.format(
            notification['id'], settings.notify_timeout))
    print('web push: {0}'.format(json.dumps(push, ensure_ascii=False)))

    title, body = _rendered_template(settings, notify.ANNOUNCE_ENDORSE,
                                     notification)
    assert push['title'] == title, \
        'the push says {0!r}, not the {1!r} push.json asks for'.format(
            push['title'], title)
    assert push['options']['body'] == body, \
        'the push body is {0!r}, not the {1!r} push.json asks for'.format(
            push['options']['body'], body)
    assert push['options']['data']['url'] == notification['context']['id'], \
        'clicking the push would open {0!r}, not the activity it is ' \
        'about'.format(push['options']['data']['url'])


def test_13_unsubscribing_stops_the_pushes(client, settings, flow_state):
    """Once the browser unsubscribes, the inbox sends it nothing more.

    The run has only one approval to give, so the second notification is
    offered to the inbox the way any sender offers one -- a POST to the
    inbox itself -- and it is the same notification but for its id, so
    the only thing that has changed is the subscription.
    """
    _require_web_push(flow_state)
    answer = push_unsubscribe(settings)
    assert answer and answer.get('unsubscribe') == 200, \
        'the inbox did not take the subscription away: {0}'.format(answer)

    before = len(push_received(settings))
    again = dict(flow_state['announcement'])
    again['id'] = 'urn:uuid:{0}'.format(uuid.uuid4())
    response = client.session.post(
        settings.url('/inbox'), data=json.dumps(again), timeout=60,
        headers={'Content-Type': 'application/ld+json'})
    assert response.status_code == 201, \
        'the inbox answered {0} for a notification it should take: ' \
        '{1}'.format(response.status_code, response.text[:200])

    deadline = time.time() + 15
    while time.time() < deadline:
        time.sleep(3)
        assert len(push_received(settings)) == before, (
            'the inbox pushed to a subscription that had unsubscribed')
    print('nothing was pushed after unsubscribing, as it should not be')


def test_14_the_user_can_choose_how_to_be_notified(page, settings, shot):
    """The registrant has a screen for saying how they want to be told."""
    page.goto(settings.url('/account/settings/notifications/'))
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1500)
    shot(page, '04-settings')

    for name in ('notifications-subscribe_webpush',
                 'notifications-subscribe_email'):
        assert page.locator("input[name='{0}']".format(name)).count(), \
            'the notification settings screen offers no {0!r}'.format(name)

    # Turning Web push on is what registers the service worker, so the
    # screen is only an offer while that script is served.
    worker = page.request.get(settings.url(SERVICE_WORKER_PATH))
    assert worker.ok, \
        'the service worker {0} answers {1}, so a browser could not ' \
        'receive a web push'.format(SERVICE_WORKER_PATH, worker.status)


def _require_web_push(flow_state):
    """Skip when this environment cannot deliver a Web Push."""
    if not flow_state.get('push_stub'):
        pytest.skip('this environment sends no web push; see the step that '
                    'looks for the stand-in')


def _wait_for_push(settings, notification_id, timeout, interval=3):
    """Wait for the push the inbox sends about one notification.

    The inbox pushes in a background task, after it has answered the
    sender, so the push follows the notification rather than arriving
    with it.  Each push carries the notification's id as its tag, which
    is what tells this run's apart from anything else in the stand-in.

    :return: the push payload, or None when none arrived in time
    """
    deadline = time.time() + timeout
    while True:
        for entry in push_received(settings):
            payload = entry.get('payload') or {}
            if payload.get('options', {}).get('tag') == notification_id:
                return payload
        if time.time() >= deadline:
            return None
        time.sleep(interval)


def _rendered_template(settings, activity_type, notification, language='en'):
    """Return the title and body ``push.json`` asks for, filled in.

    The inbox picks the template by the notification's ``type`` and
    renders ``{{ object_name }}`` and ``{{ actor_name }}`` into it; this
    does the same, so the step compares what arrived with what the
    instance's own message file says rather than with a copy of the text.

    The templates are read out of the checkout, which is the one thing
    here that wants the checkout's *files* rather than a way into the
    containers -- so where there is none this skips rather than fails.

    :raise AssertionError: when the file has no template for that type
    """
    if not settings.weko_repo:
        pytest.skip(
            'the message texts are read from {0} in the WEKO checkout, so '
            'that this step compares the push with the instance\'s own '
            'words rather than with a copy of them; set '
            'WEKO_E2E_REPO'.format(PUSH_TEMPLATES))
    path = os.path.join(settings.weko_repo, PUSH_TEMPLATES)
    assert os.path.isfile(path), \
        'the message templates are not at {0}; this is where WEKO reads ' \
        'them from before registering them with the inbox'.format(path)
    with open(path, encoding='utf-8') as handle:
        templates = json.load(handle)

    for entry in templates.values():
        if entry.get('type') != activity_type:
            continue
        text = entry.get('templates', {}).get(language)
        assert text, 'push.json has no {0!r} text for {1}'.format(
            language, activity_type)
        values = {
            'object_name': notification['object']['name'],
            'actor_name': notification['actor']['name'],
        }
        return (_render(text['title'], values), _render(text['body'], values))
    raise AssertionError(
        'push.json has no template for {0}, so the inbox had nothing to '
        'render'.format(activity_type))


def _render(text, values):
    """Fill ``{{ name }}`` in, the way the inbox does."""
    return re.sub(r'\{\{\s*(\w+)\s*\}\}',
                  lambda match: str(values.get(match.group(1), '')), text)


def _check_shape(payload, settings):
    """Check what every notification WEKO sends has to carry."""
    assert str(payload.get('id', '')).startswith('urn:uuid:'), \
        'the notification id {0!r} is not a urn:uuid:'.format(
            payload.get('id'))
    assert payload.get('@context') == notify.CONTEXT, \
        'the notification carries the context {0!r}, not COAR Notify\'s ' \
        '{1!r}'.format(payload.get('@context'), notify.CONTEXT)
    assert payload['origin']['type'] == 'Service', \
        'the notification comes from a {0!r}, not a Service'.format(
            payload['origin']['type'])
    assert payload['origin']['inbox'].rstrip('/').endswith('/inbox'), \
        'the notification names {0!r} as the sender\'s inbox'.format(
            payload['origin']['inbox'])
    assert payload['object']['name'] == settings.item_title, \
        'the notification is about {0!r}, not about the item this run ' \
        'registered ({1!r})'.format(payload['object']['name'],
                                    settings.item_title)
    assert payload['object']['type'] == ['Page', 'sorg:WebPage'], \
        'the notification calls the item a {0!r}'.format(
            payload['object']['type'])
