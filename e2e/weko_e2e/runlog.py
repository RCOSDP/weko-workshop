"""The record of a run, as the run itself leaves it behind.

``evidence/README.md`` is written by hand, after a run somebody chose to
keep; this is the part of it a run can write for itself -- what ran, what
came of each step, what each step photographed and what it created -- so
that a run made somewhere else comes back with its own record rather than
with a console log to piece one together from.

Nothing here talks to pytest or to the instance: ``conftest.py`` gathers
the facts as the run goes, and this turns them into Markdown.
"""

import platform
import subprocess

MARKS = {'passed': 'passed', 'skipped': 'skipped', 'failed': '**FAILED**',
         'error': '**ERROR**'}
"""How each outcome is spelled in the record."""


class Step(object):
    """One test, as the record tells it."""

    def __init__(self, nodeid, module, name, doc, suite):
        """Describe a test before it has run."""
        self.nodeid = nodeid
        self.module = module
        self.name = name
        self.doc = doc
        self.suite = suite
        self.outcome = None
        self.reason = None
        self.duration = 0.0
        self.images = []

    @property
    def summary(self):
        """Return the first line of the test's docstring, or nothing."""
        return (self.doc or '').strip().split('\n')[0].strip()

    def report(self, when, outcome, duration, reason=None):
        """Take in one phase of the test -- setup, call or teardown.

        The worst phase is the outcome: a setup that fails is an error, a
        setup that skips is a skip, and a teardown that fails spoils a
        call that passed.
        """
        self.duration += duration or 0.0
        if outcome == 'failed':
            outcome = 'failed' if when == 'call' else 'error'
        if outcome == 'passed' and self.outcome:
            return
        if self.outcome in ('failed', 'error'):
            return
        self.outcome = outcome
        if reason:
            self.reason = reason


def versions():
    """Return ``[(what, version)]`` of what the run ran on."""
    found = [('python', platform.python_version()),
             ('platform', platform.platform(terse=True))]
    for name in ('pytest', 'playwright', 'requests'):
        try:
            from importlib.metadata import version
            found.append((name, version(name)))
        except Exception:  # a version is never what fails a record
            found.append((name, 'unknown'))
    return found


def revision(directory):
    """Return the git revision of a directory, or None outside git."""
    try:
        result = subprocess.run(
            ['git', 'describe', '--always', '--dirty'], cwd=directory,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        return None
    if result.returncode:
        return None
    return result.stdout.decode('utf-8', 'replace').strip() or None


def _cell(text):
    """Return text fit for one cell of a Markdown table."""
    return ' '.join(str(text).split()).replace('|', r'\|')


def _counts(steps):
    """Return ``passed, 2 skipped``-style counts, in pytest's order."""
    tally = {}
    for step in steps:
        tally[step.outcome or 'not run'] = \
            tally.get(step.outcome or 'not run', 0) + 1
    order = ('failed', 'error', 'passed', 'skipped', 'not run')
    return ', '.join('{0} {1}'.format(tally[key], key)
                     for key in order if key in tally) or 'nothing ran'


def as_markdown(steps, settings, suites, started, finished, created,
                cleaned=None, doctor=True, environment=(), stopped=None):
    """Return the record of a run.

    :param steps: the :class:`Step` of every collected test, in run order
    :param suites: the optional suites the run was asked for
    :param created: ``[(suite, kind, id, name)]`` the run wrote to the
        ledger, in the order it did
    :param cleaned: None when the run left its resources behind, or the
        cleaning it did at the end -- ``'clean'`` or ``'clean --hard'``
    :param doctor: whether the run looked the instance over first
    :param environment: ``[(what, value)]`` to say what the run ran on
    :param stopped: why the run ended before any test ran, if it did.
        Written down rather than left out, because the record of the
        run before it would otherwise be what somebody sent on.
    """
    elapsed = (finished - started).total_seconds()
    lines = [
        '# The run',
        '',
        'Written by the run itself when it finished, the way `doctor.md`',
        'and the screenshots are: re-running rewrites it, so it says what',
        'this run did rather than what somebody remembered.',
        '`README.md` beside it is the hand-written account of a run that',
        'was chosen to be kept.',
        '',
        '| | |',
        '| --- | --- |',
        '| Started | {0} |'.format(started.isoformat(timespec='seconds')),
        '| Finished | {0} ({1:.0f} s) |'.format(
            finished.isoformat(timespec='seconds'), elapsed),
        '| Instance | {0} |'.format(settings.base_url),
        '| Account | {0} |'.format(settings.email),
        '| Run id | `{0}` |'.format(settings.run_id),
        '| Suites | {0} |'.format(', '.join(('base',) + tuple(suites))),
        '| Result | **{0}** |'.format(_counts(steps)),
        '| Instance check | {0} |'.format(
            '[`doctor.md`](doctor.md)' if doctor
            else 'skipped (`--no-doctor`)'),
        '| Left behind | {0} |'.format(
            'removed at the end (`./e2ectl {0} --run {1}`)'.format(
                cleaned, settings.run_id) if cleaned
            else 'yes; `./e2ectl clean --run {0}` removes it'.format(
                settings.run_id) if created else 'nothing'),
        '',
    ]

    if environment:
        lines += ['## What it ran on', '', '| | |', '| --- | --- |']
        lines += ['| {0} | {1} |'.format(_cell(what), _cell(value))
                  for what, value in environment]
        lines.append('')

    if stopped:
        lines += ['## Nothing ran', '', stopped, '']
        return '\n'.join(lines)

    lines += ['## Steps', '',
              '| Suite | Step | Outcome | Time | What it checks |',
              '| --- | --- | --- | --- | --- |']
    for step in steps:
        lines.append('| {0} | `{1}` | {2} | {3:.1f} s | {4} |'.format(
            step.suite or 'base', step.name,
            MARKS.get(step.outcome, 'not run'), step.duration,
            _cell(step.summary)))
    lines.append('')

    troubled = [step for step in steps
                if step.outcome in ('failed', 'error')]
    if troubled:
        lines += ['## What went wrong', '']
        for step in troubled:
            lines += ['### `{0}`'.format(step.nodeid), '', '```',
                      (step.reason or '(no message)').strip(), '```', '']

    skipped = {}
    for step in steps:
        if step.outcome == 'skipped':
            skipped.setdefault((step.suite or 'base', step.reason), []) \
                .append(step.name)
    if skipped:
        lines += ['## Skipped, and why', '',
                  '| Suite | Steps | Why |', '| --- | --- | --- |']
        for (suite, reason), names in skipped.items():
            lines.append('| {0} | {1} | {2} |'.format(
                suite, len(names), _cell(reason or '')))
        lines.append('')

    lines += ['## What it created', '']
    if created:
        lines += ['| Suite | Kind | Id | Name |', '| --- | --- | --- | --- |']
        lines += ['| {0} | {1} | `{2}` | {3} |'.format(
            suite or 'base', kind, identifier, _cell(name or ''))
            for suite, kind, identifier, name in created]
    else:
        lines.append('Nothing.')
    lines.append('')

    photographed = [step for step in steps if step.images]
    if photographed:
        lines += ['## Screenshots', '']
        for step in photographed:
            lines += ['### {0} `{1}` -- {2}'.format(
                step.suite or 'base', step.name,
                MARKS.get(step.outcome, 'not run')), '']
            if step.summary:
                lines += [step.summary, '']
            for image in step.images:
                lines += ['![{0}]({1})'.format(
                    image.rsplit('/', 1)[-1][:-len('.png')], image), '']
    return '\n'.join(lines)
