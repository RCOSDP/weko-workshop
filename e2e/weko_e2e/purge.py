"""Physically remove what an e2e run created.

WEKO's own delete calls are mostly logical -- a deleted index, workflow or
flow keeps its row and is only hidden -- which is right for a repository
and wrong for a test environment that wants to go back to how
``install.sh`` left it.  This script does the physical removal.

``e2ectl clean --hard`` copies it into the ``web`` container and runs it
there; this suite lives in its own repository, so it is not on the
container's bind mount and cannot be run from one::

    docker compose -f docker-compose2.yml exec -T web \\
        sh -c 'cat > /tmp/weko-e2e-purge.py' < purge.py
    docker compose -f docker-compose2.yml exec -T web \\
        invenio shell /tmp/weko-e2e-purge.py /tmp/weko-e2e-purge.json

It reads one JSON document -- ``{"items": [...], "activities": [...],
"workflows": [...], "flows": [...], "indexes": [...], "container_repo":
"/code"}`` -- and prints one JSON line reporting what it removed, which is
what ``e2ectl`` parses.

This file runs under the container's Python 3.6, not the Python the rest
of the suite runs under, so keep it to what 3.6 accepts.
"""

from __future__ import print_function

import json
import os
import sys
import traceback

MARKER = 'WEKO_E2E_PURGE_RESULT: '
"""Prefix of the one line of output ``e2ectl`` reads back."""

ACTIVITY_TABLES = [
    'workflow_action_history',
    'workflow_activity_action',
    'workflow_action_journal',
    'workflow_action_identifier',
    'workflow_action_feedbackmail',
    'workflow_activity_item_application',
    'workflow_activity_request_mail',
    'guest_activity',
    'workflow_activity',
]
"""Tables holding an activity, the one holding the activity itself last."""


def _columns(engine, table):
    """Return the column names of a table, empty when there is no table."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    try:
        return set(column['name'] for column in inspector.get_columns(table))
    except Exception:
        return set()


ITEM_METADATA_TABLES = [
    'item_metadata_version',
    'item_metadata',
    'records_metadata_version',
    'records_metadata',
]
"""The metadata rows a record leaves behind, versions before rows."""

ITEM_UUID_TABLES = [
    'doi_deposit_log',
]
"""Other tables keyed by the record's uuid.

A DOI deposit leaves a row here holding what was sent and what the agency
answered; it outlives the record, so a run that deposited would otherwise
leave its correspondence behind.
"""


def _try(db, statement, params, problems):
    """Run one delete, and carry on when the instance refuses it.

    Each statement gets its own savepoint, so a table this instance shapes
    or constrains differently costs its own row and not the whole sweep.
    """
    try:
        with db.session.begin_nested():
            db.session.execute(statement, params)
    except Exception as error:
        problems.append('{0}: {1}'.format(
            statement.split()[2], str(error).split(chr(10))[0]))


def _item_pids(db, recid):
    """Return every pid row of a record.

    The record's own identifiers -- the versions and the parent -- are
    found by value; the identifiers *granted* to it, a DOI or an ARK, have
    values of their own and are found through the objects those first ones
    point at.  Leaving a granted DOI behind would keep the prefix in use
    and make the next run's grant look wrong.
    """
    rows = db.session.execute(
        'SELECT id, object_uuid FROM pidstore_pid WHERE pid_value = :recid'
        ' OR pid_value LIKE :versions OR pid_value = :parent',
        {'recid': recid, 'versions': recid + '.%',
         'parent': 'parent:' + recid}).fetchall()
    uuids = sorted(set(str(row[1]) for row in rows if row[1] is not None))
    ids = set(row[0] for row in rows)
    if uuids:
        granted = db.session.execute(
            'SELECT id FROM pidstore_pid WHERE object_uuid IN :uuids',
            {'uuids': tuple(uuids)}).fetchall()
        ids.update(row[0] for row in granted)
    return sorted(ids), uuids


def item_buckets(db, recid):
    """Return the file buckets a record's versions use.

    Asked before anything is deleted, because both ``deleteItem`` and the
    sweep remove what links a bucket to its record; a bucket looked for
    afterwards cannot be found, and ``deleteItem`` only marks buckets
    deleted rather than removing the rows.
    """
    _, uuids = _item_pids(db, recid)
    if not uuids:
        return []
    params = {'uuids': tuple(uuids)}
    found = [str(row[0]) for row in db.session.execute(
        'SELECT bucket_id FROM records_buckets WHERE record_id IN :uuids',
        params).fetchall()]
    try:
        rows = db.session.execute(
            "SELECT json->'_buckets'->>'deposit' FROM records_metadata"
            ' WHERE id IN :uuids', params).fetchall()
    except Exception:
        db.session.rollback()
        rows = []
    for row in rows:
        if row[0] and str(row[0]) not in found:
            found.append(str(row[0]))
    return found


def _sweep_item(db, recid, known_buckets=()):
    """Remove whatever rows are left of a record.

    ``deleteItem`` stops at the first thing that is already gone, which is
    normal when WEKO's own delete has run first, so this runs afterwards
    and makes sure nothing of the record is left behind either way.

    The order is the one the foreign keys demand: what points at a bucket
    before the bucket itself, the record's own rows before its identifiers.

    :param known_buckets: buckets collected before anything was deleted
    :return: ``(pid rows still there, what the database refused)``
    """
    problems = []
    pid_ids, uuids = _item_pids(db, recid)
    buckets = list(known_buckets)
    for bucket in item_buckets(db, recid):
        if bucket not in buckets:
            buckets.append(bucket)

    if uuids:
        uuid_params = {'uuids': tuple(uuids)}
        _try(db, 'DELETE FROM records_buckets WHERE record_id IN :uuids',
             uuid_params, problems)
        for table in ITEM_UUID_TABLES:
            if 'item_uuid' not in _columns(db.engine, table):
                continue
            _try(db,
                 'DELETE FROM {0} WHERE item_uuid IN :uuids'.format(table),
                 uuid_params, problems)
        for table in ITEM_METADATA_TABLES:
            if not _columns(db.engine, table):
                continue
            _try(db, 'DELETE FROM {0} WHERE id IN :uuids'.format(table),
                 uuid_params, problems)

    # Outside the block above: ``deleteItem`` removes the record and its
    # identifiers on its way through, and the buckets it leaves behind --
    # it only marks those deleted -- would then have nothing left to find
    # them by.
    if buckets:
        bucket_params = {'buckets': tuple(buckets)}
        files = [str(row[0]) for row in db.session.execute(
            'SELECT file_id FROM files_object WHERE bucket_id IN :buckets',
            bucket_params).fetchall()]
        _try(db, 'DELETE FROM files_object WHERE bucket_id IN :buckets',
             bucket_params, problems)
        # Only the buckets and files nothing else still points at.
        _try(db, 'DELETE FROM files_bucket WHERE id IN :buckets'
                 ' AND NOT EXISTS (SELECT 1 FROM records_buckets r'
                 ' WHERE r.bucket_id = files_bucket.id)',
             bucket_params, problems)
        if files:
            _try(db, 'DELETE FROM files_files WHERE id IN :files'
                     ' AND NOT EXISTS (SELECT 1 FROM files_object o'
                     ' WHERE o.file_id = files_files.id)',
                 {'files': tuple(files)}, problems)

    if pid_ids:
        pid_params = {'ids': tuple(pid_ids)}
        _try(db, 'DELETE FROM pidrelations_pidrelation'
                 ' WHERE parent_id IN :ids OR child_id IN :ids',
             pid_params, problems)
        _try(db, 'DELETE FROM pidstore_redirect WHERE pid_id IN :ids',
             pid_params, problems)
        _try(db, 'DELETE FROM pidstore_pid WHERE id IN :ids', pid_params,
             problems)
    db.session.commit()
    return _item_pids(db, recid)[0], problems


def purge_items(recids, report, container_repo='/code'):
    """Hard delete records, their files, their PIDs and their ES documents.

    The WEKO checkout's own ``tools/deleteItem.py`` is what removes the
    Elasticsearch documents and the stored files, so it is used rather
    than reimplemented; the sweep afterwards is what guarantees the rows
    are gone, whether or not that tool ran all the way through.

    :param container_repo: where the WEKO checkout is mounted in this
        container, which is where ``tools/deleteItem.py`` is read from
    """
    if not recids:
        return
    from invenio_db import db

    sys.path.insert(0, os.path.join(container_repo, 'tools'))
    try:
        from deleteItem import deleteItem
    except Exception as error:
        deleteItem = None
        report['errors'].append('deleteItem unavailable: {0}'.format(error))

    for recid in recids:
        recid = str(recid).split('.')[0]
        try:
            buckets = item_buckets(db, recid)
        except Exception:
            db.session.rollback()
            buckets = []
        if deleteItem is not None:
            try:
                deleteItem(recid)
            except Exception:
                db.session.rollback()
        try:
            left, problems = _sweep_item(db, recid, buckets)
        except Exception as error:
            db.session.rollback()
            report['errors'].append('item {0}: {1}'.format(recid, error))
            continue
        if left:
            report['errors'].append(
                'item {0}: {1} pid row(s) left; {2}'.format(
                    recid, len(left),
                    '; '.join(problems) or 'no reason given'))
        else:
            report['items'].append(recid)
            for problem in problems:
                report['errors'].append(
                    'item {0}: left behind, {1}'.format(recid, problem))


def activity_items(activity_ids):
    """Return the record ids of the items activities were working on.

    An activity that never reached the end still left a draft deposit
    behind, and a run that failed there never recorded a record id -- the
    activity is the only thing that knows about it.  Reading it back here
    is what keeps a failed run from leaving a draft in the database.
    """
    if not activity_ids:
        return []
    from invenio_db import db

    found = []
    for activity_id in activity_ids:
        try:
            rows = db.session.execute(
                'SELECT p.pid_value FROM workflow_activity a'
                ' JOIN pidstore_pid p ON p.object_uuid = a.item_id'
                " WHERE a.activity_id = :id AND p.pid_type = 'recid'",
                {'id': activity_id}).fetchall()
        except Exception:
            db.session.rollback()
            continue
        for row in rows:
            recid = str(row[0]).split('.')[0]
            if recid not in found:
                found.append(recid)
    return found


def workflow_activities(workflow_uuids):
    """Return the ids of every activity of the given workflows.

    The activity list screen does not show the activity id unless the
    instance is configured to, so this is where a stray activity is found:
    from the workflow it belongs to, in the database.
    """
    if not workflow_uuids:
        return []
    from invenio_db import db

    found = []
    for uuid in workflow_uuids:
        try:
            rows = db.session.execute(
                'SELECT a.activity_id FROM workflow_activity a'
                ' JOIN workflow_workflow w ON w.id = a.workflow_id'
                ' WHERE w.flows_id = :id', {'id': uuid}).fetchall()
        except Exception:
            db.session.rollback()
            continue
        for row in rows:
            if row[0] not in found:
                found.append(row[0])
    return found


def purge_activities(activity_ids, report):
    """Delete activities and every row hanging off them."""
    if not activity_ids:
        return
    from invenio_db import db

    for activity_id in activity_ids:
        try:
            for table in ACTIVITY_TABLES:
                if 'activity_id' not in _columns(db.engine, table):
                    continue
                db.session.execute(
                    'DELETE FROM {0} WHERE activity_id = :id'.format(table),
                    {'id': activity_id})
            # An activity also has an identifier of its own in the pid
            # store, which outlives the workflow tables it is deleted from.
            db.session.execute(
                "DELETE FROM pidstore_pid WHERE pid_type = 'actid'"
                ' AND pid_value = :id', {'id': activity_id})
            db.session.commit()
            report['activities'].append(activity_id)
        except Exception as error:
            db.session.rollback()
            report['errors'].append(
                'activity {0}: {1}'.format(activity_id, error))


def purge_workflows(uuids, report):
    """Delete workflows by their ``flows_id``, roles included."""
    if not uuids:
        return
    from invenio_db import db

    for uuid in uuids:
        try:
            db.session.execute(
                'DELETE FROM workflow_userrole WHERE workflow_id IN '
                '(SELECT id FROM workflow_workflow WHERE flows_id = :id)',
                {'id': uuid})
            db.session.execute(
                'DELETE FROM workflow_workflow WHERE flows_id = :id',
                {'id': uuid})
            db.session.commit()
            report['workflows'].append(uuid)
        except Exception as error:
            db.session.rollback()
            report['errors'].append('workflow {0}: {1}'.format(uuid, error))


def purge_flows(uuids, report):
    """Delete flows by their ``flow_id``, actions and roles included."""
    if not uuids:
        return
    from invenio_db import db

    for uuid in uuids:
        try:
            db.session.execute(
                'DELETE FROM workflow_flow_action_role WHERE flow_action_id '
                'IN (SELECT id FROM workflow_flow_action '
                'WHERE flow_id = :id)', {'id': uuid})
            db.session.execute(
                'DELETE FROM workflow_flow_action WHERE flow_id = :id',
                {'id': uuid})
            db.session.execute(
                'DELETE FROM workflow_flow_define WHERE flow_id = :id',
                {'id': uuid})
            db.session.commit()
            report['flows'].append(uuid)
        except Exception as error:
            db.session.rollback()
            report['errors'].append('flow {0}: {1}'.format(uuid, error))


def _with_descendants(db, index_id):
    """Return an index id together with every index below it."""
    found = [int(index_id)]
    frontier = [int(index_id)]
    while frontier:
        rows = db.session.execute(
            'SELECT id FROM "index" WHERE parent = :id',
            {'id': frontier.pop()}).fetchall()
        for row in rows:
            if row[0] not in found:
                found.append(row[0])
                frontier.append(row[0])
    return found


def purge_indexes(index_ids, report):
    """Delete index rows, and rebuild the tree the screens read from Redis."""
    if not index_ids:
        return
    from invenio_db import db

    for index_id in index_ids:
        try:
            for target in reversed(_with_descendants(db, index_id)):
                db.session.execute(
                    'DELETE FROM "index" WHERE id = :id', {'id': target})
            db.session.commit()
            report['indexes'].append(index_id)
        except Exception as error:
            db.session.rollback()
            report['errors'].append('index {0}: {1}'.format(index_id, error))
    _refresh_index_cache(report)


def _refresh_index_cache(report):
    """Rebuild the cached index trees, which the REST delete would have.

    The screens read the tree from Redis, so deleting rows behind WEKO's
    back leaves the deleted index on screen until the cache is rebuilt.
    The rebuild reads the current language, which only exists inside a
    request, so one is pushed for it -- ``invenio shell`` has none.
    """
    try:
        from flask import current_app
        from weko_admin.models import AdminLangSettings
        from weko_index_tree.api import Indexes
        from weko_index_tree.utils import (
            delete_index_reset_ignore_more_trees_from_redis,
            delete_index_reset_trees_from_redis, save_index_trees_to_redis)

        with current_app.test_request_context():
            languages = AdminLangSettings.get_registered_language()
            tree_ja = Indexes.get_index_tree(lang='ja')
            tree = Indexes.get_index_tree(lang='other_lang')
            for language in languages:
                code = language['lang_code']
                save_index_trees_to_redis(tree_ja if code == 'ja' else tree,
                                          lang=code)
                delete_index_reset_trees_from_redis(code)
                delete_index_reset_ignore_more_trees_from_redis(code)
    except Exception as error:
        report['errors'].append('index cache: {0}'.format(error))


def main(spec_path):
    """Purge everything the spec names and print the report."""
    with open(spec_path) as handle:
        spec = json.load(handle)

    report = {'items': [], 'activities': [], 'workflows': [], 'flows': [],
              'indexes': [], 'errors': []}
    workflows = spec.get('workflows') or []
    activities = list(spec.get('activities') or [])
    # A workflow knows its activities even when the ledger does not.
    for activity_id in workflow_activities(workflows):
        if activity_id not in activities:
            activities.append(activity_id)
    items = list(spec.get('items') or [])
    # An activity that was quit still holds a draft deposit; purge it too,
    # whether or not the run got far enough to record its record id.
    for recid in activity_items(activities):
        if recid not in items:
            items.append(recid)
    purge_items(items, report, spec.get('container_repo') or '/code')
    purge_activities(activities, report)
    purge_workflows(workflows, report)
    purge_flows(spec.get('flows') or [], report)
    purge_indexes(spec.get('indexes') or [], report)
    print(MARKER + json.dumps(report))
    return 0 if not report['errors'] else 1


if __name__ == '__main__':
    if len(sys.argv) < 2 or not os.path.isfile(sys.argv[1]):
        print('usage: invenio shell purge.py <spec.json>', file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(main(sys.argv[1]))
    except Exception:
        traceback.print_exc()
        print(MARKER + json.dumps({'errors': ['purge script failed']}))
        sys.exit(1)
