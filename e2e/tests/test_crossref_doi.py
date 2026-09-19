"""Optional suite: a Crossref DOI is granted to the item.

Not part of the base flow, because it needs a Crossref prefix and it
changes an instance-wide setting while it runs.  Ask for it by name::

    WEKO_E2E_SUITES=crossref python -m pytest
    python -m pytest --suite crossref

The suite turns the Crossref grant on under ``/admin/identifier/``, sets
the prefix to ``WEKO_E2E_CROSSREF_PREFIX`` -- Crossref's own documented
example prefix ``10.5555`` by default -- registers an item asking for that
grant, and checks the DOI the item ends up with. The identifier settings
are put back the way they were afterwards, whether the run passed or not.

Depositing to Crossref is a step further, and off unless asked for. WEKO
grants the DOI locally first and deposits afterwards through the worker;
with ``WEKO_E2E_CROSSREF_DEPOSIT`` set, this suite waits for that deposit
and reports what Crossref said. It needs an account, which
``e2ectl crossref-account enable`` writes into the instance
configuration, and it deposits to Crossref's test system -- the URL WEKO
already defaults to. The prefix then has to be one that account is
allowed to register under, so set ``WEKO_E2E_CROSSREF_PREFIX`` to it.

Crossref will not take a journal article without the journal, its ISSN
and the date it was issued, and WEKO refuses the grant rather than
building a deposit Crossref would reject -- so this suite fills those in
where the base flow does not.
"""

import re
import time

import pytest

from weko_e2e import flow, ui
from weko_e2e.cli import deposit_log

pytestmark = pytest.mark.suite('crossref')

CROSSREF_GRANT = '2'
"""Radio value of the Crossref DOI grant on the identifier grant screen."""


@pytest.fixture(scope='module', autouse=True)
def identifier_settings(page, settings, client):
    """Turn the Crossref grant on, and put the settings back afterwards.

    The identifier settings are one row for the whole instance, so this
    remembers what was there and restores it; a run that changed a
    working repository's prefix and left it changed would be worse than a
    run that failed.
    """
    ui.login(page, settings)
    _open_identifier_form(page, settings)
    before = {
        'enabled': page.locator('#jalc_crossref_flag').is_checked(),
        'prefix': page.locator('#jalc_crossref_doi').input_value(),
    }
    print('identifier settings before: {0}'.format(before))

    _enable_crossref(page, settings.crossref_prefix)
    yield before

    _open_identifier_form(page, settings)
    # The prefix box is only writable while the grant is enabled, which it
    # still is at this point, so put the prefix back before turning the
    # grant off again.
    page.fill('#jalc_crossref_doi', before['prefix'])
    if not before['enabled']:
        _disable_crossref(page)
    _save_identifier_form(page)

    _open_identifier_form(page, settings)
    after = {
        'enabled': page.locator('#jalc_crossref_flag').is_checked(),
        'prefix': page.locator('#jalc_crossref_doi').input_value(),
    }
    print('identifier settings restored to: {0}'.format(after))
    assert after == before, \
        'the identifier settings were left as {0}, not the {1} they ' \
        'were before this run'.format(after, before)


def _open_identifier_form(page, settings):
    """Open the identifier settings of the first repository."""
    page.goto(settings.url('/admin/identifier/'))
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1000)
    edit = page.locator("a[href*='/admin/identifier/edit/']")
    assert edit.count(), 'this instance has no identifier settings row'
    edit.first.click()
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1000)


def _enable_crossref(page, prefix):
    """Move the Crossref grant to Enable and set its prefix.

    The prefix box stays read only until the grant is enabled, and the
    grant is enabled by moving it from Disable to Enable in the dual list.
    """
    if not page.locator('#jalc_crossref_flag').is_checked():
        page.locator('#leftSelect').select_option('jalc_crossref_doi')
        page.locator('#moveRight').click()
        page.wait_for_timeout(500)
    page.fill('#jalc_crossref_doi', prefix)
    _save_identifier_form(page)


def _disable_crossref(page):
    """Move the Crossref grant back to Disable."""
    if page.locator('#jalc_crossref_flag').is_checked():
        page.locator('#rightSelect').select_option('jalc_crossref_doi')
        page.locator('#moveLeft').click()
        page.wait_for_timeout(500)


def _save_identifier_form(page):
    """Save the identifier settings form."""
    page.locator("input[type=submit][value='Save']").locator(
        'visible=true').first.click()
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1500)


# -- the flow --------------------------------------------------------------

def test_01_prefix_is_set(page, settings, shot):
    """The Crossref prefix this run asked for is what the list shows."""
    page.goto(settings.url('/admin/identifier/'))
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1000)
    shot(page, '01-identifier-settings')

    row = page.locator('table tbody tr').first.inner_text()
    assert settings.crossref_prefix in row, \
        'the Crossref prefix is {0!r}, not the {1!r} this run set'.format(
            row, settings.crossref_prefix)


def test_02_set_up(client, settings, record, flow_state):
    """Create the index, the flow and the workflow this run registers with."""
    flow_state['index_id'] = flow.set_up_index(client, settings, record)
    item_type_id, _, _ = flow.set_up_workflow(client, settings, record)
    flow_state['item_type_id'] = item_type_id


def test_03_register_item(page, settings, record, flow_state, shot):
    """Register an item with the metadata a Crossref deposit requires."""
    flow_state['activity_id'] = flow.start_activity(page, settings, record)
    item_type_id = flow_state['item_type_id']

    flow.upload_sample_file(page, settings)
    flow.fill_required_metadata(page, settings, item_type_id)
    flow.fill_journal_metadata(page, item_type_id)
    shot(page, '02-item-metadata')

    flow.leave_metadata_screen(page, settings)
    flow.designate_index(page, settings)
    flow.leave_item_link(page, settings)


def test_04_choose_crossref_grant(page, settings, shot):
    """The Crossref DOI grant is offered, and the activity takes it."""
    assert ui.current_step(page) == ui.IDENTIFIER_GRANT
    body = page.locator('body').inner_text()
    assert settings.crossref_prefix in body, \
        'the identifier grant screen does not offer the prefix {0!r}'.format(
            settings.crossref_prefix)

    flow.choose_identifier_grant(page, settings, value=CROSSREF_GRANT)
    shot(page, '03-grant-chosen')


def test_05_approve(page, settings, record, flow_state, shot):
    """Approve, which is where WEKO grants the DOI."""
    shot(page, '04-approval')
    flow_state['recid'] = flow.approve(page)
    record('item', flow_state['recid'], settings.item_title)
    shot(page, '05-approved')


def test_06_doi_was_granted(client, settings, flow_state):
    """The item carries a DOI under the prefix this run configured."""
    recid = flow_state['recid']
    exists, response = client.record_exists(recid)
    assert exists, '/records/{0} answered {1}'.format(
        recid, response.status_code)

    match = re.search(
        re.escape(settings.crossref_prefix) + r'/[0-9A-Za-z.\-_/]+',
        response.text)
    assert match, (
        'no DOI under {0} on /records/{1}; the grant was chosen but no '
        'DOI was assigned'.format(settings.crossref_prefix, recid))
    flow_state['doi'] = match.group(0)
    print('granted DOI: {0}'.format(flow_state['doi']))


def test_07_doi_is_the_permalink(page, settings, flow_state, shot):
    """The DOI is what the item offers as its permalink."""
    page.goto(settings.url('/records/{0}'.format(flow_state['recid'])))
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    shot(page, '06-record-page')

    assert flow_state['doi'] in page.content(), \
        'the record page does not show the DOI that was granted'


def test_08_doi_is_published(client, settings, visitor, flow_state):
    """A visitor who has not logged in sees the item, and its DOI."""
    recid = flow_state['recid']
    exists, response = client.record_exists(recid, session=visitor)
    assert exists, \
        'a visitor gets {0} for /records/{1}'.format(
            response.status_code, recid)
    assert flow_state['doi'] in response.text, \
        'the DOI is not shown to a visitor'


# -- the deposit, when this environment has an account ---------------------

def test_09_deposit_was_recorded(settings, flow_state):
    """WEKO wrote a deposit for that DOI, and knows where it stands.

    Skipped unless this environment was given a Crossref account: without
    one WEKO grants the DOI and deposits nothing, which is the documented
    behaviour and not a failure.
    """
    _require_deposit(settings)
    doi = flow_state['doi']

    deadline = time.time() + 60
    rows = []
    while time.time() < deadline:
        rows = deposit_log(settings, doi)
        if rows:
            break
        time.sleep(5)
    assert rows, (
        'WEKO recorded no deposit for {0}. The grant went through, so the '
        'deposit itself was not started: check that '
        'WEKO_CROSSREF_ALLOW_REGISTER_DOI is on in the instance '
        'configuration ("e2ectl crossref-account status") and that the '
        'worker is running.'.format(doi))
    flow_state['deposit'] = rows[0]
    print('deposit: {0}'.format(rows[0]))


def test_10_deposit_reached_crossref(settings, flow_state):
    """Crossref accepted the deposit.

    The worker sends the deposit and then polls Crossref for the outcome,
    so this waits for the log to settle on success or failure. A failure
    carries what Crossref said, which is the whole point of sending it.
    """
    _require_deposit(settings)
    doi = flow_state['doi']

    deadline = time.time() + settings.crossref_deposit_timeout
    row = flow_state.get('deposit') or {}
    while time.time() < deadline:
        rows = deposit_log(settings, doi)
        row = rows[0] if rows else row
        if row.get('status') in ('success', 'failure'):
            break
        time.sleep(10)

    print('deposit: {0}'.format(row))
    assert row.get('status') != 'failure', (
        'Crossref refused the deposit of {0}: {1} (HTTP {2})'.format(
            doi, row.get('error') or 'no reason given', row.get('http')))
    assert row.get('status') == 'success', (
        'the deposit of {0} is still {1!r} after {2} s; Crossref had not '
        'answered yet. Raise WEKO_E2E_CROSSREF_DEPOSIT_TIMEOUT, or look at '
        '"e2ectl doi-log".'.format(
            doi, row.get('status'), settings.crossref_deposit_timeout))


def _require_deposit(settings):
    """Skip when this environment was not asked to deposit."""
    if not settings.crossref_deposit:
        pytest.skip(
            'depositing is off; set WEKO_E2E_CROSSREF_DEPOSIT=1 and give '
            'the instance an account with "e2ectl crossref-account enable"')
    if not settings.weko_repo:
        pytest.skip(
            'the deposit log is read from inside the web container; '
            'set WEKO_E2E_REPO to the WEKO checkout')
