"""The base flow: set up an index and a workflow, register an item, publish.

This is the run a working installation has to survive.  It creates
everything it needs -- an index of its own, a flow of its own and a
workflow of its own on the default full item type -- so it does not depend
on what a previous run, or a demo data load, left behind, and so that
everything it touches can be deleted again afterwards.

The steps are one flow cut into tests, so they share a browser and run in
the order they are written; each records what it created in the ledger as
soon as WEKO has created it, so a run that fails half way is still
cleanable with ``./e2ectl clean``.

The flow itself lives in :mod:`weko_e2e.flow`, which the optional suites
walk as well; what is here is the base suite's own business -- no
identifier, and the item public at the end.
"""

import time

import pytest

from weko_e2e import flow, ui
from weko_e2e.client import DEFAULT_FLOW_ACTIONS


# -- setup: the index and the workflow the run registers its item with -----

def test_01_login(page, settings, shot):
    """Log in to the instance as a system administrator."""
    ui.login(page, settings)
    shot(page, '01-logged-in')


def test_02_create_index(client, settings, record, flow_state, page, shot):
    """Create the index the item is registered in, and publish it.

    An item is only visible to a visitor when at least one index it is in
    is public, so the index is published here rather than left private as
    a newly created index is.
    """
    index_id = flow.set_up_index(client, settings, record, public=True)
    flow_state['index_id'] = index_id

    assert client.find_index(settings.index_name) == index_id, \
        'the new index is not in the index tree'
    assert settings.index_name in client.workflow_form_options()['index'], \
        'the new index is not offered to a workflow'

    page.goto(settings.url('/admin/indexedit/'))
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    shot(page, '02-index-created')


def test_03_define_flow(client, settings, record, flow_state, page, shot):
    """Define the flow the workflow runs.

    The same six actions the shipped ``Registration Flow`` has, so the run
    walks the screens a default installation walks.
    """
    flow_id = client.create_flow(settings.flow_name, DEFAULT_FLOW_ACTIONS)
    record('flow', flow_id, settings.flow_name)
    flow_state['flow_id'] = flow_id

    _, present = client._flow_page(flow_id)
    assert len(present) == len(DEFAULT_FLOW_ACTIONS), \
        'the flow has {0} actions, expected {1}'.format(
            len(present), len(DEFAULT_FLOW_ACTIONS))

    page.goto(settings.url('/admin/flowsetting/{0}'.format(flow_id)))
    page.wait_for_load_state('networkidle')
    shot(page, '03-flow-defined')


def test_04_define_workflow(client, settings, record, flow_state, page,
                            shot):
    """Define the workflow: the default full item type, on the test flow.

    No index is designated on the workflow, as the shipped workflows also
    leave it unset.  A workflow that names an index designates it by
    itself and skips the index designation screen, and that screen is part
    of what the base flow is here to walk.
    """
    item_type_id = client.item_type_id(settings.item_type_name)
    flow_state['item_type_id'] = item_type_id

    workflow_id = client.create_workflow(
        settings.workflow_name,
        item_type_id=item_type_id,
        flow_id=client.flow_numeric_id(settings.flow_name),
        index_id=None)
    record('workflow', workflow_id, settings.workflow_name)
    flow_state['workflow_id'] = workflow_id

    assert settings.workflow_name in client.workflows(), \
        'the new workflow is not in the workflow list'

    page.goto(settings.url('/admin/workflowsetting/{0}'.format(workflow_id)))
    page.wait_for_load_state('networkidle')
    shot(page, '04-workflow-defined')


# -- the flow: register an item and publish it -----------------------------

def test_05_start_activity(page, settings, record, flow_state, shot):
    """Start an activity on the workflow this run defined."""
    page.goto(settings.url('/workflow/activity/new'))
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1500)
    shot(page, '05-workflow-list')

    flow_state['activity_id'] = flow.start_activity(page, settings, record)

    assert ui.current_step(page) == ui.ITEM_REGISTRATION, \
        'the activity opened on {0!r}, not on item registration'.format(
            ui.current_step(page))
    shot(page, '06-activity-started')


def test_06_register_metadata(page, settings, flow_state, shot):
    """Attach a file and fill the metadata the item type requires.

    The default full item type requires the publication date, a title and
    a resource type; a file is not required, but an item without one is not
    what a repository holds, so the run uploads one.
    """
    flow.upload_sample_file(page, settings)
    flow_state['resource_type'] = flow.fill_required_metadata(
        page, settings, flow_state['item_type_id'])

    shot(page, '07-item-metadata')
    flow.leave_metadata_screen(page, settings)


def test_07_designate_index(page, settings, flow_state, shot):
    """Put the item in the index this run created."""
    ui.designate_index(page, settings.index_name)
    shot(page, '08-index-designated')
    ui.advance_to(page, ui.ITEM_LINK, timeout=settings.step_timeout)


def test_08_item_link(page, settings, shot):
    """Link no other item, and move on."""
    assert ui.current_step(page) == ui.ITEM_LINK
    shot(page, '09-item-link')
    flow.leave_item_link(page, settings)


def test_09_identifier_grant(page, settings, shot):
    """Grant no identifier: the base flow registers an item without a DOI.

    A DOI or an ARK is what the optional suites are for; here the point is
    that the screen offers Not Grant and that the activity moves past it.
    """
    shot(page, '10-identifier-grant')
    flow.choose_identifier_grant(page, settings, value='0')


def test_10_approve(page, flow_state, shot):
    """Approve the activity, which is what registers and publishes the item."""
    shot(page, '11-approval')
    flow_state['recid'] = flow.approve(page)
    shot(page, '12-approved')


def test_11_record_is_registered(page, settings, record, flow_state, client,
                                 shot):
    """The item exists, under the title the run gave it."""
    recid = flow_state['recid']
    record('item', recid, settings.item_title)

    exists, response = client.record_exists(recid)
    assert exists, '/records/{0} answered {1}'.format(
        recid, response.status_code)
    assert settings.item_title in response.text, \
        'the record page does not show the title the run registered'

    page.goto(settings.url('/records/{0}'.format(recid)))
    page.wait_for_load_state('networkidle')
    shot(page, '13-record-page')


def test_12_record_is_public(settings, visitor, client, flow_state,
                             visitor_page, shot):
    """A visitor who has not logged in can see the item."""
    recid = flow_state['recid']
    exists, response = client.record_exists(recid, session=visitor)
    assert exists, \
        'a visitor gets {0} for /records/{1}; the item was not published'\
        .format(response.status_code, recid)
    assert settings.item_title in response.text, \
        'the item is reachable but does not show its title to a visitor'

    visitor_page.goto(settings.url('/records/{0}'.format(recid)))
    visitor_page.wait_for_load_state('networkidle')
    shot(visitor_page, '14-record-page-anonymous')


def test_13_record_is_in_index(client, flow_state, visitor_page, settings,
                               shot):
    """Search finds the item in the index the run created.

    Indexing is asynchronous, so this is the one step that waits -- up to
    ``WEKO_E2E_SEARCH_TIMEOUT`` seconds.  It is also the step that shows
    the worker and Elasticsearch are doing their job, which is why it is
    worth waiting for rather than skipping.
    """
    index_id = flow_state['index_id']
    recid = flow_state['recid']
    deadline = time.time() + settings.search_timeout
    found = set()
    while time.time() < deadline:
        found = client.recids_in_index(index_id)
        if recid in found:
            visitor_page.goto(settings.url(
                '/search?search_type=2&q={0}'.format(index_id)))
            visitor_page.wait_for_load_state('networkidle')
            visitor_page.wait_for_timeout(4000)
            shot(visitor_page, '15-search-in-index')
            return
        time.sleep(5)
    pytest.fail('index {0} does not hold record {1} after {2} s; '
                'it holds: {3}'.format(
                    index_id, recid, settings.search_timeout,
                    ', '.join(sorted(found)) or 'nothing'))
