"""Fixtures shared by the e2e suites.

Everything here is session scoped on purpose.  A WEKO activity is locked to
the session that opened it, so a flow split across browser contexts locks
itself out; and the index, flow and workflow a run sets up are the ones
every step of that run then works with.

The run leaves its resources behind when it finishes, so that a failure can
be looked at in the browser; ``./e2ectl clean`` -- or ``--clean-after`` --
is what removes them.
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from weko_e2e import doctor, runlog, ui  # noqa: E402
from weko_e2e.client import WekoClient, anonymous_session  # noqa: E402
from weko_e2e.config import (E2E_DIR, OPTIONAL_SUITES,  # noqa: E402
                             Settings, parse_suites)
from weko_e2e.ledger import Ledger  # noqa: E402

DOCTOR_REPORT = os.path.join(E2E_DIR, 'evidence', 'doctor.md')
"""Where the look at the instance is written down.

Left behind by the run the way the screenshots are, so that what the
evidence says about the instance is what the run found rather than what
somebody remembered.
"""

EVIDENCE = os.path.join(E2E_DIR, 'evidence')
"""Where the report of a run and its screenshots are written.

The run's own record is ``evidence/run.md`` (see :data:`RUN_REPORT`); the
hand-written report of a kept run is ``evidence/README.md``.  The base
flow's screenshots are ``evidence/images/``; each optional suite has a
folder of its own beside them, so that a suite's report and the
screenshots it is written from travel together.
"""

RUN_REPORT = os.path.join(EVIDENCE, 'run.md')
"""Where the run writes down what it did, when it finishes.

Beside ``doctor.md``, and left behind the same way: a run made on
somebody else's machine comes back with its own record.
"""

_RUN = {'started': None, 'doctor': False, 'cleaned': None, 'current': None,
        'steps': [], 'created': []}
"""What the run's record is gathered into as the run goes."""


def pytest_addoption(parser):
    """Add the options that pick the suites and the cleanup."""
    group = parser.getgroup('weko-e2e')
    group.addoption(
        '--suite', action='append', default=[], metavar='NAME',
        help='run this optional suite as well ({0}, or all); repeatable, '
             'and the same thing as WEKO_E2E_SUITES'.format(
                 ', '.join(OPTIONAL_SUITES)))
    group.addoption(
        '--no-doctor', action='store_true', default=False,
        help='do not look the instance over before running')
    group.addoption(
        '--doctor-fix', action='store_true', default=False,
        help='put right what can be put right before running, as '
             '"e2ectl doctor --fix" would')
    group.addoption(
        '--doctor-fix-accounts', action='store_true', default=False,
        help='with --doctor-fix, also create accounts and give them the '
             'roles the suites need')
    group.addoption(
        '--clean-after', action='store_true', default=False,
        help='delete what the run created when it finishes, pass or fail')
    group.addoption(
        '--clean-hard', action='store_true', default=False,
        help='with --clean-after, also remove the rows WEKO only hides')


def pytest_sessionstart(session):
    """Look the instance over before a run is spent on it.

    A missing piece of what ``install.sh`` sets up shows itself as a
    failure somewhere unhelpful -- a file upload that answers 500, a
    search that finds nothing -- a minute or more into a run.  Asking
    first costs a few seconds and says which piece it is.

    A run stops only on a failure: a warning is something one of the
    optional suites wants, or somebody's leftovers, and neither is this
    run's business.  ``--no-doctor`` skips the whole thing.
    """
    config = session.config
    _RUN['started'] = datetime.now()
    if config.option.collectonly:
        return
    # Whatever else happens, the record of the *previous* run must not be
    # what somebody sends on as this one's.
    try:
        os.remove(RUN_REPORT)
    except OSError:
        pass
    if config.getoption('--no-doctor'):
        return
    _RUN['doctor'] = True

    from weko_e2e.cli import look_over, put_right

    settings = settings_for()
    book = Ledger(settings.state_path)
    try:
        survey, findings = look_over(settings, book)
    except Exception as error:  # looking is never what fails a run
        print('\ncould not look the instance over ({0}); carrying on. '
              'Run "./e2ectl doctor" to see why.'.format(error))
        return

    wanted = enabled_suites(config)
    findings = [f for f in findings if not f.suite or f.suite in wanted]
    if config.getoption('--doctor-fix'):
        repairable = [f for f in findings if f.fix and f.status != doctor.OK]
        if repairable:
            print('\nrepairing before the run:')
            put_right(findings, settings, survey,
                      config.getoption('--doctor-fix-accounts'))
            survey, findings = look_over(settings, book)
            findings = [f for f in findings
                        if not f.suite or f.suite in wanted]

    _report(findings, settings)
    _write_doctor_report(findings, settings, wanted)
    failed = [f for f in findings if f.status == doctor.FAIL]
    if failed:
        # pytest skips pytest_sessionfinish when a session is exited from
        # pytest_sessionstart, so the record of a run that got no further
        # than this has to be written here.
        _write_run_report(config, stopped=(
            'The run never started: the look at the instance found {0} '
            'wanting, and stopped rather than produce failures that are '
            'not about the tests. [`doctor.md`](doctor.md) is what it '
            'found.'.format('; '.join(
                '`{0}`'.format(f.name) for f in failed))))
        pytest.exit(
            'this instance is not in a state to be tested: {0}. Put it '
            'right with "./e2ectl doctor --fix", or run with --no-doctor '
            'to go ahead anyway.'.format(
                '; '.join(f.name for f in failed)),
            returncode=pytest.ExitCode.USAGE_ERROR)


def _write_doctor_report(findings, settings, suites):
    """Leave the look behind under ``evidence``, for the record.

    A run that stops here writes it too -- that is the run worth having
    a record of.
    """
    try:
        directory = os.path.dirname(DOCTOR_REPORT)
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(DOCTOR_REPORT, 'w', encoding='utf-8') as handle:
            handle.write(doctor.as_markdown(findings, settings, suites))
    except OSError as error:
        print('could not write {0}: {1}'.format(DOCTOR_REPORT, error))


def _report(findings, settings):
    """Print what the checks made of the instance, shortest way round."""
    troubled = [f for f in findings if f.status != doctor.OK]
    print('\n{0}: {1} of {2} checks passed'.format(
        settings.base_url, len(findings) - len(troubled), len(findings)))
    for finding in troubled:
        print('  {0}  {1}\n      {2}'.format(
            'FAIL' if finding.status == doctor.FAIL else 'warn',
            finding.name, finding.detail))


def pytest_configure(config):
    """Declare the marker the optional suites carry."""
    config.addinivalue_line(
        'markers',
        'suite(name): part of an optional suite, run only when that suite '
        'is asked for by --suite or WEKO_E2E_SUITES')


_SETTINGS = None
"""The settings the whole session shares.

Read once: a run id that is a timestamp would otherwise differ between
the look at the instance and the run it belongs to, and the report of
the one would name the other.
"""


def settings_for():
    """Return the settings this session works with."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings()
    return _SETTINGS


def enabled_suites(config):
    """Return the optional suites this run was asked for.

    ``--suite`` adds to what the environment asked for rather than
    replacing it, so a file that turns a suite on and a command line that
    turns another on both take effect.
    """
    asked = set(settings_for().suites)
    asked.update(parse_suites(' '.join(config.getoption('--suite'))))
    return tuple(name for name in OPTIONAL_SUITES if name in asked)


def pytest_collection_modifyitems(config, items):
    """Skip the optional suites nobody asked for.

    They are skipped rather than deselected so that a run says out loud
    what it did not do, and how to ask for it.
    """
    wanted = enabled_suites(config)
    _RUN['steps'] = [runlog.Step(
        item.nodeid, item.module.__name__, item.name,
        getattr(item.obj, '__doc__', None), _suite_of(item.module))
        for item in items]
    for item in items:
        marker = item.get_closest_marker('suite')
        if not marker or not marker.args:
            continue
        name = marker.args[0]
        if name not in wanted:
            item.add_marker(pytest.mark.skip(
                reason='optional suite {0!r} not enabled; '
                       'run with --suite {0} or WEKO_E2E_SUITES={0}'.format(
                           name)))


def _step(nodeid):
    """Return the record of one test, or None for one never collected."""
    for step in _RUN['steps']:
        if step.nodeid == nodeid:
            return step
    return None


def pytest_runtest_logstart(nodeid, location):
    """Note which test is running, for the screenshots and the ledger."""
    _RUN['current'] = _step(nodeid)


def pytest_runtest_logreport(report):
    """Take each phase of a test into the run's record."""
    step = _step(report.nodeid)
    if step is None:
        return
    reason = None
    if report.skipped and isinstance(report.longrepr, tuple):
        reason = report.longrepr[2]
        if reason.startswith('Skipped: '):
            reason = reason[len('Skipped: '):]
    elif report.failed:
        crash = getattr(report.longrepr, 'reprcrash', None)
        reason = crash.message if crash else report.longreprtext
    step.report(report.when, report.outcome, report.duration, reason)


def pytest_sessionfinish(session, exitstatus):
    """Write down what the run did, under ``evidence``."""
    config = session.config
    if config.option.collectonly:
        return
    _write_run_report(config, stopped=None if _RUN['steps'] else (
        'No test ran: nothing matched what was asked for.'))


def _write_run_report(config, stopped=None):
    """Write the run's own record under ``evidence``.

    :param stopped: why the run ended before any test ran, if it did.
        Written down rather than left out, because an evidence folder
        that somebody sends on should say what happened to *this* run.
    """
    settings = settings_for()
    environment = [('suite', runlog.revision(os.path.dirname(
        os.path.abspath(__file__))) or 'not a git checkout')]
    if settings.weko_repo:
        environment.append(('WEKO', '{0} {1}'.format(
            settings.weko_repo,
            runlog.revision(settings.weko_repo) or '')))
    environment += runlog.versions()
    try:
        if not os.path.isdir(EVIDENCE):
            os.makedirs(EVIDENCE)
        with open(RUN_REPORT, 'w', encoding='utf-8') as handle:
            handle.write(runlog.as_markdown(
                _RUN['steps'], settings, enabled_suites(config),
                _RUN['started'] or datetime.now(), datetime.now(),
                _RUN['created'], cleaned=_RUN['cleaned'],
                doctor=_RUN['doctor'], environment=environment,
                stopped=stopped))
        print('\nrecord of the run: {0}'.format(RUN_REPORT))
    except OSError as error:
        print('could not write {0}: {1}'.format(RUN_REPORT, error))


_FAILED = {}
"""The first step of each flow module that failed, keyed by module."""


def pytest_runtest_makereport(item, call):
    """Remember the first step of a flow that failed.

    A step that skips itself has not failed, and the flow goes on: an
    optional part of one -- a Crossref deposit nobody has an account
    for, a web push nothing is listening for -- says so and gets out of
    the way of the steps that do not depend on it.
    """
    if call.when != 'call' or call.excinfo is None:
        return
    if call.excinfo.errisinstance(pytest.skip.Exception):
        return
    _FAILED.setdefault(item.module.__name__, item.name)


def pytest_runtest_setup(item):
    """Skip the rest of a flow once one of its steps has failed.

    The tests of one module are a single flow cut into steps, so once a
    step fails the ones after it cannot say anything useful; reporting
    them as skipped rather than failed keeps the one real failure visible.
    """
    failed = _FAILED.get(item.module.__name__)
    if failed:
        pytest.skip('the flow stopped at {0}'.format(failed))


@pytest.fixture(scope='session')
def base_settings():
    """Return the settings this run works with.

    What the whole session shares: the instance, the account, the ledger.
    A test wants :func:`settings` instead, which adds names of its own.
    """
    return settings_for()


def _suite_of(module):
    """Return the optional suite a test module belongs to, or None.

    ``pytestmark`` is one mark or a list of them, depending on how the
    module spelled it.
    """
    marks = getattr(module, 'pytestmark', None) or []
    if not isinstance(marks, (list, tuple)):
        marks = [marks]
    for mark in marks:
        if getattr(mark, 'name', None) == 'suite' and mark.args:
            return mark.args[0]
    return None


@pytest.fixture(scope='module')
def settings(base_settings, request):
    """Return the settings this module works with.

    The same settings, with resource names that belong to this module
    alone, so that several suites can run in one session without asking
    WEKO for two flows of the same name.
    """
    return base_settings.scoped(_suite_of(request.module))


@pytest.fixture(scope='session')
def ledger(base_settings):
    """Return the ledger, with this run opened in it."""
    book = Ledger(base_settings.state_path)
    book.start_run(base_settings.run_id, base_settings.base_url,
                   base_settings.label)
    print('\nrun {0} against {1}; ledger {2}'.format(
        base_settings.run_id, base_settings.base_url, book.path))
    return book


@pytest.fixture(scope='session')
def record(ledger, base_settings):
    """Return a function recording one created resource in the ledger.

    Every step calls this as soon as WEKO has created something, so that a
    run which fails half way is still cleanable.

    :return: ``record(kind, identifier, name=None)``
    """
    def note(kind, identifier, name=None):
        """Write one resource to the ledger and return its identifier."""
        ledger.add(base_settings.run_id, kind, identifier, name)
        step = _RUN['current']
        _RUN['created'].append((step.suite if step else None, kind,
                                str(identifier), name))
        return identifier

    return note


@pytest.fixture(scope='session')
def client(base_settings):
    """Return a logged in HTTP client, for setup and for verification."""
    return WekoClient(base_settings).login()


@pytest.fixture(scope='session')
def visitor(base_settings):
    """Return a session that has not logged in."""
    return anonymous_session(base_settings)


@pytest.fixture(scope='session')
def browser(base_settings):
    """Return the one browser the whole run shares."""
    from playwright.sync_api import sync_playwright

    args = ['--host-resolver-rules={0}'.format(base_settings.host_map)] \
        if base_settings.host_map else []
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            headless=not base_settings.headed, args=args)
        yield instance
        instance.close()


@pytest.fixture(scope='session')
def page(browser, base_settings):
    """Return the one page every step of the run shares."""
    page = ui.new_page(browser, base_settings)
    yield page
    page.context.close()


@pytest.fixture(scope='session')
def visitor_page(browser, base_settings):
    """Return a page in a context that has never logged in.

    Used to show what the item looks like to the public, which is the
    whole point of the last steps; it has to be a separate context,
    because the run's own page is logged in as an administrator.
    """
    page = ui.new_page(browser, base_settings)
    yield page
    page.context.close()


@pytest.fixture(scope='module')
def shot(request):
    """Return a function that writes a numbered screenshot.

    The screenshots are the evidence of a run: every step leaves one
    behind, named so that re-running replaces it in place and the report
    never drifts from the run.

    A module writes into the folder its own report is written from -- the
    base flow into ``evidence/images``, an optional suite into
    ``evidence/<suite>/images`` -- so a step names only itself and two
    suites cannot overwrite each other's evidence.

    :return: ``shot(page, name)``, writing
        ``e2e/evidence/[<suite>/]images/<name>.png``
    """
    suite = _suite_of(request.module)
    directory = os.path.join(EVIDENCE, suite, 'images') if suite \
        else os.path.join(EVIDENCE, 'images')
    if not os.path.isdir(directory):
        os.makedirs(directory)

    def take(page, name, full_page=True):
        """Write one screenshot and return its path."""
        path = os.path.join(directory, '{0}.png'.format(name))
        page.wait_for_timeout(500)
        page.screenshot(path=path, full_page=full_page)
        print('screenshot: {0}'.format(path))
        step = _RUN['current']
        if step is not None:
            image = os.path.relpath(path, EVIDENCE).replace(os.sep, '/')
            if image not in step.images:
                step.images.append(image)
        return path

    return take


@pytest.fixture(scope='session')
def flow_state():
    """Return the dict the steps of one flow hand each other values in.

    The steps are a single flow cut into tests, so what one learns -- the
    index id, the activity id, the record id -- the next ones need.
    """
    return {}


@pytest.fixture(scope='session', autouse=True)
def cleanup(request, base_settings):
    """Clean the run up at the end, when the run was asked to.

    The tool does the deleting, so that what a test run cleans and what
    ``./e2ectl clean`` cleans cannot drift apart.
    """
    yield
    if not request.config.getoption('--clean-after'):
        print('\nleft behind for inspection; remove with: '
              './e2ectl clean --run {0}'.format(base_settings.run_id))
        return
    from weko_e2e.cli import main

    argv = ['clean', '--run', base_settings.run_id]
    if request.config.getoption('--clean-hard'):
        argv.append('--hard')
    _RUN['cleaned'] = ' '.join(argv[:1] + argv[3:])
    print('\ncleaning up run {0}'.format(base_settings.run_id))
    main(argv)
