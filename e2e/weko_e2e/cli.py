"""``e2ectl`` -- look at, and clear away, what the e2e runs created.

A run records every index, flow, workflow, activity and item it creates in
``e2e/.e2e-state.json``, and this reads that back and deletes them, newest
dependency first.  A run whose ledger was lost is still cleanable: with
``--discover`` the tool finds the leftovers by the name prefix every run
gives its resources.

    e2ectl env                    the settings a run would use
    e2ectl ark-account enable     a real ARK server, for the ark suite
    e2ectl ark-stub enable        a stand-in ARK server, when there is none
    e2ectl crossref-account enable    the Crossref account, for depositing
    e2ectl doi-log                what WEKO sent to a registration agency
    e2ectl inbox                  what WEKO sent over COAR Notify
    e2ectl webpush-stub enable    a stand-in browser, for the web push steps
    e2ectl ping                   can it reach the instance and log in
    e2ectl status                 what is still there
    e2ectl clean                  delete it, the way the screens do
    e2ectl clean --hard           and remove the rows WEKO only hides
    e2ectl clean --run 20260916-120000    just that run
    e2ectl clean --discover       also anything else named "E2E ..."
"""

import argparse
import json
import os
import subprocess
import sys
import time

import requests

from . import notify
from .client import WekoClient, WekoError
from .config import HERE, Settings
from .inboxpurge import MARKER as INBOX_MARKER
from .ledger import KINDS, Ledger
from .purge import MARKER

PURGE_IN_CONTAINER = '/tmp/weko-e2e-purge.py'
SPEC_IN_CONTAINER = '/tmp/weko-e2e-purge.json'
INBOX_PURGE_IN_CONTAINER = '/tmp/weko-e2e-inbox-purge.py'
INBOX_SHOWN = 10
"""How many notifications ``e2ectl inbox`` prints per account."""
LOG_MARKER = 'WEKO_E2E_DOI_LOG: '
"""Prefix of the one line :func:`deposit_log` reads back."""

PUSH_STUB_IN_CONTAINER = '/tmp/weko-e2e-push-stub.py'
PUSH_STUB_PORT = 8901
PUSH_MARKER = 'WEKO_E2E_PUSH_STUB: '
"""Prefix of the one line a call to the push stub reads back."""

WEBPUSH_BLOCK_START = '      # >>> weko-e2e webpush stub >>>'
WEBPUSH_BLOCK_END = '      # <<< weko-e2e webpush stub <<<'
VAPID_KEYS = ('VAPID_PUBLIC_KEY', 'VAPID_PRIVATE_KEY')
"""The two the inbox needs before it can send a Web Push at all.

They live in the compose file rather than in ``instance.cfg``, because
they belong to the inbox service and not to WEKO; the shipped file leaves
them empty, which is why a default stack sends no push.
"""

ARK_STUB_IN_CONTAINER = '/tmp/weko-e2e-ark-stub.py'
ARK_STUB_PORT = 8899
ARK_STUB_NAAN = '99999'
ARK_STUB_SHOULDER = 'fk4'
ARK_STUB_KEY = 'weko-e2e-ark-stub-key'

ARK_ACCOUNT_BLOCK_START = '# >>> weko-e2e ark account >>>'
ARK_ACCOUNT_BLOCK_END = '# <<< weko-e2e ark account <<<'

CROSSREF_BLOCK_START = '# >>> weko-e2e crossref account >>>'
CROSSREF_BLOCK_END = '# <<< weko-e2e crossref account <<<'

ARK_BLOCK_START = '# >>> weko-e2e ark stub >>>'
ARK_BLOCK_END = '# <<< weko-e2e ark stub <<<'
ARK_BLOCK = '''{start}
WEKO_HANDLE_ALLOW_REGISTER_ARK = True
WEKO_HANDLE_ARK_MINT_URL = 'http://127.0.0.1:{port}/mint'
WEKO_HANDLE_ARK_LOGIN_URL = 'http://127.0.0.1:{port}/login'
WEKO_HANDLE_ARK_NAAN = '{naan}'
WEKO_HANDLE_ARK_SHOULDER = '{shoulder}'
WEKO_HANDLE_ARK_API_KEY = '{key}'
{end}
'''.format(start=ARK_BLOCK_START, end=ARK_BLOCK_END, port=ARK_STUB_PORT,
           naan=ARK_STUB_NAAN, shoulder=ARK_STUB_SHOULDER, key=ARK_STUB_KEY)
"""What ``ark-stub enable`` adds to the instance configuration.

It goes into the WEKO checkout's ``scripts/instance.cfg`` -- the file the
container renders its ``invenio.cfg`` from on every start, and the place
this repository's own notes say instance settings belong -- between
markers, so that ``ark-stub disable`` can take exactly it away again.
"""
"""Where the purge script and its spec are put inside the container.

This suite does not live in the WEKO checkout, so nothing of it is on the
container's bind mount; the script is copied in for the one call instead
of being run from a path that would have to exist there.
"""


# -- gathering -------------------------------------------------------------

def _targets(ledger, run_id=None):
    """Return ``{kind: [resource, ...]}`` from the ledger."""
    targets = dict((kind, []) for kind in KINDS)
    for _, resource in ledger.resources(run_id):
        targets[resource['kind']].append(resource)
    return targets


def _discover(client, settings, targets):
    """Add anything named after the label that the ledger does not know.

    A run that was killed before it could write its ledger, or a ledger
    that was deleted, still leaves resources carrying the label; this finds
    them so that ``clean`` is not the only way back to a clean instance.
    """
    known = dict((kind, set(r['id'] for r in targets[kind])) for kind in KINDS)
    prefix = settings.label

    def walk(nodes):
        for node in nodes:
            name = node.get('name') or ''
            index_id = str(node['id'])
            if name.startswith(prefix) and index_id not in known['index']:
                targets['index'].append(
                    {'kind': 'index', 'id': index_id, 'name': name,
                     'discovered': True})
            walk(node.get('children') or [])

    walk(client.index_tree())

    for name, uuid in client.workflows().items():
        if name.startswith(prefix) and uuid not in known['workflow']:
            targets['workflow'].append(
                {'kind': 'workflow', 'id': uuid, 'name': name,
                 'discovered': True})
    for name, uuid in client.flows().items():
        if name.startswith(prefix) and uuid not in known['flow']:
            targets['flow'].append({'kind': 'flow', 'id': uuid, 'name': name,
                                    'discovered': True})

    # Items are found through the indexes they were registered in, which is
    # the only place a run's items are all together.
    for index in targets['index']:
        try:
            hits = client.recids_in_index(index['id'])
        except WekoError:
            continue
        for recid in sorted(hits):
            if recid not in known['item']:
                targets['item'].append(
                    {'kind': 'item', 'id': recid, 'discovered': True,
                     'name': 'in index {0}'.format(index['id'])})
                known['item'].add(recid)

    for activity in client.activities():
        row = activity['row']
        if prefix in row and activity['activity_id'] not in known['activity']:
            targets['activity'].append(
                {'kind': 'activity', 'id': activity['activity_id'],
                 'name': row[:60], 'discovered': True})
    return targets


# -- commands --------------------------------------------------------------

def command_status(args, settings, ledger):
    """Print the settings, and every resource the ledger still holds."""
    print(settings)
    print('ledger: {0}'.format(ledger.path))
    runs = ledger.runs()
    if not runs:
        print('  (no runs recorded)')
    for run in runs:
        print('  run {0}  started {1}  {2} resource(s)'.format(
            run['run_id'], run.get('started', '?'), len(run['resources'])))
        for resource in run['resources']:
            print('    {0:<9} {1:<24} {2}'.format(
                resource['kind'], resource['id'], resource.get('name', '')))
    if args.discover:
        client = WekoClient(settings).login()
        found = _discover(client, settings, _targets(ledger))
        print('named {0}* on {1}:'.format(settings.label, settings.base_url))
        for kind in KINDS:
            for resource in found[kind]:
                if resource.get('discovered'):
                    print('    {0:<9} {1:<24} {2}'.format(
                        kind, resource['id'], resource.get('name', '')))
    return 0


def command_env(args, settings, ledger):
    """Print what a run would use, without touching the instance."""
    for name, value in settings.describe():
        print('{0:<24} {1}'.format(name, value))
    return 0


def command_ping(args, settings, ledger):
    """Check that the instance answers and the account can log in."""
    client = WekoClient(settings)
    if not client.is_reachable():
        print('{0} does not answer'.format(settings.base_url))
        print('(settings: run "e2ectl env" to see what is being used)')
        return 1
    try:
        client.login()
    except WekoError as error:
        print(str(error))
        return 1
    options = client.workflow_form_options()
    print('{0} is up; logged in as {1}'.format(
        settings.base_url, settings.email))
    print('item types: {0}'.format(', '.join(sorted(options['itemtype']))))
    found = options['itemtype'].get(settings.item_type_name)
    print('item type under test: {0} ({1})'.format(
        settings.item_type_name,
        'id {0}'.format(found) if found else 'NOT FOUND'))
    print('hard purge: {0}'.format(
        'available ({0})'.format(settings.weko_repo) if settings.weko_repo
        else 'unavailable; set WEKO_E2E_REPO to the WEKO checkout'))
    return 0 if found else 1


def command_clean(args, settings, ledger):
    """Delete what the runs created."""
    targets = _targets(ledger, args.run)
    # A dry run that is not discovering has nothing to ask the instance,
    # and should say what it would do even while the stack is down.
    client = None
    if args.discover or not args.dry_run:
        client = WekoClient(settings).login()
    if args.discover:
        targets = _discover(client, settings, targets)

    total = sum(len(targets[kind]) for kind in KINDS)
    if not total:
        print('nothing to clean')
        return 0

    for kind in KINDS:
        for resource in targets[kind]:
            label = '{0} {1} {2}'.format(
                kind, resource['id'], resource.get('name', '')).strip()
            if args.dry_run:
                print('would delete {0}'.format(label))
                continue
            ok, detail = _delete(client, kind, resource['id'])
            print('{0} {1}{2}'.format(
                'deleted ' if ok else 'left    ', label,
                '' if ok else '  ({0})'.format(detail)))

    if args.hard and not args.dry_run:
        _hard_purge(settings, targets)

    if not args.dry_run and not args.keep_ledger:
        for run_id, resource in ledger.resources(args.run):
            ledger.drop(run_id, resource)
        ledger.drop_empty()
    return 0


def _delete(client, kind, identifier):
    """Delete one resource through the screens' own endpoints."""
    try:
        if kind == 'item':
            return client.soft_delete_item(identifier), 'delete refused'
        if kind == 'activity':
            return client.quit_activity(identifier), 'already finished'
        if kind == 'workflow':
            client.delete_workflow(identifier)
        elif kind == 'flow':
            client.delete_flow(identifier)
        elif kind == 'index':
            client.delete_index(identifier)
        return True, ''
    except WekoError as error:
        return False, str(error)


def _compose(settings, *arguments):
    """Return a ``docker compose`` command line for the WEKO checkout."""
    return ['docker', 'compose', '-f', settings.compose_file] + list(arguments)


def _in_service(settings, service, *arguments):
    """Return a command line running something in one container."""
    return _compose(settings, 'exec', '-T', service, *arguments)


def _in_web(settings, *arguments):
    """Return a command line running something in the web container."""
    return _in_service(settings, settings.web_service, *arguments)


def _copy_into_container(settings, content, path, service=None):
    """Write bytes to a path inside a container.

    :param service: the compose service, defaulting to ``web``
    :return: True when the container took it
    """
    result = subprocess.run(
        _in_service(settings, service or settings.web_service,
                    'sh', '-c', 'cat > {0}'.format(path)),
        cwd=settings.weko_repo, input=content,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        print(result.stdout.decode('utf-8', 'replace')[-2000:])
    return result.returncode == 0


def _hard_purge(settings, targets):
    """Run the purge script inside the ``web`` container."""
    if not settings.weko_repo:
        print('hard purge needs the WEKO checkout that owns {0}; '
              'set WEKO_E2E_REPO to it'.format(settings.compose_file))
        return
    spec = {
        'items': [r['id'] for r in targets['item']],
        'activities': [r['id'] for r in targets['activity']],
        'workflows': [r['id'] for r in targets['workflow']],
        'flows': [r['id'] for r in targets['flow']],
        'indexes': [r['id'] for r in targets['index']],
        'container_repo': settings.container_repo,
    }
    with open(os.path.join(HERE, 'purge.py'), 'rb') as handle:
        script = handle.read()
    if not _copy_into_container(settings, script, PURGE_IN_CONTAINER):
        print('could not copy the purge script into the container; '
              'is the stack up?')
        return
    if not _copy_into_container(
            settings, json.dumps(spec).encode('utf-8'), SPEC_IN_CONTAINER):
        print('could not copy the purge spec into the container')
        return

    command = _in_web(settings, 'invenio', 'shell',
                      PURGE_IN_CONTAINER, SPEC_IN_CONTAINER)
    print('hard purge: {0}'.format(' '.join(command)))
    result = subprocess.run(command, cwd=settings.weko_repo,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = result.stdout.decode('utf-8', 'replace')
    report = None
    for line in output.splitlines():
        if line.startswith(MARKER):
            report = json.loads(line[len(MARKER):])
    if report is None:
        print(output[-2000:])
        print('hard purge did not report; is the stack up?')
        return
    for kind in ('items', 'activities', 'workflows', 'flows', 'indexes'):
        if report.get(kind):
            print('purged {0}: {1}'.format(kind, ', '.join(
                str(value) for value in report[kind])))
    for error in report.get('errors') or []:
        print('purge error: {0}'.format(error))
    _purge_inbox(settings, targets)


def _purge_inbox(settings, targets):
    """Remove from the LDN inbox what this run's activities announced.

    The inbox is a service of its own with a database of its own, so it
    does not go back to its baseline when the WEKO database does; the
    notifications a run sent would otherwise pile up there for ever.

    Silent where the instance has no inbox container to speak to: an
    instance reached over the network is not a stack this tool can run
    ``docker compose`` in, and that is not an error.
    """
    activities = [resource['id'] for resource in targets['activity']]
    if not activities:
        return
    with open(os.path.join(HERE, 'inboxpurge.py'), 'rb') as handle:
        script = handle.read()
    if not _copy_into_container(settings, script, INBOX_PURGE_IN_CONTAINER,
                                service=settings.inbox_service):
        print('no {0} container to clear; the notifications this run sent '
              'are still in the inbox'.format(settings.inbox_service))
        return

    result = subprocess.run(
        _in_service(settings, settings.inbox_service, 'sh', '-c',
                    'cd /app && python {0} {1}'.format(
                        INBOX_PURGE_IN_CONTAINER, ' '.join(activities))),
        cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = result.stdout.decode('utf-8', 'replace')
    report = None
    for line in output.splitlines():
        if line.startswith(INBOX_MARKER):
            report = json.loads(line[len(INBOX_MARKER):])
    if report is None:
        print(output[-2000:])
        print('the inbox purge did not report; the notifications this run '
              'sent are still there')
        return
    if report.get('notifications'):
        print('purged notifications: {0}'.format(
            len(report['notifications'])))
    for error in report.get('errors') or []:
        print('inbox purge error: {0}'.format(error))


# -- COAR Notify -----------------------------------------------------------

def command_inbox(args, settings, ledger):
    """Print what this instance has sent over COAR Notify.

    A notification is addressed to a person, so it is read as that
    person: the account the suite registers with, and the account it has
    approve.  ``--run`` narrows the list to the notifications one run's
    activities produced, which is what the ``coarnotify`` suite checks.
    """
    activities = [resource['id']
                  for resource in _targets(ledger, args.run)['activity']] \
        if args.run else None
    if activities is not None and not activities:
        print('run {0} recorded no activity, so nothing was announced about '
              'it'.format(args.run))
        return 0

    for role, account in (
            ('registrant', settings),
            ('approver', settings.as_account(settings.approver_email,
                                             settings.approver_password))):
        print('{0}: {1}'.format(role, account.email))
        try:
            client = WekoClient(account).login()
        except WekoError as error:
            print('  cannot log in: {0}'.format(error))
            continue
        if role == 'registrant':
            print('  announced inbox: {0}'.format(
                notify.announced_inbox(client.session, account)
                or '(the site announces none)'))
        _print_notifications(client, account, activities)
    return 0


def _print_notifications(client, settings, activities):
    """Print one account's notifications, newest first."""
    urls = notify.notifications(client.session, settings)
    shown = 0
    for url in urls:
        payload = notify.fetch(client.session, settings, url)
        if activities is not None and not any(
                notify.is_about(payload, activity) for activity in activities):
            continue
        print('  {0}  {1}'.format(payload.get('updated'),
                                  notify.summary(payload)))
        shown += 1
        if activities is None and shown >= INBOX_SHOWN:
            break
    print('  {0} of {1} notification(s) shown'.format(shown, len(urls)))


# -- the web push stand-in -------------------------------------------------

def _compose_path(settings):
    """Return the compose file of the WEKO checkout."""
    return os.path.join(settings.weko_repo, settings.compose_file)


def _generate_vapid_keys(settings):
    """Return a VAPID key pair, generated in the inbox container.

    The pair has to be one the inbox's own ``pywebpush`` will sign with,
    so it is made with the library that will use it rather than with
    something this suite would have to grow a dependency on.

    :return: ``(public, private)`` base64url, or ``(None, None)``
    """
    snippet = (
        "import base64;"
        "from cryptography.hazmat.primitives.asymmetric import ec;"
        "from cryptography.hazmat.primitives import serialization;"
        "k=ec.generate_private_key(ec.SECP256R1());"
        "b=lambda r: base64.urlsafe_b64encode(r).rstrip(b'=').decode();"
        "print('{0}'+b(k.public_key().public_bytes("
        "serialization.Encoding.X962,"
        "serialization.PublicFormat.UncompressedPoint))+' '"
        "+b(k.private_numbers().private_value.to_bytes(32,'big')))".format(
            PUSH_MARKER))
    result = subprocess.run(
        _in_service(settings, settings.inbox_service, 'python', '-c', snippet),
        cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in result.stdout.decode('utf-8', 'replace').splitlines():
        if line.startswith(PUSH_MARKER):
            public, private = line[len(PUSH_MARKER):].split()
            return public, private
    print(result.stdout.decode('utf-8', 'replace')[-2000:])
    return None, None


def _vapid_lines(settings):
    """Return the compose file's VAPID lines, as ``{key: line}``.

    Only the ones inside the inbox service: another service could set a
    name of its own and must not be rewritten.
    """
    with open(_compose_path(settings), encoding='utf-8') as handle:
        lines = handle.read().split('\n')
    inside = False
    found = {}
    for index, line in enumerate(lines):
        if line.startswith('  ') and not line.startswith('   ') \
                and line.strip().endswith(':'):
            inside = line.strip() == '{0}:'.format(settings.inbox_service)
            continue
        if inside:
            for key in VAPID_KEYS:
                if line.strip().startswith('- {0}='.format(key)):
                    found[key] = index
    return lines, found


def _write_webpush_block(settings, public, private):
    """Put a VAPID key pair into the compose file, reversibly.

    The shipped file sets both keys to nothing, so rather than adding a
    second copy -- which would leave which one wins to the reader and to
    docker -- the lines themselves are replaced, and what they said is
    kept inside the block so ``disable`` can put it back exactly.

    :return: True when the file changed
    """
    lines, found = _vapid_lines(settings)
    if WEBPUSH_BLOCK_START in lines:
        return False
    missing = [key for key in VAPID_KEYS if key not in found]
    if missing:
        print('the {0} service in {1} sets no {2}; add it and try '
              'again'.format(settings.inbox_service, settings.compose_file,
                             ', '.join(missing)))
        return False

    at = min(found.values())
    was = [lines[found[key]] for key in VAPID_KEYS]
    for index in sorted(found.values(), reverse=True):
        del lines[index]
    block = [WEBPUSH_BLOCK_START]
    block += ['      # was:{0}'.format(line.rstrip()) for line in was]
    block += ['      - VAPID_PUBLIC_KEY={0}'.format(public),
              '      - VAPID_PRIVATE_KEY={0}'.format(private),
              WEBPUSH_BLOCK_END]
    lines[at:at] = block
    with open(_compose_path(settings), 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))
    return True


def _remove_webpush_block(settings):
    """Put the compose file's VAPID lines back as they were.

    :return: True when the file changed
    """
    with open(_compose_path(settings), encoding='utf-8') as handle:
        lines = handle.read().split('\n')
    if WEBPUSH_BLOCK_START not in lines:
        return False
    start = lines.index(WEBPUSH_BLOCK_START)
    end = lines.index(WEBPUSH_BLOCK_END)
    restored = [line.replace('      # was:', '', 1)
                for line in lines[start:end] if '# was:' in line]
    lines[start:end + 1] = restored
    with open(_compose_path(settings), 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))
    return True


def _recreate_inbox(settings):
    """Recreate the inbox container, so it reads the keys just written."""
    print('recreating {0}'.format(settings.inbox_service))
    subprocess.run(
        _compose(settings, 'up', '-d', settings.inbox_service),
        cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _copy_push_stub(settings):
    """Put the stub script into the inbox container."""
    with open(os.path.join(HERE, 'pushstub.py'), 'rb') as handle:
        script = handle.read()
    return _copy_into_container(settings, script, PUSH_STUB_IN_CONTAINER,
                                service=settings.inbox_service)


def _stop_push_stub(settings):
    """Stop the stub in the inbox container, if one is running there.

    The script stops itself: the inbox's image has neither ``pkill`` nor
    ``ps``, so it finds the serving process in ``/proc``.  It is copied
    in first, because stopping has to work even where nothing put it
    there in this session.
    """
    _copy_push_stub(settings)
    subprocess.run(
        _in_service(settings, settings.inbox_service, 'python',
                    PUSH_STUB_IN_CONTAINER, '--stop'),
        cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _start_push_stub(settings):
    """Copy the stub into the inbox container and start it there."""
    if not _copy_push_stub(settings):
        return False
    _stop_push_stub(settings)
    subprocess.run(
        _in_service(settings, settings.inbox_service, 'sh', '-c',
                    'cd /app && nohup python {0} {1} >/dev/null 2>&1 &'.format(
                        PUSH_STUB_IN_CONTAINER, PUSH_STUB_PORT)),
        cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return push_stub(settings, '/subscription') is not None


def push_stub(settings, path, payload=None):
    """Call the push stub inside the inbox container and return its answer.

    The stub listens on the loopback interface of the container the inbox
    sends from, which is the only place a subscription endpoint of its own
    can be reached; so a caller out here asks through docker, the way the
    DOI deposit log is read.

    :param path: the stub's endpoint, e.g. ``/received``
    :param payload: a body to POST, or None for a GET
    :return: what the stub answered, or None when it did not
    """
    if not settings.weko_repo:
        return None
    snippet = (
        "import json,urllib.request;"
        "d={0};"
        "r=urllib.request.Request('http://127.0.0.1:{1}{2}',"
        "data=None if d is None else json.dumps(d).encode(),"
        "headers={{'Content-Type':'application/json'}},"
        "method='GET' if d is None else 'POST');"
        "print('{3}'+json.dumps(json.load(urllib.request.urlopen(r,"
        "timeout=30))))".format(
            repr(payload), PUSH_STUB_PORT, path, PUSH_MARKER))
    result = subprocess.run(
        _in_service(settings, settings.inbox_service, 'python', '-c', snippet),
        cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in result.stdout.decode('utf-8', 'replace').splitlines():
        if line.startswith(PUSH_MARKER):
            return json.loads(line[len(PUSH_MARKER):])
    return None


def push_received(settings):
    """Return every Web Push the stand-in browser has been sent."""
    answer = push_stub(settings, '/received')
    return (answer or {}).get('received') or []


def push_subscribe(settings, target, language='en', displayname=None):
    """Subscribe the stand-in browser to Web Push for one user."""
    return push_stub(settings, '/subscribe', {
        'target': target, 'language': language,
        'displayname': displayname or 'WEKO E2E'})


def push_unsubscribe(settings):
    """Take the stand-in browser's subscription away again."""
    return push_stub(settings, '/unsubscribe', {})


def command_webpush_stub(args, settings, ledger):
    """Turn the stand-in Web Push browser on or off.

    The inbox sends a Web Push to whatever endpoint a subscription names,
    so a stand-in that holds keys of its own and decrypts what arrives is
    enough to exercise the whole path -- and the alternative, a real
    subscription, would mean a browser talking to Google's or Mozilla's
    push service, which a run against a local stack cannot do.

    The inbox also needs a VAPID key pair before it will send anything at
    all, and the shipped compose file leaves it empty; ``enable``
    generates one, writes it into the compose file between markers, and
    recreates the inbox so it is read.
    """
    action = args.action or 'status'
    if not settings.weko_repo:
        print('the web push stand-in needs the WEKO checkout that owns {0}; '
              'set WEKO_E2E_REPO to it'.format(settings.compose_file))
        return 1

    if action == 'status':
        print('settings in {0}: {1}'.format(
            settings.compose_file,
            'present' if WEBPUSH_BLOCK_START in
            open(_compose_path(settings), encoding='utf-8').read()
            else 'absent'))
        subscription = push_stub(settings, '/subscription')
        print('stand-in in the container: {0}'.format(
            'subscribed as {0}'.format(subscription['endpoint'])
            if subscription else 'not answering'))
        print('pushes received so far: {0}'.format(
            len(push_received(settings))))
        return 0

    if action == 'start':
        # The stub is an ordinary process in the container, so a restart
        # of that container takes it with it; this puts it back without
        # touching the configuration.
        if not _start_push_stub(settings):
            print('the stand-in did not answer in the container')
            return 1
        print('web push stand-in is listening on port {0}'.format(
            PUSH_STUB_PORT))
        return 0

    if action == 'stop':
        _stop_push_stub(settings)
        print('stopped the web push stand-in, leaving the keys alone')
        return 0

    if action == 'enable':
        public, private = _generate_vapid_keys(settings)
        if not public:
            print('could not generate a VAPID key pair in the {0} '
                  'container; is the stack up?'.format(settings.inbox_service))
            return 1
        if _write_webpush_block(settings, public, private):
            print('wrote a VAPID key pair into {0}'.format(
                _compose_path(settings)))
            _recreate_inbox(settings)
        else:
            print('the VAPID keys are already in {0}'.format(
                _compose_path(settings)))
        if not _start_push_stub(settings):
            print('the stand-in did not answer in the container')
            return 1
        print('the inbox signs with {0}...'.format(public[:16]))
        print('run the suite with: WEKO_E2E_SUITES=coarnotify '
              'python -m pytest')
        return 0

    if action == 'disable':
        _stop_push_stub(settings)
        if _remove_webpush_block(settings):
            print('took the VAPID keys back out of {0}'.format(
                _compose_path(settings)))
            _recreate_inbox(settings)
        else:
            print('the VAPID keys were not in {0}'.format(
                _compose_path(settings)))
        return 0

    print('unknown action {0!r}; use enable, disable, start, stop or '
          'status'.format(action))
    return 1


# -- the Crossref account --------------------------------------------------

def _crossref_block(settings):
    """Return the Crossref settings to write into the instance config."""
    lines = [
        CROSSREF_BLOCK_START,
        'WEKO_CROSSREF_ALLOW_REGISTER_DOI = True',
        "WEKO_CROSSREF_DEPOSIT_URL = {0!r}".format(
            settings.crossref_deposit_url),
        "WEKO_CROSSREF_SUBMISSION_LOG_URL = {0!r}".format(
            settings.crossref_submission_log_url),
        "WEKO_CROSSREF_LOGIN_ID = {0!r}".format(settings.crossref_login_id),
        "WEKO_CROSSREF_LOGIN_PASSWD = {0!r}".format(
            settings.crossref_login_passwd),
        "WEKO_CROSSREF_DEPOSITOR_NAME = {0!r}".format(
            settings.crossref_depositor_name),
        "WEKO_CROSSREF_DEPOSITOR_EMAIL = {0!r}".format(
            settings.crossref_depositor_email),
        "WEKO_CROSSREF_REGISTRANT = {0!r}".format(
            settings.crossref_registrant),
        CROSSREF_BLOCK_END,
        '',
    ]
    return '\n'.join(lines)


def command_crossref_account(args, settings, ledger):
    """Put the Crossref account into the instance configuration.

    WEKO has no admin screen for the deposit credentials -- they are
    instance settings -- so this writes them, between markers, into the
    file the container renders its configuration from, and takes them away
    again on ``disable``.  The deposit URL defaults to Crossref's test
    system, which is where a test run belongs.
    """
    action = args.action or 'status'
    if not settings.weko_repo:
        print('the Crossref account needs the WEKO checkout that owns {0}; '
              'set WEKO_E2E_REPO to it'.format(settings.compose_file))
        return 1

    if action == 'status':
        print('settings in {0}: {1}'.format(
            _instance_cfg(settings),
            'present' if _cfg_block_present(settings, CROSSREF_BLOCK_START)
            else 'absent'))
        print('deposit to: {0}'.format(settings.crossref_deposit_url))
        print('account: {0}'.format(
            settings.crossref_login_id or '(WEKO_E2E_CROSSREF_LOGIN_ID '
                                          'is not set)'))
        return 0

    if action == 'enable':
        missing = [name for name, value in (
            ('WEKO_E2E_CROSSREF_LOGIN_ID', settings.crossref_login_id),
            ('WEKO_E2E_CROSSREF_LOGIN_PASSWD',
             settings.crossref_login_passwd),
            ('WEKO_E2E_CROSSREF_DEPOSITOR_EMAIL',
             settings.crossref_depositor_email),
        ) if not value]
        if missing:
            print('set {0} first; Crossref refuses a deposit without '
                  'them'.format(', '.join(missing)))
            return 1
        _write_cfg_block(settings, CROSSREF_BLOCK_START, CROSSREF_BLOCK_END,
                         _crossref_block(settings), True)
        print('wrote the Crossref account into {0}'.format(
            _instance_cfg(settings)))
        _restart_weko(settings)
        print('deposits go to {0} as {1}'.format(
            settings.crossref_deposit_url, settings.crossref_login_id))
        print('run the suite with: WEKO_E2E_SUITES=crossref '
              'WEKO_E2E_CROSSREF_DEPOSIT=1 '
              'WEKO_E2E_CROSSREF_PREFIX=<your prefix> python -m pytest')
        return 0

    if action == 'disable':
        if _write_cfg_block(settings, CROSSREF_BLOCK_START,
                            CROSSREF_BLOCK_END, '', False):
            print('removed the Crossref account from {0}'.format(
                _instance_cfg(settings)))
            _restart_weko(settings)
        else:
            print('the Crossref account was not in {0}'.format(
                _instance_cfg(settings)))
        return 0

    print('unknown action {0!r}; use enable, disable or status'.format(
        action))
    return 1


def deposit_log(settings, doi):
    """Return the DOI deposit log rows of one DOI, newest first.

    WEKO keeps them in ``doi_deposit_log`` and offers no screen for it, so
    they are read from inside the container.

    :return: list of dicts, empty when there is no row or no container
    """
    snippet = (
        "import json;"
        "from weko_workflow.models import DoiDepositLog as L;"
        "rows=L.query.filter_by(doi={0!r}).order_by(L.id.desc()).all();"
        "print('{1}'+json.dumps([{{'id':r.id,'agency':r.agency,"
        "'status':r.deposit_status,'doi':r.doi,'attempt':r.attempt,"
        "'poll':r.poll_attempt,'http':r.http_status,"
        "'tracking_id':r.tracking_id,"
        "'error':r.error_message}} for r in rows]))".format(doi, LOG_MARKER))
    result = subprocess.run(
        _in_web(settings, 'invenio', 'shell', '-c', snippet),
        cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in result.stdout.decode('utf-8', 'replace').splitlines():
        if line.startswith(LOG_MARKER):
            return json.loads(line[len(LOG_MARKER):])
    return []


def command_doi_log(args, settings, ledger):
    """Print the DOI deposits WEKO has recorded."""
    if not settings.weko_repo:
        print('reading the deposit log needs the WEKO checkout; '
              'set WEKO_E2E_REPO to it')
        return 1
    result = subprocess.run(
        _in_web(settings, 'invenio', 'workflow', 'doi', 'list'),
        cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout.decode('utf-8', 'replace').strip())
    return result.returncode


# -- the ARK server --------------------------------------------------------

def _ark_account_block(settings):
    """Return the ARK settings to write into the instance configuration."""
    lines = [
        ARK_ACCOUNT_BLOCK_START,
        'WEKO_HANDLE_ALLOW_REGISTER_ARK = True',
        'WEKO_HANDLE_ARK_MINT_URL = {0!r}'.format(settings.ark_mint_url),
        'WEKO_HANDLE_ARK_NAAN = {0!r}'.format(settings.ark_naan),
        'WEKO_HANDLE_ARK_SHOULDER = {0!r}'.format(settings.ark_shoulder),
        'WEKO_HANDLE_ARK_TIMEOUT = {0!r}'.format(settings.ark_timeout),
    ]
    if settings.ark_api_key:
        lines += [
            'WEKO_HANDLE_ARK_API_KEY = {0!r}'.format(settings.ark_api_key),
            'WEKO_HANDLE_ARK_API_KEY_HEADER = {0!r}'.format(
                settings.ark_api_key_header),
            'WEKO_HANDLE_ARK_API_KEY_PREFIX = {0!r}'.format(
                settings.ark_api_key_prefix),
        ]
    else:
        lines += [
            'WEKO_HANDLE_ARK_LOGIN_URL = {0!r}'.format(
                settings.ark_login_url),
            'WEKO_HANDLE_ARK_LOGIN_USER = {0!r}'.format(
                settings.ark_login_user),
            'WEKO_HANDLE_ARK_LOGIN_PASSWD = {0!r}'.format(
                settings.ark_login_passwd),
        ]
    lines += [ARK_ACCOUNT_BLOCK_END, '']
    return '\n'.join(lines)


def _missing_ark_settings(settings):
    """Return the settings an ARK server needs and this run does not have.

    WEKO always needs the mint URL, the NAAN and the shoulder, and then
    either an API key or the three login settings -- the same rule
    ``is_ark_registration_allowed`` applies.
    """
    missing = [name for name, value in (
        ('WEKO_E2E_ARK_MINT_URL', settings.ark_mint_url),
        ('WEKO_E2E_ARK_NAAN', settings.ark_naan),
        ('WEKO_E2E_ARK_SHOULDER', settings.ark_shoulder),
    ) if not value]
    if not settings.ark_api_key:
        missing += [name for name, value in (
            ('WEKO_E2E_ARK_LOGIN_URL', settings.ark_login_url),
            ('WEKO_E2E_ARK_LOGIN_USER', settings.ark_login_user),
            ('WEKO_E2E_ARK_LOGIN_PASSWD', settings.ark_login_passwd),
        ) if not value]
    return missing


def command_ark_account(args, settings, ledger):
    """Point the instance at a real ARK server.

    WEKO has no admin screen for the ARK settings -- they are instance
    settings -- so this writes them between markers, the way
    ``crossref-account`` writes the Crossref account.  Use ``ark-stub``
    instead when there is no ARK server to talk to.
    """
    action = args.action or 'status'
    if not settings.weko_repo:
        print('the ARK settings need the WEKO checkout that owns {0}; '
              'set WEKO_E2E_REPO to it'.format(settings.compose_file))
        return 1

    if action == 'status':
        print('settings in {0}: {1}'.format(
            _instance_cfg(settings),
            'present' if _cfg_block_present(settings, ARK_ACCOUNT_BLOCK_START)
            else 'absent'))
        print('mint at: {0}'.format(
            settings.ark_mint_url or '(WEKO_E2E_ARK_MINT_URL is not set)'))
        print('as: {0}'.format(
            'API key' if settings.ark_api_key
            else 'login {0}'.format(settings.ark_login_user or '(not set)')))
        print('ark:/{0}/{1}'.format(settings.ark_naan or '?',
                                    settings.ark_shoulder or '?'))
        if _cfg_block_present(settings, ARK_BLOCK_START):
            print('note: the ARK stub settings are in the file as well; '
                  'run "ark-stub disable" so the two cannot disagree')
        return 0

    if action == 'enable':
        missing = _missing_ark_settings(settings)
        if missing:
            print('set {0} first; WEKO mints nothing without '
                  'them'.format(', '.join(missing)))
            return 1
        # The two ARK blocks set the same keys, so only one may be in the
        # file at a time.
        if _write_cfg_block(settings, ARK_BLOCK_START, ARK_BLOCK_END,
                            ARK_BLOCK, False):
            print('removed the ARK stub settings, which set the same keys')
            _stop_ark_stub(settings)
        _write_cfg_block(settings, ARK_ACCOUNT_BLOCK_START,
                         ARK_ACCOUNT_BLOCK_END,
                         _ark_account_block(settings), True)
        print('wrote the ARK settings into {0}'.format(
            _instance_cfg(settings)))
        _restart_weko(settings)
        print('minting at {0} under ark:/{1}/{2}'.format(
            settings.ark_mint_url, settings.ark_naan, settings.ark_shoulder))
        print('run the suite with: WEKO_E2E_SUITES=ark python -m pytest')
        return 0

    if action == 'disable':
        if _write_cfg_block(settings, ARK_ACCOUNT_BLOCK_START,
                            ARK_ACCOUNT_BLOCK_END, '', False):
            print('removed the ARK settings from {0}'.format(
                _instance_cfg(settings)))
            _restart_weko(settings)
        else:
            print('the ARK settings were not in {0}'.format(
                _instance_cfg(settings)))
        return 0

    print('unknown action {0!r}; use enable, disable or status'.format(
        action))
    return 1


# -- the ARK stub ----------------------------------------------------------

def _instance_cfg(settings):
    """Return the instance configuration file of the WEKO checkout."""
    return os.path.join(settings.weko_repo, 'scripts', 'instance.cfg')


def _cfg_block_present(settings, start):
    """Return whether a marked block is in the instance configuration."""
    path = _instance_cfg(settings)
    if not os.path.isfile(path):
        return False
    with open(path, encoding='utf-8') as handle:
        return start in handle.read()


def _write_cfg_block(settings, start, end, block, present):
    """Add or remove one marked block, and say whether anything moved.

    The block goes into the WEKO checkout's ``scripts/instance.cfg``: the
    file the container renders its ``invenio.cfg`` from on every start,
    and the place instance settings belong.  Writing it between markers is
    what lets the matching ``disable`` take exactly it away again.
    """
    path = _instance_cfg(settings)
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    had = start in text
    if had:
        head, _, rest = text.partition(start)
        _, _, tail = rest.partition(end)
        text = head + tail.lstrip('\n')
    if present:
        text = text.rstrip('\n') + '\n\n' + block
    if had == present:
        return False
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    return True


def _restart_weko(settings):
    """Restart the containers that read the instance configuration."""
    for service in (settings.web_service, 'worker'):
        print('restarting {0}'.format(service))
        subprocess.run(_compose(settings, 'restart', service),
                       cwd=settings.weko_repo,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    _wait_for_weko(settings)


def _wait_for_weko(settings, timeout=300):
    """Wait until the instance is serving again, and say whether it is.

    ``docker compose restart`` comes back when the container is running,
    which is a good while before WEKO answers; a suite started in that
    window fails on its first page for a reason that has nothing to do
    with what it was testing.  nginx answers throughout, so what is
    waited for is a login rather than a connection.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            WekoClient(settings).login()
            return True
        except (WekoError, requests.RequestException):
            time.sleep(5)
    print('{0} is still not answering after {1} s; "e2ectl ping" says '
          'more'.format(settings.base_url, timeout))
    return False


def _stop_ark_stub(settings):
    """Stop the stub in the container, if one is running there."""
    subprocess.run(
        _in_web(settings, 'sh', '-c',
                'pkill -f {0} || true'.format(ARK_STUB_IN_CONTAINER)),
        cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _start_ark_stub(settings):
    """Copy the stub into the container and start it there."""
    with open(os.path.join(HERE, 'arkstub.py'), 'rb') as handle:
        script = handle.read()
    if not _copy_into_container(settings, script, ARK_STUB_IN_CONTAINER):
        return False
    _stop_ark_stub(settings)
    subprocess.run(
        _in_web(settings, 'sh', '-c',
                'nohup python {0} {1} >/dev/null 2>&1 &'.format(
                    ARK_STUB_IN_CONTAINER, ARK_STUB_PORT)),
        cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return _ark_stub_answers(settings)


def _ark_stub_answers(settings):
    """Return whether the stub in the container answers a mint."""
    probe = (
        "import json,urllib.request;"
        "r=urllib.request.urlopen(urllib.request.Request("
        "'http://127.0.0.1:{0}/mint',"
        "data=json.dumps({{'naan':'x','shoulder':'y','url':'z'}})"
        ".encode(),headers={{'Content-Type':'application/json'}}),"
        "timeout=5);"
        "print(json.load(r)['data']['ark'])".format(ARK_STUB_PORT))
    result = subprocess.run(
        _in_web(settings, 'python', '-c', probe), cwd=settings.weko_repo,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.returncode == 0 and b'ark:/' in result.stdout


def command_ark_stub(args, settings, ledger):
    """Turn the stand-in ARK server in the web container on or off."""
    action = args.action or 'status'
    if not settings.weko_repo:
        print('the ARK stub needs the WEKO checkout that owns {0}; '
              'set WEKO_E2E_REPO to it'.format(settings.compose_file))
        return 1

    if action == 'status':
        print('settings in {0}: {1}'.format(
            _instance_cfg(settings),
            'present' if _cfg_block_present(settings, ARK_BLOCK_START)
            else 'absent'))
        print('stub in the container: {0}'.format(
            'answering' if _ark_stub_answers(settings) else 'not answering'))
        return 0

    if action == 'start':
        # The stub is an ordinary process in the container, so a restart
        # of that container takes it with it; this puts it back without
        # touching the configuration.
        if not _start_ark_stub(settings):
            print('the stub did not answer in the container')
            return 1
        print('ARK stub is answering on port {0}'.format(ARK_STUB_PORT))
        return 0

    if action == 'stop':
        _stop_ark_stub(settings)
        print('stopped the ARK stub, leaving the configuration alone')
        return 0

    if action == 'enable':
        # The two ARK blocks set the same keys, so only one may be in the
        # file at a time.
        if _write_cfg_block(settings, ARK_ACCOUNT_BLOCK_START,
                            ARK_ACCOUNT_BLOCK_END, '', False):
            print('removed the ARK server settings, which set the same keys')
        if _write_cfg_block(settings, ARK_BLOCK_START, ARK_BLOCK_END,
                            ARK_BLOCK, True):
            print('added the ARK stub settings to {0}'.format(
                _instance_cfg(settings)))
            _restart_weko(settings)
        else:
            print('the ARK settings are already in {0}'.format(
                _instance_cfg(settings)))
        if not _start_ark_stub(settings):
            print('the stub did not answer in the container')
            return 1
        print('ARK stub is minting ark:/{0}/{1}... on port {2}'.format(
            ARK_STUB_NAAN, ARK_STUB_SHOULDER, ARK_STUB_PORT))
        print('run the suite with: WEKO_E2E_SUITES=ark '
              'WEKO_E2E_ARK_NAAN={0} python -m pytest'.format(ARK_STUB_NAAN))
        return 0

    if action == 'disable':
        _stop_ark_stub(settings)
        if _write_cfg_block(settings, ARK_BLOCK_START, ARK_BLOCK_END,
                            ARK_BLOCK, False):
            print('removed the ARK settings from {0}'.format(
                _instance_cfg(settings)))
            _restart_weko(settings)
        else:
            print('the ARK settings were not in {0}'.format(
                _instance_cfg(settings)))
        return 0

    print('unknown action {0!r}; use enable, disable, start, stop or '
          'status'.format(action))
    return 1


COMMANDS = {
    'ark-account': command_ark_account,
    'ark-stub': command_ark_stub,
    'crossref-account': command_crossref_account,
    'doi-log': command_doi_log,
    'env': command_env,
    'inbox': command_inbox,
    'status': command_status,
    'webpush-stub': command_webpush_stub,
    'ping': command_ping,
    'clean': command_clean,
}


def build_parser():
    """Return the argument parser for the tool."""
    parser = argparse.ArgumentParser(
        prog='e2ectl', description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=sorted(COMMANDS),
                        help='what to do')
    parser.add_argument('action', nargs='?',
                        help='for ark-account, ark-stub and '
                             'crossref-account: enable, disable or status; '
                             'ark-stub also takes start and stop')
    parser.add_argument('--run', help='act on one run id only')
    parser.add_argument('--discover', action='store_true',
                        help='also act on resources named after the label, '
                             'whether or not the ledger knows them')
    parser.add_argument('--hard', action='store_true',
                        help='also remove the rows WEKO only marks deleted, '
                             'by running the purge inside the web container')
    parser.add_argument('--dry-run', action='store_true',
                        help='say what would be deleted, delete nothing')
    parser.add_argument('--keep-ledger', action='store_true',
                        help='leave the ledger as it is')
    return parser


def main(argv=None):
    """Run the tool."""
    args = build_parser().parse_args(argv)
    settings = Settings()
    ledger = Ledger(settings.state_path)
    try:
        return COMMANDS[args.command](args, settings, ledger)
    except WekoError as error:
        print('error: {0}'.format(error), file=sys.stderr)
        return 1
    except requests.RequestException as error:
        print('error: {0} is not answering ({1})'.format(
            settings.base_url, error.__class__.__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
