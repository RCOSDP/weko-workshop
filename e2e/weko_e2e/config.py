"""Settings the test suite and the ``e2ectl`` tool both read.

Everything a run needs to know about the environment comes from here, so
the same suite can be pointed at a local docker stack, at a staging server
behind a real host name, or at a colleague's instance, without editing
code: set the environment variables, or put them in an environment file.

An environment file is ``KEY=value`` lines, ``#`` for comments; the suite
reads the one named by ``WEKO_E2E_ENV``, or ``e2e/e2e.env`` when that
exists.  Variables already set in the environment win over the file, so a
one-off override on the command line still works::

    WEKO_E2E_ENV=environments/staging.env \
        WEKO_TEST_EMAIL=someone@example.org python -m pytest

``e2ectl env`` prints what a run would actually use.
"""

import os
from datetime import datetime

DEFAULTS = {
    'WEKO_BASE_URL': 'https://localhost',
    'WEKO_E2E_HOST_IP': '',
    'WEKO_HOST_MAP': '',
    'WEKO_E2E_VERIFY_TLS': '',
    'WEKO_TEST_EMAIL': 'wekosoftware@nii.ac.jp',
    'WEKO_TEST_PASSWORD': 'uspass123',
    'WEKO_E2E_LABEL': 'E2E',
    'WEKO_E2E_ITEM_TYPE': 'デフォルトアイテムタイプ（フル）',
    'WEKO_E2E_COMPOSE_FILE': 'docker-compose2.yml',
    'WEKO_E2E_WEB_SERVICE': 'web',
    'WEKO_E2E_CONTAINER_REPO': '/code',
    'WEKO_E2E_TIMEOUT': '60000',
    'WEKO_E2E_STEP_TIMEOUT': '300',
    'WEKO_E2E_UPLOAD_TIMEOUT': '180',
    'WEKO_E2E_SEARCH_TIMEOUT': '180',
    'WEKO_E2E_SUITES': '',
    'WEKO_E2E_APPROVER_EMAIL': 'repoadmin@example.org',
    'WEKO_E2E_APPROVER_PASSWORD': 'uspass123',
    'WEKO_E2E_NOTIFY_TIMEOUT': '120',
    'WEKO_E2E_INBOX_SERVICE': 'inbox',
    'WEKO_E2E_CROSSREF_PREFIX': '10.5555',
    'WEKO_E2E_CROSSREF_DEPOSIT': '',
    'WEKO_E2E_CROSSREF_LOGIN_ID': '',
    'WEKO_E2E_CROSSREF_LOGIN_PASSWD': '',
    'WEKO_E2E_CROSSREF_DEPOSITOR_NAME': 'WEKO E2E',
    'WEKO_E2E_CROSSREF_DEPOSITOR_EMAIL': '',
    'WEKO_E2E_CROSSREF_REGISTRANT': 'WEKO E2E',
    'WEKO_E2E_CROSSREF_DEPOSIT_URL':
        'https://test.crossref.org/servlet/deposit',
    'WEKO_E2E_CROSSREF_SUBMISSION_LOG_URL':
        'https://test.crossref.org/servlet/submissionDownload',
    'WEKO_E2E_CROSSREF_DEPOSIT_TIMEOUT': '600',
    'WEKO_E2E_ARK_NAAN': '',
    'WEKO_E2E_ARK_SHOULDER': '',
    'WEKO_E2E_ARK_MINT_URL': '',
    'WEKO_E2E_ARK_LOGIN_URL': '',
    'WEKO_E2E_ARK_LOGIN_USER': '',
    'WEKO_E2E_ARK_LOGIN_PASSWD': '',
    'WEKO_E2E_ARK_API_KEY': '',
    'WEKO_E2E_ARK_API_KEY_HEADER': 'Authorization',
    'WEKO_E2E_ARK_API_KEY_PREFIX': 'Bearer ',
    'WEKO_E2E_ARK_TIMEOUT': '30',
    'WEKO_HEADED': '',
}
"""Environment variables the suite reads, with the value used when unset."""

TRUE = ('1', 'true', 'yes', 'on')
FALSE = ('', '0', 'false', 'no', 'off')
"""What counts as "yes" and "no" in a variable that switches something."""

HERE = os.path.dirname(os.path.abspath(__file__))
E2E_DIR = os.path.abspath(os.path.join(HERE, os.pardir))
WORKSHOP_DIR = os.path.abspath(os.path.join(E2E_DIR, os.pardir))

WEKO_REPO_NAMES = ('wekov2', 'weko3', 'weko')
"""Names a WEKO checkout next to this repository is likely to have."""


def find_weko_repo(compose_file):
    """Return the WEKO checkout whose containers are under test, or None.

    This suite lives in its own repository, so the WEKO checkout that owns
    the compose file -- the one ``e2ectl clean --hard`` has to run
    ``docker compose`` in -- has to be found rather than assumed.  Set
    ``WEKO_E2E_REPO`` when it is somewhere these guesses do not reach.

    :param compose_file: compose file name that marks the checkout
    :return: absolute path of the checkout, or None when there is none
    """
    named = os.environ.get('WEKO_E2E_REPO')
    if named:
        return os.path.abspath(os.path.expanduser(named))

    candidates = [os.getcwd(), WORKSHOP_DIR]
    beside = os.path.abspath(os.path.join(WORKSHOP_DIR, os.pardir))
    candidates += [os.path.join(beside, name) for name in WEKO_REPO_NAMES]
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, compose_file)):
            return os.path.abspath(candidate)
    return None


def read_env_file(path):
    """Return the ``KEY=value`` pairs of an environment file.

    :param path: file to read; a missing file is not an error
    :return: dict of the pairs, empty when there is no file
    """
    values = {}
    if not path or not os.path.isfile(path):
        return values
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            value = value.strip()
            if len(value) > 1 and value[0] == value[-1] and value[0] in '"\'':
                value = value[1:-1]
            values[key.strip()] = value
    return values


def env_file_path():
    """Return the environment file a run reads, or None.

    ``WEKO_E2E_ENV`` names one -- relative paths are resolved against the
    suite, so ``environments/staging.env`` works from anywhere -- and
    ``e2e/e2e.env`` is read when it exists and nothing was named.
    """
    named = os.environ.get('WEKO_E2E_ENV')
    if named:
        if os.path.isabs(named):
            return named
        for base in (os.getcwd(), E2E_DIR):
            candidate = os.path.join(base, named)
            if os.path.isfile(candidate):
                return candidate
        return os.path.join(E2E_DIR, named)
    default = os.path.join(E2E_DIR, 'e2e.env')
    return default if os.path.isfile(default) else None


FILE_VALUES = read_env_file(env_file_path())
"""What the environment file said, read once."""


def _env(name):
    """Return a setting: the environment, then the file, then the default.

    The environment wins over the file so that one variable can be
    overridden for a single run without editing the file.
    """
    for value in (os.environ.get(name), FILE_VALUES.get(name)):
        if value is not None and value != '':
            return value
    return DEFAULTS[name]


OPTIONAL_SUITES = ('ark', 'coarnotify', 'crossref')
"""Optional suites, each of which has to be asked for by name.

The base flow always runs.  These do not, because each needs something of
the instance that not every instance has -- an ARK server, a Crossref
prefix, an LDN inbox and a second account -- so running them where that
is missing would only produce failures nobody asked for.
"""


def parse_suites(value):
    """Return the optional suites a setting asks for.

    :param value: comma or space separated names, or ``all``
    :return: tuple of names, in the order :data:`OPTIONAL_SUITES` lists them
    :raise ValueError: when a name is not one of :data:`OPTIONAL_SUITES`
    """
    asked = [name.strip().lower()
             for name in value.replace(',', ' ').split() if name.strip()]
    if 'all' in asked:
        return OPTIONAL_SUITES
    unknown = [name for name in asked if name not in OPTIONAL_SUITES]
    if unknown:
        raise ValueError(
            'unknown suite(s): {0}; known: {1}, or all'.format(
                ', '.join(unknown), ', '.join(OPTIONAL_SUITES)))
    return tuple(name for name in OPTIONAL_SUITES if name in asked)


def _flag(name):
    """Return whether a setting that switches something on is set.

    Anything but an explicit "no" counts as yes, so ``WEKO_HEADED=1`` and
    ``WEKO_HEADED=please`` both mean the same thing and nobody has to
    remember which words are accepted.
    """
    value = _env(name).strip().lower()
    return value in TRUE or value not in FALSE


class Settings(object):
    """What a run needs to know about the instance it is testing.

    The resource names are all derived from ``label`` and ``run_id``, so
    every artefact a run leaves behind carries the same recognisable prefix
    and ``e2ectl clean --discover`` can find them without the ledger.
    """

    def __init__(self, run_id=None):
        """Read the settings from the environment.

        :param run_id: identifier shared by every resource of one run;
            defaults to ``$WEKO_E2E_RUN_ID`` or the current time
        """
        self.env_file = env_file_path()
        self.base_url = _env('WEKO_BASE_URL').rstrip('/')
        self.host_ip = _env('WEKO_E2E_HOST_IP')
        self.verify_tls = _flag('WEKO_E2E_VERIFY_TLS')
        self.email = _env('WEKO_TEST_EMAIL')
        self.password = _env('WEKO_TEST_PASSWORD')
        self.label = _env('WEKO_E2E_LABEL')
        self.item_type_name = _env('WEKO_E2E_ITEM_TYPE')
        self.compose_file = _env('WEKO_E2E_COMPOSE_FILE')
        self.web_service = _env('WEKO_E2E_WEB_SERVICE')
        self.timeout = int(_env('WEKO_E2E_TIMEOUT'))
        self.step_timeout = int(_env('WEKO_E2E_STEP_TIMEOUT'))
        self.upload_timeout = int(_env('WEKO_E2E_UPLOAD_TIMEOUT'))
        self.search_timeout = int(_env('WEKO_E2E_SEARCH_TIMEOUT'))
        self.headed = _flag('WEKO_HEADED')
        self.run_id = run_id or os.environ.get('WEKO_E2E_RUN_ID') \
            or FILE_VALUES.get('WEKO_E2E_RUN_ID') \
            or datetime.now().strftime('%Y%m%d-%H%M%S')
        self.state_path = os.environ.get(
            'WEKO_E2E_STATE',
            FILE_VALUES.get('WEKO_E2E_STATE',
                            os.path.join(E2E_DIR, '.e2e-state.json')))
        self.container_repo = _env('WEKO_E2E_CONTAINER_REPO')
        self.weko_repo = find_weko_repo(self.compose_file)
        self.suites = parse_suites(_env('WEKO_E2E_SUITES'))
        self.approver_email = _env('WEKO_E2E_APPROVER_EMAIL')
        self.approver_password = _env('WEKO_E2E_APPROVER_PASSWORD')
        self.notify_timeout = int(_env('WEKO_E2E_NOTIFY_TIMEOUT'))
        self.inbox_service = _env('WEKO_E2E_INBOX_SERVICE')
        self.crossref_prefix = _env('WEKO_E2E_CROSSREF_PREFIX')
        self.crossref_deposit = _flag('WEKO_E2E_CROSSREF_DEPOSIT')
        self.crossref_login_id = _env('WEKO_E2E_CROSSREF_LOGIN_ID')
        self.crossref_login_passwd = _env('WEKO_E2E_CROSSREF_LOGIN_PASSWD')
        self.crossref_depositor_name = _env('WEKO_E2E_CROSSREF_DEPOSITOR_NAME')
        self.crossref_depositor_email = _env(
            'WEKO_E2E_CROSSREF_DEPOSITOR_EMAIL')
        self.crossref_registrant = _env('WEKO_E2E_CROSSREF_REGISTRANT')
        self.crossref_deposit_url = _env('WEKO_E2E_CROSSREF_DEPOSIT_URL')
        self.crossref_submission_log_url = _env(
            'WEKO_E2E_CROSSREF_SUBMISSION_LOG_URL')
        self.crossref_deposit_timeout = int(
            _env('WEKO_E2E_CROSSREF_DEPOSIT_TIMEOUT'))
        self.ark_naan = _env('WEKO_E2E_ARK_NAAN')
        self.ark_shoulder = _env('WEKO_E2E_ARK_SHOULDER')
        self.ark_mint_url = _env('WEKO_E2E_ARK_MINT_URL')
        self.ark_login_url = _env('WEKO_E2E_ARK_LOGIN_URL')
        self.ark_login_user = _env('WEKO_E2E_ARK_LOGIN_USER')
        self.ark_login_passwd = _env('WEKO_E2E_ARK_LOGIN_PASSWD')
        self.ark_api_key = _env('WEKO_E2E_ARK_API_KEY')
        self.ark_api_key_header = _env('WEKO_E2E_ARK_API_KEY_HEADER')
        self.ark_api_key_prefix = os.environ.get(
            'WEKO_E2E_ARK_API_KEY_PREFIX',
            FILE_VALUES.get('WEKO_E2E_ARK_API_KEY_PREFIX',
                            DEFAULTS['WEKO_E2E_ARK_API_KEY_PREFIX']))
        self.ark_timeout = int(_env('WEKO_E2E_ARK_TIMEOUT'))

    @property
    def host(self):
        """Return the host name of the instance under test."""
        from urllib.parse import urlparse

        return urlparse(self.base_url).hostname or ''

    @property
    def host_map(self):
        """Return the chromium host resolver rule, or an empty string.

        WEKO builds absolute URLs from the Host header, so a run against a
        host name that DNS does not know still has to *browse* that name.
        ``WEKO_E2E_HOST_IP`` is the short way to say so -- the rule is
        built from it -- and ``WEKO_HOST_MAP`` is there for a rule that
        needs to say something else.
        """
        rule = _env('WEKO_HOST_MAP')
        if rule:
            return rule
        if self.host_ip and self.host:
            return 'MAP {0} {1}'.format(self.host, self.host_ip)
        return ''

    def scoped(self, scope):
        """Return these settings with resource names of their own.

        Two suites in one session share a run id, and would then ask WEKO
        for two indexes, flows and workflows of the same name -- which it
        refuses.  A scope keeps their names apart while leaving the run,
        and so the ledger, one thing.

        :param scope: short name of the suite, or None for the base names
        """
        if not scope:
            return self
        copy = self._copy()
        copy.run_id = '{0}-{1}'.format(self.run_id, scope)
        return copy

    def as_account(self, email, password):
        """Return these settings with somebody else's credentials.

        The ``coarnotify`` suite needs two accounts at once -- one
        registers, the other approves and is the one the approval request
        is sent to -- and everything else about the instance is the same
        for both.

        :param email: the account to log in as
        :param password: its password
        """
        copy = self._copy()
        copy.email = email
        copy.password = password
        return copy

    def _copy(self):
        """Return a shallow copy of these settings."""
        copy = Settings.__new__(Settings)
        copy.__dict__.update(self.__dict__)
        return copy

    @property
    def index_name(self):
        """Return the name of the index the run registers its item in."""
        return '{0} Index {1}'.format(self.label, self.run_id)

    @property
    def flow_name(self):
        """Return the name of the flow the run defines."""
        return '{0} Flow {1}'.format(self.label, self.run_id)

    @property
    def workflow_name(self):
        """Return the name of the workflow the run defines."""
        return '{0} Workflow {1}'.format(self.label, self.run_id)

    @property
    def item_title(self):
        """Return the title of the item the run registers."""
        return '{0} item {1}'.format(self.label, self.run_id)

    def url(self, path):
        """Return an absolute URL for a path on the instance under test."""
        return '{0}/{1}'.format(self.base_url, path.lstrip('/'))

    def describe(self):
        """Return what a run would use, as ``(name, value)`` pairs.

        This is what ``e2ectl env`` prints: the point of it is that an
        environment that does not work can be compared with one that does
        without reading the code.
        """
        return [
            ('environment file', self.env_file or '(none)'),
            ('base URL', self.base_url),
            ('host', self.host),
            ('host resolver rule', self.host_map or '(DNS)'),
            ('verify TLS', 'yes' if self.verify_tls else 'no'),
            ('account', self.email),
            ('approver account', self.approver_email),
            ('item type', self.item_type_name),
            ('label', self.label),
            ('optional suites', ', '.join(self.suites) or
             '(none; set WEKO_E2E_SUITES)'),
            ('crossref prefix', self.crossref_prefix),
            ('crossref deposit', self._describe_deposit()),
            ('ark server', self._describe_ark()),
            ('notification wait', '{0} s'.format(self.notify_timeout)),
            ('run id', self.run_id),
            ('ledger', self.state_path),
            ('action timeout', '{0} ms'.format(self.timeout)),
            ('step timeout', '{0} s'.format(self.step_timeout)),
            ('upload timeout', '{0} s'.format(self.upload_timeout)),
            ('search timeout', '{0} s'.format(self.search_timeout)),
            ('WEKO checkout', self.weko_repo or '(not found)'),
            ('compose file', self.compose_file),
            ('web service', self.web_service),
            ('inbox service', self.inbox_service),
            ('repository in container', self.container_repo),
        ]

    def _describe_ark(self):
        """Return what the ARK suite would be minting against."""
        if not self.ark_mint_url:
            return ('(none; "e2ectl ark-stub enable" for a stand-in, or set '
                    'WEKO_E2E_ARK_MINT_URL)')
        how = 'API key' if self.ark_api_key else 'login {0}'.format(
            self.ark_login_user or '(not set)')
        return '{0} with {1}'.format(self.ark_mint_url, how)

    def _describe_deposit(self):
        """Return what the Crossref suite will do about depositing."""
        if not self.crossref_deposit:
            return 'no (grant only; set WEKO_E2E_CROSSREF_DEPOSIT to send)'
        if not self.crossref_login_id:
            return 'asked for, but WEKO_E2E_CROSSREF_LOGIN_ID is not set'
        return '{0} as {1}'.format(self.crossref_deposit_url,
                                   self.crossref_login_id)

    def __repr__(self):
        """Return a one line summary, for the tool's status output."""
        return 'Settings(base_url={0!r}, run_id={1!r}, label={2!r})'.format(
            self.base_url, self.run_id, self.label)
