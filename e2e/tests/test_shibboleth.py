"""Optional suite: a Shibboleth user logs in, and gets the right account.

Not part of the base flow, because Shibboleth login is off on a stock
instance and because it has to be driven from where the Service Provider
drives it.  Ask for it by name::

    WEKO_E2E_SUITES=shibboleth python -m pytest
    python -m pytest --suite shibboleth

WEKO is not what speaks SAML.  The SP does, in nginx, and what reaches
WEKO is an ordinary POST of the attributes the IdP released --
``nginx/login.py`` is the script that makes it.  So this suite needs no
IdP: :mod:`weko_e2e.shibstub` is copied into the **nginx** container and
sends what that script sends, from where it sends it.  That last part
matters.  ``release_v2.1.0`` closes ``POST /weko/shib/login`` to
everything but the addresses in ``WEKO_ACCOUNTS_SHIB_SP_ALLOWED_ADDRS``,
and standing in the right place is how this suite stays on the right side
of that check -- **nothing here widens it**, because an instance that
takes those attributes from anywhere is an instance anyone can log into
as anyone.

What the suite is really asking is where the attributes end up:

    eppn   -> shibboleth_user.shib_eppn, the binding
    mail   -> accounts_user.email, the account itself

The second is the one worth a test.  WEKO makes the account's email out
of ``mail``, not out of ``eppn``, so an IdP that releases one and not the
other -- or releases a ``mail`` that is not the address the repository
knows the person by -- gives them an account under a name nobody expects.
This suite sends an ``eppn`` and a ``mail`` that are deliberately
different, and says which one it finds.

**Nothing that was already on the instance is touched.**  The
confirmation screen offers two ways through: bind to an existing WEKO
account, which *overwrites that account's email* with the one the IdP
released, and make a new account.  This takes the new-account way, and
removes what it made at the end.  The Shibboleth switch is put back to
what it was.
"""

import pytest

from weko_e2e import ui
from weko_e2e.cli import forget_shib_account, shib_account, shib_login
from weko_e2e.client import (SHIB_CONFIRM_PATH, WHOAMI_PATH,  # noqa: I100
                             WekoClient, anonymous_session)
from weko_e2e.config import SHIBBOLETH

pytestmark = pytest.mark.suite('shibboleth')


@pytest.fixture(scope='module')
def shibboleth(client, settings):
    """Turn Shibboleth login on for this suite, and put it back after.

    The switch is a row in ``admin_settings`` that the screen writes, so
    turning it on is the same thing an administrator does; what it was
    before is read first and written back at the end, whatever the suite
    did in between.

    The account the run logs in as is removed on the way out too, so an
    instance is left holding neither the account nor the binding.

    Skipped whole where nothing can be run in the containers.  Every
    step needs the stand-in, and the stand-in has to be copied into the
    ``nginx`` container -- so skipping here skips the suite, rather than
    letting the steps after the first fail one by one for a reason that
    has nothing to do with Shibboleth.
    """
    if not settings.can_exec:
        pytest.skip(
            'the Shibboleth stand-in runs in the {0} container, and '
            'nothing here can run a command in it: set WEKO_E2E_REPO to '
            'the WEKO checkout that owns the compose file, or '
            'WEKO_E2E_EXEC to a command that reaches the containers '
            '(Kubernetes and the like)'.format(settings.nginx_service))
    was = client.shib_login_enabled()
    client.shib_login_enabled(True)
    yield was
    for line in forget_shib_account(settings):
        print(line)
    client.shib_login_enabled(was)


@pytest.fixture(scope='module')
def shib_page(browser, settings):
    """Return a browsing context of this suite's own.

    The run's shared page is logged in as the administrator and other
    suites go on using it; this one ends up logged in as somebody else
    entirely, so it is kept apart.
    """
    page = ui.new_page(browser, settings)
    yield page
    page.context.close()


@pytest.fixture(scope='module')
def shib_state():
    """Carry what one step learned to the steps after it."""
    return {}


def test_01_the_instance_can_be_reached_where_the_sp_stands(settings,
                                                            shibboleth):
    """Check the stand-in can be run where the SP's script runs.

    Everything after this step depends on it, so it is asked first --
    and asked by running it, because a checkout that is there is not the
    same as a container that will take the script.
    """
    assert shib_login(settings, {'eppn': ''}) is not None, \
        'the stand-in could not be run in the {0} container'.format(
            settings.nginx_service)


def test_02_the_instance_offers_shibboleth_login(client, shibboleth):
    """Check the switch this suite turned on reads back as on.

    An administrator turning it on is the whole of what an instance has
    to do to accept a Shibboleth login, so a run that could not turn it
    on is a run that is about to fail for the wrong reason.
    """
    assert client.shib_login_enabled() is True, \
        'the Shibboleth switch on /admin/shibboleth/ did not take'


def test_03_the_sp_posts_and_weko_answers_with_a_path(settings, shibboleth,
                                                      shib_state):
    """Post the attributes the way the SP's script does.

    WEKO answers a path rather than a redirect -- the SP's script is what
    turns it into one -- and the session is made by whoever follows it.
    A first-time identity gets the confirmation screen; this checks that
    is where an unknown user lands.
    """
    answer = shib_login(settings)
    assert answer and answer.get('next'), \
        'WEKO refused the attributes of {0} ({1}): {2}'.format(
            settings.shib_eppn, (answer or {}).get('status'),
            (answer or {}).get('said') or 'no reason given')
    assert SHIB_CONFIRM_PATH in answer['next'], (
        'an identity WEKO has not seen should be sent to the confirmation '
        'screen, not to {0}; something is already bound to {1}'.format(
            answer['next'], settings.shib_eppn))
    shib_state['first_answer'] = answer


def test_04_the_confirmation_screen_offers_both_ways(shib_page, settings,
                                                     shibboleth, shib_state,
                                                     shot):
    """Look at the screen an identity WEKO does not know is sent to.

    Two ways through, and they are not the same thing: one makes an
    account out of the attributes, and the other binds to an account that
    is already there **and overwrites its email**.
    """
    shib_page.goto(settings.url(shib_state['first_answer']['next']))
    shib_page.wait_for_load_state('networkidle')
    shot(shib_page, '01-confirm-account')
    assert shib_page.locator(ui.NEW_SHIB_USER_LINK).count(), \
        'the confirmation screen offered no way through for a new user'
    assert shib_page.locator('input[name=WEKO_ATTR_ACCOUNT]').count(), \
        'the confirmation screen offered no way to bind an existing account'


def test_05_a_new_user_gets_an_account_and_a_session(shib_page, settings,
                                                     shibboleth, shot):
    """Take the new-user way through, in the browser.

    The same walk the SP sends a real user on: post, follow, and come out
    the other side logged in.  The session id the screen put there is
    what carries it, which is why this follows on from the page above
    rather than starting again.
    """
    shib_page.click(ui.NEW_SHIB_USER_LINK)
    shib_page.wait_for_load_state('networkidle')
    landed = shib_page.url
    assert SHIB_CONFIRM_PATH not in landed and '/login/' not in landed, \
        'the new-user way through did not end in a session (at {0})'.format(
            landed)
    ui.dismiss_cookie_banner(shib_page)
    shot(shib_page, '02-logged-in')


def test_06_the_account_is_the_one_the_attributes_asked_for(settings,
                                                            shibboleth,
                                                            shib_state):
    """Check which attribute became the account.

    ``mail`` does, and ``eppn`` becomes the binding.  The two are
    deliberately different in this run, so this says which one it found
    rather than agreeing with either.
    """
    bound = shib_account(settings)
    assert bound, 'nothing is bound to {0}; no account was made'.format(
        settings.shib_eppn)
    assert bound['eppn'] == settings.shib_eppn
    assert bound['email'] == settings.shib_mail, (
        'the account WEKO made is {0!r}, but the IdP released mail={1!r} '
        '(eppn was {2!r})'.format(
            bound['email'], settings.shib_mail, settings.shib_eppn))
    shib_state['user_id'] = bound['user_id']


def test_07_the_session_belongs_to_that_account(shib_page, settings,
                                                shibboleth, shot):
    """Ask the instance, as the browser, whose account this is.

    The profile screen is the one screen that shows a user their own
    account and nothing else, so it is what the answer is read from.
    """
    shib_page.goto(settings.url('/account/settings/profile/'))
    shib_page.wait_for_load_state('networkidle')
    shot(shib_page, '03-profile')
    email = shib_page.locator('input[name=profile-email]').first.input_value()
    assert email == settings.shib_mail, \
        'the browser is logged in as {0!r}, not as {1!r}'.format(
            email, settings.shib_mail)


def test_08_a_known_identity_comes_straight_in(settings, shibboleth):
    """Log in a second time, now that WEKO knows the identity.

    No confirmation screen this time: WEKO finds the binding and answers
    with the path that logs the user straight in.  Done over HTTP rather
    than in the browser, so that it is a fresh session and not the one
    the steps above left open.
    """
    answer = shib_login(settings)
    assert answer and answer.get('next'), \
        'the second login was refused: {0}'.format(
            (answer or {}).get('said') or 'no reason given')
    assert SHIB_CONFIRM_PATH not in answer['next'], (
        'WEKO asked to confirm an identity it has already bound; '
        'it answered {0}'.format(answer['next']))

    session = WekoClient(settings).login(how=SHIBBOLETH)
    assert session.whoami() == settings.shib_mail


def test_09_a_session_id_nobody_issued_buys_nothing(settings, shibboleth):
    """Check a made-up Shib-Session-ID does not become a session.

    The path the SP sends a user to carries the session id in the URL,
    which is only safe because the id has to have been cached by a POST
    WEKO accepted -- and that POST is what the address check guards.  An
    id nobody issued has nothing behind it, so this asks for one and
    checks that what comes back is still a visitor.
    """
    visitor = anonymous_session(settings)
    visitor.get(settings.url(
        '/weko/auto/login?Shib-Session-ID=_e2e-never-issued&next=%2F'),
        timeout=120)
    after = visitor.get(settings.url(WHOAMI_PATH), timeout=120,
                        allow_redirects=False)
    assert after.status_code != 200, \
        'a Shib-Session-ID nobody issued was enough to log in'
