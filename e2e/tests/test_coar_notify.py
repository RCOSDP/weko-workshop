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

import pytest

from weko_e2e import flow, notify, ui
from weko_e2e.client import WekoClient, WekoError

pytestmark = pytest.mark.suite('coarnotify')


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
    shot(page, 'coarnotify-01-awaiting-approval')


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


def test_08_the_approver_approves(page, approver, approver_page, settings,
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
    shot(approver_page, 'coarnotify-02-approver-screen')

    flow_state['recid'] = flow.approve(approver_page)
    record('item', flow_state['recid'], settings.item_title)
    shot(approver_page, 'coarnotify-03-approved')


def test_09_the_registrant_is_told_it_was_approved(client, settings,
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


def test_10_the_user_can_choose_how_to_be_notified(page, settings, shot):
    """The registrant has a screen for saying how they want to be told."""
    page.goto(settings.url('/account/settings/notifications/'))
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1500)
    shot(page, 'coarnotify-04-settings')

    for name in ('notifications-subscribe_webpush',
                 'notifications-subscribe_email'):
        assert page.locator("input[name='{0}']".format(name)).count(), \
            'the notification settings screen offers no {0!r}'.format(name)


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
