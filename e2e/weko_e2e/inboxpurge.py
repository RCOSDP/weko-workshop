"""Remove from the LDN inbox the notifications one e2e run produced.

``e2ectl clean --hard`` copies this into the ``inbox`` container and runs
it there.  The inbox is a service of its own with a database of its own --
MongoDB -- and the credentials for it belong to that container and not to
this suite, so the work is done where they already are, through the
inbox's own database layer.

    docker compose -f docker-compose2.yml exec -T inbox \\
        sh -c 'cd /app && python /tmp/weko-e2e-inbox-purge.py A-20260919-00001'

Every notification WEKO sends about an activity carries that activity's
detail page as its ``context``, so the activity ids are all that is
needed to find them.  The read/unread state the inbox keeps beside each
notification goes with it.  One JSON line is printed, which ``e2ectl``
parses.
"""

from __future__ import print_function

import asyncio
import json
import sys
import traceback

sys.path.insert(0, '/app')

MARKER = 'WEKO_E2E_INBOX_RESULT: '
"""Prefix of the one line ``e2ectl`` reads back."""

LIMIT = 1000
"""Most notifications one activity could conceivably have produced."""


async def purge(activity_ids, report):
    """Remove the notifications about each activity, and say which."""
    from db.notifications import (get_notification_states_collection,
                                  get_notifications_collection)

    notifications = await get_notifications_collection()
    states = await get_notification_states_collection()
    for activity_id in activity_ids:
        try:
            rows = await notifications.find(
                {'context.id': {'$regex': '/{0}$'.format(activity_id)}},
                {'_id': 0, 'id': 1}).to_list(length=LIMIT)
            found = [row['id'] for row in rows if row.get('id')]
            if not found:
                continue
            await notifications.delete_many({'id': {'$in': found}})
            await states.delete_many({'id': {'$in': found}})
            report['notifications'] += found
        except Exception as error:
            report['errors'].append('{0}: {1}'.format(activity_id, error))


def main(activity_ids):
    """Purge the notifications of the given activities and report."""
    report = {'notifications': [], 'errors': []}
    asyncio.get_event_loop().run_until_complete(purge(activity_ids, report))
    print(MARKER + json.dumps(report))
    return 0 if not report['errors'] else 1


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        traceback.print_exc()
        print(MARKER + json.dumps({'errors': ['inbox purge failed']}))
        sys.exit(1)
