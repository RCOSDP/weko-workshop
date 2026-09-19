"""The registration flow itself, so that every suite walks the same one.

The base suite and the optional ones differ in what they ask WEKO for --
no identifier, an ARK, a Crossref DOI -- and not in how an item gets
registered.  That part lives here: the setup a run needs, the fields the
item type requires, and the walk from the metadata form to approval.

A suite is then the handful of steps that are actually its own.
"""

import datetime

from . import ui
from .client import DEFAULT_FLOW_ACTIONS

PUB_DATE = datetime.date.today().isoformat()
"""Today, so the item is published rather than embargoed."""

TITLE_LANGUAGE = 'string:en'
PREFERRED_RESOURCE_TYPE = 'string:conference paper'
"""Resource type to choose, when the item type offers it."""

JOURNAL_TITLE = 'Journal of WEKO E2E Studies'
ISSN = '0317-8471'
"""A structurally valid ISSN: WEKO checks the check digit before depositing."""


# -- the fields of the default full item type ------------------------------
#
# The control names of an item type's form carry its id, so they are built
# rather than written out; an item type whose properties are numbered
# differently needs its own builders.

def title_field(item_type_id):
    """Return the form control name of the item's title."""
    return 'item_{0}_title0.0.subitem_title'.format(item_type_id)


def title_language_field(item_type_id):
    """Return the form control name of the title's language."""
    return 'item_{0}_title0.0.subitem_title_language'.format(item_type_id)


def resource_type_field(item_type_id):
    """Return the form control name of the item's resource type."""
    return 'item_{0}_resource_type13.resourcetype'.format(item_type_id)


def source_title_field(item_type_id):
    """Return the form control name of the journal title."""
    return 'item_{0}_source_title23.0.subitem_source_title'.format(
        item_type_id)


def source_title_language_field(item_type_id):
    """Return the form control name of the journal title's language."""
    return 'item_{0}_source_title23.0.subitem_source_title_language'.format(
        item_type_id)


def source_identifier_field(item_type_id):
    """Return the form control name of the journal's identifier."""
    return 'item_{0}_source_identifier22.0.subitem_source_identifier'.format(
        item_type_id)


def source_identifier_type_field(item_type_id):
    """Return the form control name of that identifier's type."""
    return ('item_{0}_source_identifier22.0'
            '.subitem_source_identifier_type'.format(item_type_id))


def date_issued_type_field(item_type_id):
    """Return the form control name of the issue date's type."""
    return 'item_{0}_date11.0.subitem_date_issued_type'.format(item_type_id)


# -- setup -----------------------------------------------------------------

def set_up_index(client, settings, record, public=True):
    """Create the index the run registers its item in, and record it.

    :param record: the conftest fixture that writes to the ledger
    :return: the new index id
    """
    index_id = client.create_index(settings.index_name, public=public)
    record('index', index_id, settings.index_name)
    return index_id


def set_up_workflow(client, settings, record, actions=None, index_id=None):
    """Create the flow and the workflow the run registers through.

    :param actions: flow action names, defaulting to the six of the
        shipped ``Registration Flow``
    :param index_id: index to designate on the workflow.  Leave it None:
        a workflow that names an index designates it by itself, and the
        index designation screen then never appears.
    :return: ``(item type id, flow uuid, workflow uuid)``
    """
    flow_id = client.create_flow(settings.flow_name,
                                 actions or DEFAULT_FLOW_ACTIONS)
    record('flow', flow_id, settings.flow_name)

    item_type_id = client.item_type_id(settings.item_type_name)
    workflow_id = client.create_workflow(
        settings.workflow_name,
        item_type_id=item_type_id,
        flow_id=client.flow_numeric_id(settings.flow_name),
        index_id=index_id)
    record('workflow', workflow_id, settings.workflow_name)
    return item_type_id, flow_id, workflow_id


def start_activity(page, settings, record):
    """Start an activity on the workflow this run defined, and record it."""
    activity_id = ui.start_activity(page, settings, settings.workflow_name)
    record('activity', activity_id, settings.workflow_name)
    return activity_id


# -- the metadata form -----------------------------------------------------

def fill_required_metadata(page, settings, item_type_id):
    """Fill what the default full item type requires.

    The publication date, a title and a resource type; everything else is
    optional as far as registration is concerned.

    :return: the resource type that was chosen
    """
    ui.field(page, 'pubdate').fill(PUB_DATE)
    ui.field(page, title_field(item_type_id)).fill(settings.item_title)
    ui.field(page, title_language_field(item_type_id)).select_option(
        TITLE_LANGUAGE)

    resource_type = ui.field(page, resource_type_field(item_type_id))
    offered = resource_type.locator('option').evaluate_all(
        'options => options.map(option => option.value)')
    choice = PREFERRED_RESOURCE_TYPE if PREFERRED_RESOURCE_TYPE in offered \
        else next(value for value in offered if value and value != 'string:')
    resource_type.select_option(choice)
    return choice


def fill_journal_metadata(page, item_type_id, journal_title=JOURNAL_TITLE,
                          issn=ISSN, date=PUB_DATE):
    """Fill what a Crossref deposit needs beyond the required fields.

    Crossref will not take a journal article without the journal it
    appeared in, its ISSN and the date it was issued, and WEKO refuses the
    grant rather than depositing something Crossref would reject.
    """
    ui.field(page, source_title_field(item_type_id)).fill(journal_title)
    ui.field(page, source_title_language_field(item_type_id)).select_option(
        TITLE_LANGUAGE)
    ui.field(page, source_identifier_field(item_type_id)).fill(issn)
    ui.field(page, source_identifier_type_field(item_type_id)).select_option(
        'string:ISSN')
    # The date picker's visible input carries the bare sub item name.
    ui.field(page, 'subitem_date_issued_datetime').fill(date)
    ui.field(page, date_issued_type_field(item_type_id)).select_option(
        'string:Issued')


# -- walking the activity --------------------------------------------------

def upload_sample_file(page, settings):
    """Attach the sample file the item is registered with."""
    ui.upload_file(page, ui.sample_file(),
                   timeout=settings.upload_timeout * 1000)


def leave_metadata_screen(page, settings):
    """Move on from the metadata form to the index designation screen."""
    ui.click_next(page)
    ui.wait_for_index_tree(page, settings.index_name,
                           timeout=settings.step_timeout * 1000)


def designate_index(page, settings):
    """Designate the run's index and walk on to the item link step."""
    ui.designate_index(page, settings.index_name)
    ui.advance_to(page, ui.ITEM_LINK, timeout=settings.step_timeout)


def leave_item_link(page, settings):
    """Link no other item, and walk on to the identifier grant step."""
    ui.click_next(page)
    ui.wait_for_step(page, ui.IDENTIFIER_GRANT, timeout=settings.step_timeout)


def choose_identifier_grant(page, settings, value='0'):
    """Pick an identifier grant and walk on to approval.

    :param value: the grant's radio value -- ``0`` Not Grant, ``1`` JaLC
        DOI, ``2`` Crossref DOI, ``3`` DataCite DOI
    :raise AssertionError: when the screen does not offer that grant
    """
    radio = page.locator(
        "input[type=radio][name=identifier_grant][value='{0}']".format(
            value)).locator('visible=true')
    assert radio.count(), \
        'the identifier grant screen does not offer grant {0!r}; the ' \
        'grant has to be turned on under /admin/identifier/ first'.format(
            value)
    radio.first.check()
    page.wait_for_timeout(1000)
    ui.click_next(page)
    ui.wait_for_step(page, ui.APPROVAL, timeout=settings.step_timeout)


def approve(page):
    """Approve the activity and return the record it registered."""
    ui.approve(page)
    recid = ui.registered_recid(page)
    assert recid, 'the finished activity does not point at a record'
    return recid
