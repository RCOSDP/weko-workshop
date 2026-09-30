"""Is this instance in a state the suite can be run against?

The suites assume an instance ``install.sh`` has just finished setting
up: the accounts it creates, the item types and the flow actions it
loads, a root index, somewhere for files to go, and a log partition for
the month.  When one of those is missing the failure usually lands
somewhere unhelpful -- an item registration that stops at Next, a login
screen that comes back, a search that finds nothing -- so this says which
one it is, before a run wastes a minute finding out.

Nothing here talks to the instance: :mod:`weko_e2e.cli` gathers the
facts, over HTTP and by running :mod:`weko_e2e.inspect` in the ``web``
container, and this turns them into findings.  A finding that can be
repaired names its repair, and the tool holds the repairs -- they need
the containers, and this file is only judgement.

**What is already there wins.** A repair fills in what is missing and
never replaces what is not: an instance with a file location of its own
keeps it, and the shipped item types, flow, index and identifier
settings are added a row at a time rather than by running the files that
would drop the tables first -- see :mod:`weko_e2e.dataload`.
"""

OK = 'ok'
WARN = 'warn'
FAIL = 'fail'
"""What a check can conclude.

``warn`` is for what only some runs need -- the optional suites, the
baseline being tidy -- and does not fail the tool.
"""

WEKO_REPO_NAMES = ('wekov2', 'weko3', 'weko')
"""Names a WEKO checkout beside this repository is looked for under."""

BASELINE = {'indexes': 1, 'flows': 1, 'workflows': 2, 'activities': 0,
            'records': 0, 'buckets': 0, 'pids': 0, 'identifiers': 1}
"""What ``install.sh`` leaves behind, for saying how far off this is."""


class Finding(object):
    """One thing that was looked at, and how it turned out."""

    def __init__(self, status, name, detail, fix=None, suite=None):
        """Record one check.

        :param status: :data:`OK`, :data:`WARN` or :data:`FAIL`
        :param name: what was looked at, as a phrase
        :param detail: what was found, and what to do about it
        :param fix: name of the repair that would put it right, if any
        :param suite: the optional suite this matters to, or None for
            anything the base flow needs as well
        """
        self.status = status
        self.name = name
        self.detail = detail
        self.fix = fix
        self.suite = suite

    def __repr__(self):
        """Return a one line form, for a test or a traceback."""
        return 'Finding({0}, {1!r})'.format(self.status, self.name)


class Survey(object):
    """What was found out about the instance, before judging any of it."""

    def __init__(self, settings):
        """Start an empty survey of one instance."""
        self.settings = settings
        self.reachable = False
        self.login_error = None
        self.approver_login_error = None
        self.admin_error = None
        self.search_error = None
        self.leftovers = {}
        self.inbox = None
        self.worker = None
        self.report = None
        self.report_error = None

    @property
    def counts(self):
        """Return what the instance holds, or an empty dict."""
        return (self.report or {}).get('counts') or {}

    @property
    def accounts(self):
        """Return ``{email: [role, ...]}``, or an empty dict."""
        return (self.report or {}).get('accounts') or {}

    def config(self, name, default=None):
        """Return one instance setting as the application sees it."""
        return ((self.report or {}).get('settings') or {}).get(name, default)


# -- the checks ------------------------------------------------------------
#
# Each takes the survey and returns one Finding.  They run in this order,
# and the first failure that makes the rest meaningless says so itself.

def check_reachable(survey):
    """The instance answers at all."""
    if survey.reachable:
        return Finding(OK, 'the instance answers', survey.settings.base_url)
    return Finding(
        FAIL, 'the instance answers',
        '{0} does not answer. For a local stack, "docker compose -f {1} ps"; '
        'for a host name DNS does not know, set WEKO_E2E_HOST_IP.'.format(
            survey.settings.base_url, survey.settings.compose_file))


def check_checkout(survey):
    """The WEKO checkout that owns the containers was found.

    Half of what there is to look at -- roles, partitions, what the
    running application believes its configuration is -- is only
    reachable by running something in a container, and that means
    knowing which checkout owns the compose file.
    """
    if survey.report:
        return Finding(OK, 'the WEKO checkout', survey.settings.weko_repo)
    if survey.settings.weko_repo:
        return Finding(
            WARN, 'the WEKO checkout',
            '{0} was found, but it could not be inspected ({1}). Is the '
            'stack up?'.format(survey.settings.weko_repo,
                               survey.report_error or 'no answer'))
    return Finding(
        WARN, 'the WEKO checkout',
        'not found, so the checks that run inside a container were not '
        'asked. It is found automatically when it sits next to this '
        'repository and is named {0}; otherwise set WEKO_E2E_REPO to the '
        'one that holds {1}.'.format(
            ', '.join(WEKO_REPO_NAMES), survey.settings.compose_file))


def check_login(survey):
    """The account the run works as can log in."""
    if not survey.login_error:
        return Finding(OK, 'the account logs in', survey.settings.email)
    return Finding(
        FAIL, 'the account logs in',
        '{0} was refused ({1}). WEKO_TEST_EMAIL and WEKO_TEST_PASSWORD say '
        'who to be.'.format(survey.settings.email, survey.login_error),
        fix='account')


def check_admin(survey):
    """That account can reach the screens the run sets up through."""
    if survey.login_error:
        return Finding(WARN, 'the account administers',
                       'not asked, because the login was refused')
    if not survey.admin_error:
        return Finding(OK, 'the account administers',
                       'the admin screens answer')
    return Finding(
        FAIL, 'the account administers',
        '{0} cannot reach the admin screens ({1}). The run creates an '
        'index, a flow and a workflow, so it has to be an '
        'administrator.'.format(survey.settings.email, survey.admin_error),
        fix='account')


def check_item_type(survey):
    """The item type the run registers on is loaded."""
    report = survey.report
    if not report:
        return Finding(WARN, 'the item type under test',
                       'not asked; the instance could not be inspected')
    wanted = survey.settings.item_type_name
    types = report.get('item_types') or []
    if wanted in types:
        return Finding(OK, 'the item type under test', wanted)
    if not types:
        return Finding(
            FAIL, 'the item type under test',
            'this instance has no item types at all',
            fix='item-types')
    return Finding(
        FAIL, 'the item type under test',
        'there is no {0!r}; this instance has {1} of its own ({2}...). '
        'Either set WEKO_E2E_ITEM_TYPE to one of them, or add the shipped '
        'ones -- which leaves these alone, because only the rows are '
        'added and never the file that would drop the tables.'.format(
            wanted, len(types), ', '.join(sorted(types)[:3])),
        fix='item-types')


def check_actions(survey):
    """The flow actions the suite builds its flow out of exist."""
    from .client import DEFAULT_FLOW_ACTIONS

    report = survey.report
    if not report:
        return Finding(WARN, 'the workflow actions',
                       'not asked; the instance could not be inspected')
    missing = [name for name in DEFAULT_FLOW_ACTIONS
               if name not in (report.get('actions') or [])]
    if not missing:
        return Finding(OK, 'the workflow actions',
                       '{0} of them, the six the suite uses '
                       'included'.format(len(report['actions'])))
    return Finding(
        FAIL, 'the workflow actions',
        'missing: {0}. Without them no flow can be defined.'.format(
            ', '.join(missing)),
        fix='actions')


def check_flow(survey):
    """There is a flow to read the action ids and versions off."""
    report = survey.report
    if not report:
        return Finding(WARN, 'a flow to copy from',
                       'not asked; the instance could not be inspected')
    flows = report.get('flows') or []
    if flows:
        return Finding(OK, 'a flow to copy from',
                       '{0} flow(s), starting with {1!r}'.format(
                           len(flows), flows[0]))
    return Finding(
        FAIL, 'a flow to copy from',
        'this instance has no flow at all; the shipped Registration Flow '
        'is what the screens list the actions on',
        fix='flow')


def check_index_tree(survey):
    """There is an index for the run to hang its own index under."""
    report = survey.report
    if not report:
        return Finding(WARN, 'the index tree',
                       'not asked; the instance could not be inspected')
    if survey.counts.get('indexes'):
        return Finding(OK, 'the index tree',
                       '{0} index(es)'.format(survey.counts['indexes']))
    return Finding(
        FAIL, 'the index tree',
        'the index tree is empty; a run creates its own index but the '
        'screens want a tree to put it in',
        fix='index-tree')


def check_identifier_settings(survey):
    """The identifier settings row the crossref suite edits exists."""
    report = survey.report
    if not report:
        return Finding(WARN, 'the identifier settings',
                       'not asked; the instance could not be inspected',
                       suite='crossref')
    if survey.counts.get('identifiers'):
        return Finding(OK, 'the identifier settings',
                       '{0} row(s) under /admin/identifier/'.format(
                           survey.counts['identifiers']),
                       suite='crossref')
    return Finding(
        WARN, 'the identifier settings',
        'there is no row under /admin/identifier/, so the crossref suite '
        'has nothing to turn the grant on in',
        fix='identifier-settings', suite='crossref')


def check_location(survey):
    """Files have somewhere to be written.

    Whatever an instance already has is what it keeps: a repository with
    a location of its own is not a broken one, and the run uploads a file
    wherever that location points.
    """
    report = survey.report
    if not report:
        return Finding(WARN, 'somewhere to put files',
                       'not asked; the instance could not be inspected')
    locations = report.get('locations') or []
    if locations:
        return Finding(OK, 'somewhere to put files',
                       ', '.join(locations) + ' (left as it is)')
    return Finding(
        FAIL, 'somewhere to put files',
        'no file location is set, so the file the run attaches has nowhere '
        'to go and Item Registration fails',
        fix='location')


def check_partition(survey):
    """This month has a partition for the activity log to be written to."""
    report = survey.report
    if not report:
        return Finding(WARN, "this month's log partition",
                       'not asked; the instance could not be inspected')
    found = report.get('partitions')
    if found is None:
        return Finding(OK, "this month's log partition",
                       'user_activity_logs is not partitioned here')
    wanted = 'user_activity_logs_{0}'.format(report.get('today'))
    if wanted in found:
        return Finding(OK, "this month's log partition", wanted)
    return Finding(
        FAIL, "this month's log partition",
        'there is no {0}. WEKO writes a log row for most requests, so '
        'without it the file upload answers 500 and item registration '
        'stops at Next.'.format(wanted),
        fix='partition')


def check_language(survey):
    """At least one language is registered.

    The index tree is cached per registered language, and the tool's own
    hard purge rebuilds those caches; an instance with none of them
    leaves a deleted index on screen.
    """
    report = survey.report
    if not report:
        return Finding(WARN, 'a registered language',
                       'not asked; the instance could not be inspected')
    languages = report.get('languages') or []
    if languages:
        return Finding(OK, 'a registered language', ', '.join(languages))
    return Finding(
        WARN, 'a registered language',
        'no language is registered, so the index tree has no cache to '
        'rebuild after a hard clean',
        fix='language')


def check_search(survey):
    """Search answers, which is what the last step of the base flow needs."""
    if survey.login_error:
        return Finding(WARN, 'search answers',
                       'not asked, because the login was refused')
    if not survey.search_error:
        return Finding(OK, 'search answers', 'Elasticsearch is reachable')
    return Finding(
        FAIL, 'search answers',
        'the search API said {0}. The last step of the base flow waits for '
        'the item to be indexed, and will time out.'.format(
            survey.search_error))


def check_worker(survey):
    """The worker is running, because indexing is its job."""
    if survey.worker is None:
        return Finding(WARN, 'the worker is running',
                       'not asked; there is no WEKO checkout to ask docker '
                       'through')
    if survey.worker:
        return Finding(OK, 'the worker is running', 'up')
    return Finding(
        WARN, 'the worker is running',
        'the worker container is not up, so nothing will be indexed and '
        'the last step of the base flow will time out')


def check_approver(survey):
    """The second account the coarnotify suite needs can log in."""
    if not survey.approver_login_error:
        return Finding(OK, 'the approver logs in',
                       survey.settings.approver_email, suite='coarnotify')
    return Finding(
        WARN, 'the approver logs in',
        '{0} was refused ({1}). The coarnotify suite has it approve, so '
        'that the announcement has somebody to go to.'.format(
            survey.settings.approver_email, survey.approver_login_error),
        fix='approver', suite='coarnotify')


def check_approver_role(survey):
    """The approver holds the role approval requests are sent to."""
    report = survey.report
    if not report:
        return Finding(WARN, 'the approver holds the role',
                       'not asked; the instance could not be inspected',
                       suite='coarnotify')
    wanted = survey.config('WEKO_ADMIN_PERMISSION_ROLE_REPO',
                           'Repository Administrator')
    email = survey.settings.approver_email
    held = survey.accounts.get(email)
    if held is None:
        return Finding(
            WARN, 'the approver holds the role',
            'there is no account {0}'.format(email),
            fix='approver', suite='coarnotify')
    if wanted in held:
        return Finding(OK, 'the approver holds the role',
                       '{0} is a {1}'.format(email, wanted),
                       suite='coarnotify')
    return Finding(
        WARN, 'the approver holds the role',
        '{0} holds {1}, not {2!r} -- which is who WEKO sends approval '
        'requests to, so nothing would reach them'.format(
            email, ', '.join(held) or 'no role', wanted),
        fix='approver-role', suite='coarnotify')


def check_inbox(survey):
    """The instance announces an LDN inbox for the coarnotify suite."""
    if survey.login_error:
        return Finding(WARN, 'the site announces an inbox',
                       'not asked, because the login was refused',
                       suite='coarnotify')
    if survey.inbox:
        return Finding(OK, 'the site announces an inbox', survey.inbox,
                       suite='coarnotify')
    return Finding(
        WARN, 'the site announces an inbox',
        'the top page carries no ldp#inbox link. WEKO adds it when '
        'WEKO_NOTIFICATIONS is on, which here is {0}.'.format(
            survey.config('WEKO_NOTIFICATIONS', 'unknown')),
        suite='coarnotify')


def check_leftovers(survey):
    """Nothing from an earlier run is still lying about."""
    total = sum(len(found) for found in survey.leftovers.values())
    if survey.login_error:
        return Finding(WARN, 'nothing left from an earlier run',
                       'not asked, because the login was refused')
    if not total:
        return Finding(OK, 'nothing left from an earlier run',
                       'nothing is named {0}*'.format(survey.settings.label))
    counted = ', '.join(
        '{0} {1}'.format(len(found), kind)
        for kind, found in sorted(survey.leftovers.items()) if found)
    return Finding(
        WARN, 'nothing left from an earlier run',
        '{0} left behind ({1}). A run does not collide with them -- every '
        'name carries its own run id -- but they are somebody\'s '
        'leftovers.'.format(counted, survey.settings.label),
        fix='leftovers')


def check_baseline(survey):
    """How far the instance is from what ``install.sh`` leaves behind."""
    if not survey.report:
        return Finding(WARN, 'the instance is at its baseline',
                       'not asked; the instance could not be inspected')
    over = {name: survey.counts.get(name, 0) - wanted
            for name, wanted in BASELINE.items()
            if survey.counts.get(name, 0) > wanted}
    if not over:
        return Finding(OK, 'the instance is at its baseline',
                       'exactly what install.sh leaves')
    return Finding(
        WARN, 'the instance is at its baseline',
        'above it by {0}. That is normal for a repository in use, and for '
        'a run that was cleaned with "clean" rather than "clean '
        '--hard".'.format(', '.join(
            '{0} {1}'.format(count, name)
            for name, count in sorted(over.items()))))


CHECKS = (
    check_reachable,
    check_checkout,
    check_login,
    check_admin,
    check_item_type,
    check_actions,
    check_flow,
    check_index_tree,
    check_location,
    check_partition,
    check_language,
    check_search,
    check_worker,
    check_identifier_settings,
    check_approver,
    check_approver_role,
    check_inbox,
    check_leftovers,
    check_baseline,
)
"""Every check, in the order they are reported in."""


def evaluate(survey):
    """Return what every check made of the survey.

    An instance that does not answer is not asked the rest: every other
    check would only repeat that one.
    """
    findings = [check_reachable(survey)]
    if findings[0].status == FAIL:
        return findings
    return findings + [check(survey) for check in CHECKS[1:]]


MARKDOWN_MARKS = {OK: 'ok', WARN: 'warn', FAIL: '**FAIL**'}
"""How each status is spelled in the report a run writes."""


def as_markdown(findings, settings, suites=(), when=None):
    """Return the report of a look, as a run leaves it behind.

    Written by the run rather than by hand, the way the screenshots are,
    so that what the evidence says about the instance is what the run
    actually found rather than what somebody remembered.

    :param suites: the optional suites the run was asked for
    :param when: when the look happened, defaulting to now
    """
    from datetime import datetime

    troubled = [finding for finding in findings if finding.status != OK]
    lines = [
        '# What the instance looked like before the run',
        '',
        'Written by the run itself, before its first test: every `pytest`',
        'looks the instance over and stops rather than spending a run on',
        'one that cannot pass.  Re-running rewrites this file, so it',
        'cannot drift from what was actually found.',
        '',
        '| | |',
        '| --- | --- |',
        '| Looked at | {0} |'.format(
            (when or datetime.now()).isoformat(timespec='seconds')),
        '| Instance | {0} |'.format(settings.base_url),
        '| Run id | `{0}` |'.format(settings.run_id),
        '| Suites | {0} |'.format(', '.join(('base',) + tuple(suites))),
        '| Result | {0} of {1} checks passed |'.format(
            len(findings) - len(troubled), len(findings)),
        '',
        '| | Check | What was found |',
        '| --- | --- | --- |',
    ]
    for finding in findings:
        lines.append('| {0} | {1}{2} | {3} |'.format(
            MARKDOWN_MARKS[finding.status], finding.name,
            ' `[{0}]`'.format(finding.suite) if finding.suite else '',
            finding.detail.replace('|', r'\|')))
    lines += ['', _closing(troubled), '']
    return '\n'.join(lines)


def _closing(troubled):
    """Return the line that says what the look came to."""
    if not troubled:
        return ('Everything the suites depend on was there, so the run went '
                'ahead.')
    failed = [finding for finding in troubled if finding.status == FAIL]
    if not failed:
        return ('Nothing the run itself depends on was missing, so it went '
                'ahead; the warnings are what the other suites want, or '
                'what an earlier run left behind.')
    return ('The run stopped here: {0}. `./e2ectl doctor --fix` is what '
            'puts right the ones that can be.'.format(
                '; '.join(finding.name for finding in failed)))


def worst(findings):
    """Return the worst status among findings, or :data:`OK` for none."""
    for status in (FAIL, WARN):
        if any(finding.status == status for finding in findings):
            return status
    return OK
