"""Browser helpers for walking a WEKO workflow activity.

The screens of an activity all live in one page, several of them at once,
and the page is rebuilt by Angular and React as the activity moves on, so
almost every helper here is about waiting for the right screen and acting
only on the controls that screen is showing.

The step names used throughout are WEKO's own action endpoints -- the value
the page publishes in ``#hide-actioncur_step`` -- rather than the labels on
the screen, so a run does not depend on the instance's display language.
"""

import os
import re
import tempfile
import time

from playwright.sync_api import Error

from .client import SHIB_CONFIRM_PATH
from .config import E2E_DIR, SHIBBOLETH

NEW_SHIB_USER_LINK = 'a[href*="/weko/auto/login"]'
"""The confirmation screen's "Login (New WEKO users)" way through."""

BEGIN = 'begin_action'
ITEM_REGISTRATION = 'item_login'
ITEM_LINK = 'item_link'
IDENTIFIER_GRANT = 'identifier_grant'
APPROVAL = 'approval'
END = 'end_action'

SAMPLE_PDF = (
    b'%PDF-1.4\n'
    b'1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
    b'2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
    b'3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]'
    b'/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n'
    b'4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n'
    b'5 0 obj<</Length 54>>stream\n'
    b'BT /F1 12 Tf 20 50 Td (WEKO3 e2e sample file) Tj ET\n'
    b'endstream endobj\n'
    b'trailer<</Root 1 0 R>>\n'
)
"""A one page PDF, so the registered item has a file like a real one does."""


def sample_file(name='weko-e2e-sample.pdf'):
    """Write the sample PDF to a temporary file and return its path."""
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, 'wb') as handle:
        handle.write(SAMPLE_PDF)
    return path


# -- session ---------------------------------------------------------------

def new_page(browser, settings):
    """Return a page in a browsing context of its own.

    A context is what holds the cookies, so one per account: the run's own
    page is logged in as the registrant, and a page that has to be
    somebody else -- the approver, or a visitor who has not logged in --
    cannot share it.  Close ``page.context`` when done with it.
    """
    context = browser.new_context(
        ignore_https_errors=True,
        viewport={'width': 1440, 'height': 1000},
        locale='en-US')
    context.set_default_timeout(settings.timeout)
    return context.new_page()


def dismiss_cookie_banner(page):
    """Accept the cookie banner, if this instance shows one.

    Found by what it is rather than by what it says, so that an instance
    running in Japanese is no different from one running in English.
    """
    for selector in ('.cc-compliance .cc-dismiss', '.cc-compliance .cc-allow',
                     '.cc-window .cc-btn', '#cookie-consent-accept'):
        banner = page.locator(selector).locator('visible=true')
        if banner.count():
            banner.first.click()
            page.wait_for_timeout(500)
            return True
    banner = page.get_by_role('button', name="That's ok")
    if banner.count() and banner.first.is_visible():
        banner.first.click()
        page.wait_for_timeout(500)
        return True
    return False


def login(page, settings, how=None):
    """Log in, and get the cookie banner out of the way of the screenshots.

    Does nothing when this page is logged in already: several suites in
    one session share the browser, and WEKO sends an authenticated
    visitor away from the login screen rather than showing it again.

    :param how: ``'local'`` for the login screen, ``'shibboleth'`` to
        come in the way the Shibboleth SP brings a user in; defaults to
        what the environment asked for
    :raise AssertionError: when the credentials are refused
    """
    if (how or settings.login_as) == SHIBBOLETH:
        return login_shibboleth(page, settings)
    return login_locally(page, settings)


def login_shibboleth(page, settings):
    """Bring this browser in the way the Shibboleth SP brings a user in.

    The SP is stood in for -- see :mod:`weko_e2e.shibstub` -- and what
    comes back is a path.  In a real deployment the SP's script answers
    the browser with a redirect to it; here the browser is simply sent
    there, which is the same walk with the same session.

    The new-user way through the confirmation screen is the one taken,
    because the other way overwrites the email of the account it binds
    to.  See :meth:`~weko_e2e.client.WekoClient.login_shibboleth`.

    :raise AssertionError: when the login does not end in a session
    """
    from .cli import shib_login

    answer = shib_login(settings)
    assert answer and answer.get('next'), \
        'WEKO refused the attributes of {0}: {1}'.format(
            settings.shib_eppn,
            (answer or {}).get('said') or 'the stand-in could not be run')
    page.goto(settings.url(answer['next']))
    page.wait_for_load_state('networkidle')
    if page.locator(NEW_SHIB_USER_LINK).count():
        page.click(NEW_SHIB_USER_LINK)
        page.wait_for_load_state('networkidle')
    assert '/login/' not in page.url and SHIB_CONFIRM_PATH not in page.url, \
        'the Shibboleth login of {0} did not end in a session; Shibboleth ' \
        'login has to be on (/admin/shibboleth/)'.format(settings.shib_eppn)
    dismiss_cookie_banner(page)


def login_locally(page, settings):
    """Log in through the login screen.

    :raise AssertionError: when the credentials are refused
    """
    page.goto(settings.url('/login/?next=%2F'))
    page.wait_for_load_state('networkidle')
    if not page.locator('input[name=email]').count():
        dismiss_cookie_banner(page)
        return
    page.fill('input[name=email]', settings.email)
    page.fill('input[name=password]', settings.password)
    page.click('button[type=submit]')
    page.wait_for_load_state('networkidle')
    assert '/login/' not in page.url, \
        'login as {0} failed'.format(settings.email)
    dismiss_cookie_banner(page)


# -- activities ------------------------------------------------------------

def start_activity(page, settings, workflow_name):  # noqa: C901
    """Start an activity on a named workflow and return its id.

    A run that did not reach the end leaves its activity open, and WEKO
    lets one user hold one activity at a time, so any activity still open
    is quit first -- WEKO names them one at a time, hence the loop.

    :return: the activity id, for example ``A-20260916-00001``
    """
    for _ in range(6):
        page.goto(settings.url('/workflow/activity/new'))
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1500)
        begin = page.locator(
            "//td[normalize-space(text())={0}]/..//*[contains(@class, "
            "'btn-begin')]".format(_xpath_literal(workflow_name)))
        assert begin.count(), \
            'workflow {0!r} is not offered on /workflow/activity/new'.format(
                workflow_name)
        begin.first.click()
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(6000)
        if '/workflow/activity/detail/' in page.url:
            force_unlock(page)
            return activity_id(page)
        if not quit_open_activity(page, settings):
            break
    raise AssertionError(
        'could not start an activity on {0!r}; the page says: {1}'.format(
            workflow_name, page.locator('body').inner_text()[:400]))


def activity_id(page):
    """Return the id of the activity the page is showing."""
    marker = page.locator('#activity_id, #activity_id_text')
    if marker.count():
        text = marker.first.inner_text().strip()
        if text:
            return text
    match = re.search(r'/workflow/activity/detail/(A-[0-9\-]+)', page.url)
    return match.group(1) if match else None


def quit_open_activity(page, settings):
    """Quit the activity WEKO says is already open, if it named one.

    :return: the activity id that was quit, or None
    """
    match = re.search(r'Already have another activity open \((A-[0-9\-]+)\)',
                      page.locator('body').inner_text())
    if not match:
        return None
    return quit_activity(page, settings, match.group(1))


def quit_activity(page, settings, identifier):
    """Quit one activity through its own screen."""
    page.goto(settings.url('/workflow/activity/detail/{0}'.format(identifier)))
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(4000)
    force_unlock(page)
    quit_button = page.locator('#btn_quit').locator('visible=true')
    if not quit_button.count():
        return None
    quit_button.first.click()
    page.wait_for_timeout(1000)
    page.locator('#btn_cancel').locator('visible=true').first.click()
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(4000)
    return identifier


def leave_activity(page, settings):
    """Leave the activity screen, which lets go of the lock on it.

    WEKO locks an activity to the window that has it open and releases
    the lock as that window unloads, so a second person can take the
    activity over only once the first has moved on.  A run in which the
    registrant hands an item to an approver has to do the same.
    """
    page.goto(settings.url('/'))
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)


def force_unlock(page):
    """Take over an activity another session left locked, when asked to."""
    button = page.locator('#user_locked_btn')
    if button.count() and button.first.is_visible():
        button.first.click()
        page.locator('#btn_unlock').first.click()
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(6000)


# -- steps -----------------------------------------------------------------

def current_step(page):
    """Return the endpoint name of the step the activity is on.

    :return: one of :data:`BEGIN`, :data:`ITEM_REGISTRATION`,
        :data:`ITEM_LINK`, :data:`IDENTIFIER_GRANT`, :data:`APPROVAL`,
        :data:`END`, or an empty string when the page shows no step
    """
    marker = page.locator('#hide-actioncur_step')
    if marker.count():
        return marker.first.inner_text().strip()
    return ''


NEXT_BUTTON = (
    '#btn-finish, #item-link-run-btn, '
    '.next-button:not(#btn-back):not(#btn-reject)'
)
"""Selector for the Next button, whichever screen is showing.

Every screen of the activity is in the page at once, so only the visible
match belongs to the screen the user is looking at.  The exclusions are
there because the comment screen gives its *Back* button the same
``next-button`` class as its Next, and clicking that walks the activity
backwards for ever.
"""


def next_button(page):
    """Return the Next button of the screen that is showing."""
    button = page.locator(NEXT_BUTTON).locator('visible=true')
    if not button.count():
        # Last resort, for a screen whose button carries neither id nor
        # class: match the label in either of the languages WEKO ships.
        button = page.get_by_role(
            'button',
            name=re.compile(r'^\s*(Next|次へ)')).locator('visible=true')
    return button


def click_next(page):
    """Click the Next button of the screen that is showing."""
    button = next_button(page)
    assert button.count(), 'no Next button on the screen that is showing'
    button.first.click()


def wait_for_step(page, name, timeout=300):
    """Wait until the activity has moved on to a named step.

    Saving an item runs long enough that the next screen is still being
    built when the click returns.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        page.wait_for_timeout(1000)
        force_unlock(page)
        if current_step(page) == name:
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(2000)
            return
    _stuck(page, name)


def advance_to(page, name, timeout=300):
    """Click Next until the activity reaches a named step.

    One step can span several screens -- Item Registration is the metadata
    form, then the index designation -- and the step marker only changes on
    the last of them, so reaching the next step means clicking Next as many
    times as the screens require.
    """
    deadline = time.time() + timeout
    clicked_at = 0
    while time.time() < deadline:
        force_unlock(page)
        if current_step(page) == name:
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(2000)
            return
        button = next_button(page)
        if button.count() and time.time() - clicked_at > 8:
            button.first.click()
            clicked_at = time.time()
        page.wait_for_timeout(1500)
    _stuck(page, name)


DIALOG_SELECTORS = (
    '.modal:visible',
    '[role=dialog]:visible',
    '.modal-dialog:visible',
    '.alert:visible',
    '.panel-danger:visible',
)
"""Where WEKO puts what it wants to say when something has gone wrong.

More than one, and every frame, because the screens that matter here are
served in an iframe and the dialog itself is built by JavaScript rather
than written in a template -- so there is no one selector to rely on.
A run that stops and reports "(no dialog)" while the screen is showing
"Server Error" is worse than no diagnosis at all.
"""


def _dialog_text(page):
    """Return what a dialog on the page says, from any frame."""
    for frame in page.frames:
        for selector in DIALOG_SELECTORS:
            try:
                found = frame.locator(selector)
                if found.count():
                    said = found.first.inner_text().strip()
                    if said:
                        return said
            except Error:  # a frame that went away mid-look
                continue
    return '(no dialog)'


def _stuck(page, name):
    """Fail with what the screen was showing when a step did not arrive.

    The screenshot goes under ``evidence`` rather than into a temporary
    directory, because what somebody sends back after a run elsewhere is
    that folder -- and a picture of the screen a run stopped on is
    exactly what is wanted and exactly what used to be left behind.
    """
    detail = _dialog_text(page)
    evidence = os.path.join(E2E_DIR, 'evidence', 'stuck-{0}.png'.format(name))
    try:
        os.makedirs(os.path.dirname(evidence), exist_ok=True)
    except OSError:  # a picture is never what fails a step
        evidence = os.path.join(tempfile.gettempdir(), 'weko-e2e-stuck.png')
    page.screenshot(path=evidence, full_page=True)
    try:
        with open(evidence[:-len('.png')] + '.html', 'w',
                  encoding='utf-8') as handle:
            handle.write(page.content())
    except (OSError, Error):  # neither is what fails a step
        pass
    raise AssertionError(
        'stuck on step "{0}", waiting for "{1}"; showing: {2}; '
        'screen saved to {3}'.format(
            current_step(page), name, detail.replace(chr(10), ' | '),
            evidence))


# -- the item metadata form ------------------------------------------------

def field(page, name):
    """Return the visible control of an item metadata field.

    The form is a set of collapsible panels and a field is invisible until
    its panel is open, so this opens the panel holding the field the first
    time that field is asked for.  It also skips the hidden copy the form
    keeps of every field as its "add another" template.

    :param name: form control name, e.g.
        ``item_30002_title0.0.subitem_title``
    """
    escaped = name.replace('.', '\\.')
    control = page.locator(
        "input[name='{0}'], select[name='{0}'], textarea[name='{0}']".format(
            escaped))
    visible = control.locator('visible=true')
    if not visible.count():
        control.first.evaluate(
            "el => {const panel = el.closest('.panel');"
            " const toggle = panel && panel.querySelector('a.panel-toggle');"
            " if (toggle) toggle.click();}")
        page.wait_for_timeout(800)
        visible = control.locator('visible=true')
    assert visible.count(), 'the form has no visible field {0!r}'.format(name)
    return visible.first


def upload_file(page, path, timeout=180000):
    """Attach a file to the item and wait for the upload to finish.

    :param timeout: milliseconds to wait for the upload to complete; a
        slow or remote instance wants ``WEKO_E2E_UPLOAD_TIMEOUT`` raised
    """
    page.locator("//input[@type='file']").first.set_input_files(path)
    page.locator('button[ng-click="onUploadFileContents()"]').locator(
        'visible=true').first.click()
    page.wait_for_selector(
        '//tr[contains(@class, "sel-file")]//span[@ng-show="f.completed"]',
        timeout=timeout)
    page.wait_for_timeout(2000)


def wait_for_index_tree(page, index_name, timeout=300000):
    """Wait for the index designation screen to list a named index."""
    page.wait_for_selector(
        '//*[contains(@class, "node-name") and text()={0}]'.format(
            _xpath_literal(index_name)), timeout=timeout)


def designate_index(page, index_name):
    """Tick a named index on the index designation screen.

    The screen refuses Next while no index is designated, so the checkbox
    is found through its tree node rather than by position.
    """
    page.wait_for_timeout(2000)
    checkbox = page.locator(
        '//*[contains(@class, "node-name") and text()={0}]'
        '/../..//input[@type="checkbox"]'.format(_xpath_literal(index_name)))
    assert checkbox.count(), \
        'the index tree does not offer {0!r}'.format(index_name)
    checkbox.first.check()
    page.wait_for_timeout(1500)


def approve(page):
    """Approve the activity, which is what publishes the item."""
    button = page.locator('#btn-approval').locator('visible=true')
    assert button.count(), 'the approval screen has no Approval button'
    button.first.click()
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(8000)


def registered_recid(page):
    """Return the id of the record the finished activity registered.

    A finished activity offers an Access button pointing at the item's
    public page; its target is where the record id comes from.
    """
    for _ in range(20):
        match = re.search(r"window\.location\.href='/records/([^']+)'",
                          page.content())
        if match:
            return match.group(1)
        link = page.locator("a[href^='/records/']")
        if link.count():
            href = link.first.get_attribute('href')
            found = re.match(r'^/records/([^/?#]+)', href or '')
            if found:
                return found.group(1)
        page.wait_for_timeout(1500)
        page.reload()
        page.wait_for_load_state('networkidle')
    return None


def _xpath_literal(text):
    """Return an XPath string literal for text that may contain quotes."""
    if "'" not in text:
        return "'{0}'".format(text)
    if '"' not in text:
        return '"{0}"'.format(text)
    parts = text.split("'")
    return "concat({0})".format(
        ", \"'\", ".join("'{0}'".format(part) for part in parts))
