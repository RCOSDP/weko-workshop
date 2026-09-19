"""Optional suite: an ARK is minted for the item and becomes its permalink.

Not part of the base flow, because minting an ARK means calling an ARK
server and most instances have none.  Ask for it by name::

    WEKO_E2E_SUITES=ark python -m pytest
    python -m pytest --suite ark

The instance has to be configured for ARK -- ``WEKO_HANDLE_ALLOW_REGISTER_ARK``
together with the mint URL, the NAAN and the shoulder, and either an API
key or login credentials.  There is no admin screen for it; it is
instance configuration.  For a local docker environment, ``e2ectl
ark-stub enable`` writes those settings and runs a stand-in ARK server
inside the ``web`` container, which is enough to exercise the whole path.

Set ``WEKO_E2E_ARK_NAAN`` to assert the ARK was minted under the NAAN
this environment is configured for; without it, any ARK counts.

WEKO mints the ARK when the Item Registration action completes, not at
approval, so this suite registers an item, grants no DOI, approves, and
then asks what identifier the item ended up with.
"""

import pytest

from weko_e2e import flow, ui

pytestmark = pytest.mark.suite('ark')

ARK_PREFIX = 'ark:/'
"""What a minted ARK starts with, whatever server minted it."""


def test_01_login(page, settings):
    """Log in to the instance as a system administrator.

    No screenshot: the login screen is the same one the base suite has
    already captured.
    """
    ui.login(page, settings)


def test_02_set_up(client, settings, record, flow_state):
    """Create the index, the flow and the workflow this run registers with."""
    flow_state['index_id'] = flow.set_up_index(client, settings, record)
    item_type_id, _, _ = flow.set_up_workflow(client, settings, record)
    flow_state['item_type_id'] = item_type_id


def test_03_register_item(page, settings, record, flow_state, shot):
    """Register an item, granting no DOI, and approve it.

    The ARK is minted on the way through -- when Item Registration
    completes -- so nothing here asks for one.
    """
    flow_state['activity_id'] = flow.start_activity(page, settings, record)
    flow.upload_sample_file(page, settings)
    flow.fill_required_metadata(page, settings, flow_state['item_type_id'])
    flow.leave_metadata_screen(page, settings)

    flow.designate_index(page, settings)
    flow.leave_item_link(page, settings)
    flow.choose_identifier_grant(page, settings, value='0')

    shot(page, 'ark-02-approval')
    flow_state['recid'] = flow.approve(page)
    record('item', flow_state['recid'], settings.item_title)
    shot(page, 'ark-03-approved')


def test_04_ark_was_minted(client, settings, flow_state):
    """The item carries an ARK.

    The permalink of an item with no DOI and no CNRI is its ARK, so the
    record page is where a minted ARK shows up.
    """
    recid = flow_state['recid']
    exists, response = client.record_exists(recid)
    assert exists, '/records/{0} answered {1}'.format(
        recid, response.status_code)

    assert ARK_PREFIX in response.text, (
        'no ARK on /records/{0}. WEKO mints one only when the instance is '
        'configured for it: WEKO_HANDLE_ALLOW_REGISTER_ARK with the mint '
        'URL, NAAN and shoulder. For a local docker environment, run '
        '"e2ectl ark-stub enable".'.format(recid))

    ark = _ark_in(response.text)
    flow_state['ark'] = ark
    print('minted ARK: {0}'.format(ark))

    if settings.ark_naan:
        expected = '{0}{1}/'.format(ARK_PREFIX, settings.ark_naan)
        assert ark.startswith(expected), \
            'the ARK {0!r} is not under the NAAN {1!r} this environment ' \
            'is configured for'.format(ark, settings.ark_naan)


def test_05_ark_is_the_permalink(page, settings, flow_state, shot):
    """The item's permalink, on its own page, is that ARK."""
    recid = flow_state['recid']
    page.goto(settings.url('/records/{0}'.format(recid)))
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    shot(page, 'ark-04-record-page')

    permalink = page.locator("text=/{0}/".format(ARK_PREFIX)).locator(
        'visible=true')
    assert permalink.count(), \
        'the record page does not show the ARK where a visitor can see it'
    assert flow_state['ark'] in page.content(), \
        'the record page shows a different ARK than the one that was minted'


def test_06_ark_is_published(client, settings, visitor, flow_state):
    """A visitor who has not logged in sees the item, and its ARK."""
    recid = flow_state['recid']
    exists, response = client.record_exists(recid, session=visitor)
    assert exists, \
        'a visitor gets {0} for /records/{1}'.format(
            response.status_code, recid)
    assert flow_state['ark'] in response.text, \
        'the ARK is not shown to a visitor'


def _ark_in(text):
    """Return the first ARK in a page, without its surrounding markup."""
    import re

    match = re.search(r'ark:/[0-9A-Za-z]+/[0-9A-Za-z.\-_]+', text)
    assert match, 'no ARK found'
    return match.group(0)
