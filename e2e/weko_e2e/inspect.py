"""Report what state a WEKO instance is in, from inside the container.

``e2ectl doctor`` copies this into the ``web`` container and runs it
there, because most of what it has to know -- which accounts hold which
roles, whether this month's log partition exists, what the instance
configuration actually says -- is not on any screen.

    docker compose -f docker-compose2.yml exec -T web \\
        sh -c 'cat > /tmp/weko-e2e-inspect.py' < inspect.py
    docker compose -f docker-compose2.yml exec -T web \\
        invenio shell /tmp/weko-e2e-inspect.py

It changes nothing.  One JSON line is printed, which ``e2ectl`` parses
and turns into the checks; gathering it all in one call is what keeps
``doctor`` quick, because every ``docker compose exec`` costs seconds.

This file runs under the container's Python 3.6, not the Python the rest
of the suite runs under, so keep it to what 3.6 accepts.
"""

from __future__ import print_function

import json
import sys
import traceback
from datetime import datetime

MARKER = 'WEKO_E2E_INSPECT: '
"""Prefix of the one line ``e2ectl`` reads back."""

COUNTS = [
    ('indexes', 'SELECT count(*) FROM "index"'),
    ('flows', 'SELECT count(*) FROM workflow_flow_define'),
    ('workflows', 'SELECT count(*) FROM workflow_workflow'),
    ('activities', 'SELECT count(*) FROM workflow_activity'),
    ('records', 'SELECT count(*) FROM records_metadata'),
    ('buckets', 'SELECT count(*) FROM files_bucket'),
    ('pids', 'SELECT count(*) FROM pidstore_pid'),
    ('identifiers', 'SELECT count(*) FROM doi_identifier'),
]
"""What an instance holds, so a run can say how far it is from baseline.

``install.sh`` leaves one index, one flow, two workflows, one row of
identifier settings and nothing else, so anything above that is either
somebody's work or a run that was never cleaned up.
"""

SETTINGS = [
    'WEKO_NOTIFICATIONS',
    'WEKO_NOTIFICATIONS_INBOX_ADDRESS',
    'WEKO_NOTIFICATIONS_PUSH_TEMPLATE_PATH',
    'WEKO_HANDLE_ALLOW_REGISTER_ARK',
    'WEKO_CROSSREF_ALLOW_REGISTER_DOI',
    'THEME_SITEURL',
    'WEKO_ADMIN_PERMISSION_ROLE_REPO',
    'WEKO_PERMISSION_SUPER_ROLE_USER',
]
"""Instance settings the suites depend on, reported as the app sees them.

They come from ``instance.cfg`` by way of ``invenio.cfg``, so reading
them here is the only way to know what the running application believes
rather than what a file on disk says.
"""


def _rows(db, statement):
    """Return the rows of one query, or an empty list."""
    try:
        return db.session.execute(statement).fetchall()
    except Exception:
        db.session.rollback()
        return []


def _one(db, statement, default=0):
    """Return the single value of one query, or a default."""
    rows = _rows(db, statement)
    return rows[0][0] if rows else default


def accounts(db):
    """Return ``{email: [role, ...]}`` for every account."""
    found = {}
    for row in _rows(db, 'SELECT u.email, r.name FROM accounts_user u'
                         ' LEFT JOIN accounts_userrole ur'
                         ' ON ur.user_id = u.id'
                         ' LEFT JOIN accounts_role r ON r.id = ur.role_id'):
        found.setdefault(row[0], [])
        if row[1]:
            found[row[0]].append(row[1])
    return found


def partitions(db):
    """Return the names of ``user_activity_logs``'s partitions.

    WEKO writes a log row for most requests, and the table is partitioned
    by month; a month with no partition of its own fails every write, and
    with it the request that made it -- which is what an item
    registration that stops at Next turns out to be.

    :return: ``None`` when the table is not partitioned at all
    """
    parent = _one(db, "SELECT count(*) FROM pg_partitioned_table p"
                      " JOIN pg_class c ON c.oid = p.partrelid"
                      " WHERE c.relname = 'user_activity_logs'")
    if not parent:
        return None
    return sorted(str(row[0]) for row in _rows(
        db, 'SELECT c.relname FROM pg_class c'
            ' JOIN pg_inherits i ON i.inhrelid = c.oid'
            ' JOIN pg_class p ON p.oid = i.inhparent'
            " WHERE p.relname = 'user_activity_logs'"))


def search_blocks():
    """Return the indices Elasticsearch has stopped accepting writes to.

    Elasticsearch puts every index into ``read_only_allow_delete`` when
    the disk it is on crosses its flood-stage watermark, and does not
    always take it off again when space comes back.  WEKO goes on
    answering and searching while that is true, and registering an item
    fails with "Server Error. Please reload this page." -- which names
    neither Elasticsearch nor the disk.

    :return: the blocked index names, or None when it could not be asked
    """
    try:
        from invenio_search import current_search_client
        state = current_search_client.cluster.state(metric='blocks')
    except Exception:
        return None
    blocked = []
    for name, blocks in ((state or {}).get('blocks', {})
                         .get('indices', {}) or {}).items():
        for block in (blocks or {}).values():
            # By what it stops rather than by what it is called: the
            # description is prose ("index read-only / allow delete
            # (api)") and the levels are the thing itself.
            if 'write' in ((block or {}).get('levels') or []):
                blocked.append(str(name))
                break
    return sorted(blocked)


def report():
    """Return everything ``doctor`` asks about this instance."""
    from flask import current_app
    from invenio_db import db

    found = {
        'accounts': accounts(db),
        'roles': sorted(str(row[0]) for row in _rows(
            db, 'SELECT name FROM accounts_role')),
        'item_types': sorted(str(row[0]) for row in _rows(
            db, 'SELECT name FROM item_type_name')),
        'actions': [str(row[0]) for row in _rows(
            db, 'SELECT action_name FROM workflow_action ORDER BY id')],
        'flows': sorted(str(row[0]) for row in _rows(
            db, 'SELECT flow_name FROM workflow_flow_define')),
        'locations': [str(row[0]) for row in _rows(
            db, 'SELECT uri FROM files_location')],
        'languages': sorted(str(row[0]) for row in _rows(
            db, 'SELECT lang_code FROM admin_lang_settings'
                ' WHERE is_active')),
        'partitions': partitions(db),
        'search_blocks': search_blocks(),
        'today': datetime.now().strftime('%Y%m'),
        'counts': {},
        'settings': {},
    }
    for name, statement in COUNTS:
        found['counts'][name] = _one(db, statement)
    for name in SETTINGS:
        value = current_app.config.get(name)
        found['settings'][name] = value if isinstance(
            value, (bool, int, float, list, type(None))) else str(value)
    return found


def main():
    """Print the report and say whether it could be gathered."""
    print(MARKER + json.dumps(report()))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        print(MARKER + json.dumps({'error': 'inspection failed'}))
        sys.exit(1)
