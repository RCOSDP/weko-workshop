"""An HTTP client for the WEKO screens a run has to set up and tear down.

The registration flow itself is driven through the browser, because that is
what the suite is there to test.  Creating the index, the flow and the
workflow beforehand, and deleting them afterwards, is not: those calls are
made here, against exactly the endpoints the admin screens call, so that
setup is quick and deterministic and so that ``e2ectl`` can clean up
without a browser.
"""

import json
import re
import time
from urllib.parse import urlparse, urlunparse

import requests
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class PinnedHostAdapter(HTTPAdapter):
    """Send requests for one host name to a fixed address.

    The browser gets this from chromium's host resolver rules; this is the
    same thing for the HTTP client, so that a run against a host name DNS
    does not know needs neither an ``/etc/hosts`` entry nor root.  The
    request still carries the host name in its Host header, which is what
    WEKO builds its absolute URLs from.
    """

    def __init__(self, host, address, **kwargs):
        """Pin *host* to *address*."""
        self.host = host
        self.address = address
        super(PinnedHostAdapter, self).__init__(**kwargs)

    def send(self, request, **kwargs):
        """Swap the host for the address, keeping the Host header."""
        parsed = urlparse(request.url)
        if parsed.hostname == self.host:
            netloc = self.address
            if parsed.port:
                netloc = '{0}:{1}'.format(self.address, parsed.port)
            request.url = urlunparse(parsed._replace(netloc=netloc))
            request.headers['Host'] = parsed.netloc
        return super(PinnedHostAdapter, self).send(request, **kwargs)


ACTION_MAIL_SETTING = {
    'inform_reject': {'send': False, 'mail': '0'},
    'inform_reject_for_guest': {'send': False, 'mail': '0'},
    'inform_approval': {'send': False, 'mail': '0'},
    'inform_approval_for_guest': {'send': False, 'mail': '0'},
    'request_approval': {'send': False, 'mail': '0'},
    'request_approval_for_guest': {'send': False, 'mail': '0'},
    'inform_itemReg': {'send': False, 'mail': '0'},
    'inform_itemReg_for_registerPerson': {'send': False, 'mail': '0'},
}
"""The notification settings a flow action is created with: none of them."""

DEFAULT_FLOW_ACTIONS = [
    'Start',
    'Item Registration',
    'Item Link',
    'Identifier Grant',
    'Approval',
    'End',
]
"""The actions of the flow the base test defines.

The same six the shipped ``Registration Flow`` has, so that the base test
walks the screens a default installation walks, and so that a derived test
can drop or add one by passing its own list to :meth:`WekoClient.create_flow`.
"""


class WekoError(RuntimeError):
    """A WEKO call answered with something the suite cannot work with."""


class WekoClient(object):
    """A logged in session against one WEKO instance."""

    def __init__(self, settings):
        """Prepare a session; :meth:`login` still has to be called."""
        self.settings = settings
        self.session = new_session(settings)

    # -- plumbing ---------------------------------------------------------

    def _url(self, path):
        """Return an absolute URL for a path on the instance."""
        return self.settings.url(path)

    def get(self, path, **kwargs):
        """GET a path and fail on anything but a 2xx."""
        response = self.session.get(self._url(path), timeout=120, **kwargs)
        if not response.ok:
            raise WekoError('GET {0} -> {1}'.format(
                path, response.status_code))
        return response

    def post_json(self, path, payload, expect=(200, 201)):
        """POST a JSON body the way the admin screens do."""
        response = self.session.post(
            self._url(path), data=json.dumps(payload), timeout=120,
            headers={'Content-Type': 'application/json'})
        if response.status_code not in expect:
            raise WekoError('POST {0} -> {1}: {2}'.format(
                path, response.status_code, response.text[:400]))
        return response

    def put_json(self, path, payload, expect=(200, 201)):
        """PUT a JSON body the way the admin screens do."""
        response = self.session.put(
            self._url(path), data=json.dumps(payload), timeout=120,
            headers={'Content-Type': 'application/json'})
        if response.status_code not in expect:
            raise WekoError('PUT {0} -> {1}: {2}'.format(
                path, response.status_code, response.text[:400]))
        return response

    def delete(self, path, expect=(200, 201, 204)):
        """DELETE a path the way the admin screens do."""
        response = self.session.delete(
            self._url(path), timeout=120,
            headers={'Content-Type': 'application/json'})
        if response.status_code not in expect:
            raise WekoError('DELETE {0} -> {1}: {2}'.format(
                path, response.status_code, response.text[:400]))
        return response

    @staticmethod
    def _soup(response):
        """Return the parsed body of a response."""
        return BeautifulSoup(response.text, 'html.parser')

    # -- session ----------------------------------------------------------

    def login(self):
        """Log in as the configured account.

        :raise WekoError: when the credentials are refused
        """
        page = self.get('/login/?next=%2F')
        soup = self._soup(page)
        email = soup.find('input', {'name': 'email'})
        login_form = email.find_parent('form') if email else None
        action = (login_form.get('action') if login_form else '') or page.url
        form = {
            'email': self.settings.email,
            'password': self.settings.password,
        }
        for hidden in (login_form.find_all('input', {'type': 'hidden'})
                       if login_form else []):
            if hidden.get('name'):
                form.setdefault(hidden['name'], hidden.get('value', ''))
        response = self.session.post(
            action if action.startswith('http') else self._url(action),
            data=form, timeout=120)
        if not response.ok or '/login/' in response.url:
            raise WekoError('login as {0} was refused'.format(
                self.settings.email))
        return self

    def is_reachable(self):
        """Return whether the instance answers at all."""
        try:
            self.session.get(self._url('/'), timeout=30)
        except requests.RequestException:
            return False
        return True

    # -- indexes ----------------------------------------------------------

    def index_tree(self):
        """Return the index tree as the index screens see it."""
        return self.get('/api/tree').json()

    def find_index(self, name):
        """Return the id of the index with a name, or None.

        The tree carries one name per node, in the language the session
        asked for; an index created through :meth:`create_index` has the
        same text as its Japanese and its English name, so either answers.
        """
        def walk(nodes):
            for node in nodes:
                if node.get('name') == name:
                    return int(node['id'])
                found = walk(node.get('children') or [])
                if found:
                    return found
            return None

        return walk(self.index_tree())

    def create_index(self, name, parent=0, public=True):
        """Create an index and return its id.

        WEKO lets the caller choose the index id, and the index screens
        use a millisecond timestamp; this does the same, so that the id is
        known before the call and the run owns it from the start.

        :param name: index name, written to both the Japanese and the
            English name, as the index screens do
        :param parent: id of the parent index, 0 for a top level index
        :param public: whether to publish the index, which an item has to be
            in before an anonymous visitor can see it
        :return: the new index id
        """
        index_id = int(time.time() * 1000)
        self.post_json('/api/tree/index/{0}'.format(parent),
                       {'id': index_id, 'value': name}, expect=(200, 201))
        if public:
            self.publish_index(index_id)
        return index_id

    def publish_index(self, index_id, public_date='20000101'):
        """Make an index public, so that a visitor can see what is in it.

        Only the three fields that publish an index are sent.  WEKO updates
        exactly the fields it is given, and leaves the roles alone unless
        they are among them, so a partial update cannot quietly reset the
        permissions the index was created with.
        """
        payload = {
            'public_state': True,
            'public_date': public_date,
            'harvest_public_state': True,
        }
        self.put_json('/api/tree/index/{0}'.format(index_id), payload)
        return payload

    def delete_index(self, index_id, action='all'):
        """Delete an index and everything under it."""
        return self.delete('/api/tree/index/{0}?action={1}'.format(
            index_id, action))

    # -- item types -------------------------------------------------------

    def workflow_form_options(self):
        """Return the options the new-workflow screen offers.

        One page carries the item types, the flows and the indexes with the
        ids the workflow has to be created with, so the run reads them all
        from there rather than guessing at ids.

        :return: dict of ``{'itemtype': {name: id}, 'flow': {...},
            'index': {...}}``
        """
        soup = self._soup(self.get('/admin/workflowsetting/0'))
        options = {'itemtype': {}, 'flow': {}, 'index': {}}
        for key, select_id in (('itemtype', 'txt_itemtype'),
                               ('flow', 'txt_flow_name'),
                               ('index', 'txt_index')):
            select = soup.find(id=select_id)
            if not select:
                continue
            for option in select.find_all('option'):
                value = (option.get('value') or '').strip()
                text = ' '.join(option.get_text().split())
                if not value or not text:
                    continue
                if key == 'index':
                    # The index list reads "ID: 17 Name: Some index".
                    match = re.match(r'^ID:\s*\d+\s+Name:\s*(.*)$', text)
                    text = match.group(1).strip() if match else text
                options[key][text] = value
        return options

    def item_type_id(self, name):
        """Return the id of an item type, by the name the screens show.

        :raise WekoError: when no item type has that name
        """
        types = self.workflow_form_options()['itemtype']
        if name not in types:
            raise WekoError('no item type named {0!r}; the instance has: '
                            '{1}'.format(name, ', '.join(sorted(types))))
        return int(types[name])

    # -- flows ------------------------------------------------------------

    def flows(self):
        """Return ``{flow name: flow uuid}`` for every flow."""
        soup = self._soup(self.get('/admin/flowsetting/'))
        found = {}
        for link in soup.find_all('a', href=True):
            match = re.search(r'/admin/flowsetting/([0-9a-f-]{36})$',
                              link['href'])
            if match:
                found[link.get_text().strip()] = match.group(1)
        return found

    def create_flow(self, name, actions=None, repository='Root Index'):
        """Create a flow and give it its actions.

        Creating a flow leaves it with Start and End only, which is also
        what the flow screen shows; the actions in between are added by a
        second call, the one the screen's Save button makes.

        :param name: flow name, which WEKO requires to be unique
        :param actions: action names in order, defaulting to
            :data:`DEFAULT_FLOW_ACTIONS`
        :return: the new flow's uuid
        """
        response = self.post_json('/admin/flowsetting/0', {
            'flow_name': name,
            'repository_id': repository,
        })
        body = response.json()
        redirect = (body.get('data') or {}).get('redirect', '')
        match = re.search(r'/admin/flowsetting/([0-9a-f-]{36})', redirect)
        if not match:
            raise WekoError('flow was not created: {0}'.format(body))
        flow_id = match.group(1)
        self.set_flow_actions(flow_id, actions or DEFAULT_FLOW_ACTIONS)
        return flow_id

    def _flow_page(self, flow_id):
        """Return what the flow screen knows about a flow.

        :return: ``(available, present)`` where *available* maps an action
            name to its ``(id, version)`` and *present* maps an action id to
            the id of the flow's row for it
        """
        soup = self._soup(self.get('/admin/flowsetting/{0}'.format(flow_id)))
        available = {}
        for span in soup.find_all('span', id=re.compile(r'^action_name_\d+$')):
            action_id = span['id'].rsplit('_', 1)[1]
            version = soup.find(id='action_ver_{0}'.format(action_id))
            available[span.get_text().strip()] = (
                action_id, version.get_text().strip() if version else '1.0.0')
        present = {}
        # Only the rows of the flow itself; the page also carries a hidden
        # template row whose cells hold Jinja placeholders.
        for cell in soup.select('#tb_action_list td.action_ids'):
            present[cell.get_text().strip()] = \
                cell.get('data-workflow-flow-action-id')
        return available, present

    def set_flow_actions(self, flow_id, action_names):
        """Set the actions of a flow, in order.

        :param action_names: action names as the flow screen lists them,
            for example ``['Start', 'Item Registration', 'End']``
        :raise WekoError: when the instance has no action of that name
        """
        available, present = self._flow_page(flow_id)
        payload = []
        for name in action_names:
            if name not in available:
                raise WekoError(
                    'no action named {0!r}; the instance offers: {1}'.format(
                        name, ', '.join(sorted(available))))
            action_id, version = available[name]
            payload.append({
                'id': action_id,
                'name': name,
                'date': '',
                'version': version,
                'user': '0',
                'user_deny': False,
                'role': '0',
                'role_deny': False,
                'workflow_flow_action_id': present.get(action_id, -1),
                'send_mail_setting': ACTION_MAIL_SETTING,
                'action': 'ADD',
            })
        response = self.post_json(
            '/admin/flowsetting/action/{0}'.format(flow_id), payload)
        if response.json().get('code') != 0:
            raise WekoError('flow actions were refused: {0}'.format(
                response.text[:400]))
        return payload

    def delete_flow(self, flow_id):
        """Delete a flow, which WEKO refuses while a workflow uses it."""
        response = self.delete('/admin/flowsetting/{0}'.format(flow_id))
        body = response.json()
        if body.get('code') not in (0, None):
            raise WekoError('flow {0} was not deleted: {1}'.format(
                flow_id, body.get('msg')))
        return body

    # -- workflows --------------------------------------------------------

    def workflows(self):
        """Return ``{workflow name: workflow uuid}`` for every workflow."""
        soup = self._soup(self.get('/admin/workflowsetting/'))
        found = {}
        for link in soup.find_all('a', href=True):
            match = re.search(r'/admin/workflowsetting/([0-9a-f-]{36})$',
                              link['href'])
            if match:
                found[link.get_text().strip()] = match.group(1)
        return found

    def create_workflow(self, name, item_type_id, flow_id, index_id=None,
                        repository='Root Index'):
        """Create a workflow and return its uuid.

        :param flow_id: the flow's *numeric* id, which is what the workflow
            screen's flow list carries, not the flow uuid
        :param index_id: index the activity starts with designated, or None
        """
        self.post_json('/admin/workflowsetting/0', {
            'flows_name': name,
            'itemtype_id': int(item_type_id),
            'flow_id': int(flow_id),
            'index_id': int(index_id) if index_id else None,
            'location_id': None,
            'open_restricted': False,
            'is_gakuninrdm': False,
            'repository_id': repository,
            'list_hide': [],
        })
        uuid = self.workflows().get(name)
        if not uuid:
            raise WekoError('workflow {0!r} was not created'.format(name))
        return uuid

    def flow_numeric_id(self, flow_name):
        """Return the numeric id the workflow screen uses for a flow."""
        flows = self.workflow_form_options()['flow']
        if flow_name not in flows:
            raise WekoError('no flow named {0!r}'.format(flow_name))
        return int(flows[flow_name])

    def delete_workflow(self, workflow_uuid):
        """Delete a workflow, which WEKO refuses while it has activities."""
        response = self.delete(
            '/admin/workflowsetting/{0}'.format(workflow_uuid))
        body = response.json()
        if body.get('code') not in (0, None):
            raise WekoError('workflow {0} was not deleted: {1}'.format(
                workflow_uuid, body.get('msg')))
        return body

    # -- activities -------------------------------------------------------

    def activities(self, tab='all'):
        """Return the activities the list screen shows.

        Which columns that screen shows is an instance setting, and a
        default installation does not show the activity id, in which case
        this finds nothing however many activities exist.  Discovery of
        stray activities therefore belongs to ``e2ectl clean --hard``,
        which reads them from the workflow they belong to; this is only
        the best the screens can offer.

        :return: list of ``{'activity_id', 'row'}``
        """
        soup = self._soup(
            self.get('/workflow/activity/list?tab={0}&size=100'.format(tab)))
        rows = []
        for link in soup.select('a.activity-link'):
            match = re.search(r'\bA-\d{8}-\d+\b', link.get('href') or '')
            if match:
                rows.append({
                    'activity_id': match.group(0),
                    'row': link.find_parent('tr').get_text(' ', strip=True)
                    if link.find_parent('tr') else '',
                })
        return rows

    def release_user_lock(self, activity_id):
        """Let go of whatever activity this account is holding open.

        WEKO lets one account have one activity open at a time and
        releases the hold when the window showing it unloads, so a run
        that was killed leaves one behind -- and the screens only offer
        to force it off when it is the same activity, which leaves the
        next run looking at "Already have another activity open".

        :param activity_id: the activity that is about to be opened
        :return: True when WEKO took the call
        """
        response = self.session.post(
            self._url('/workflow/activity/user_unlock/{0}'.format(
                activity_id)),
            data=json.dumps({'is_opened': False, 'is_force': True}),
            timeout=120, headers={'Content-Type': 'application/json'})
        return response.ok

    def quit_activity(self, activity_id):
        """Quit an activity, as the Quit button on its screen does.

        :return: True when the activity was quit or was already gone
        """
        self.session.post(
            self._url('/workflow/activity/unlock/{0}'.format(activity_id)),
            data=json.dumps({'is_opened': True}), timeout=120,
            headers={'Content-Type': 'application/json'})
        page = self.session.get(
            self._url('/workflow/activity/detail/{0}'.format(activity_id)),
            timeout=120)
        if page.status_code == 404:
            return True
        cancel = re.search(r'data-cancel-uri="([^"]+)"', page.text)
        version = re.search(r'data-action-version="([^"]*)"', page.text)
        if not cancel:
            return False
        response = self.session.post(
            self._url(cancel.group(1)),
            data=json.dumps({
                'commond': 'quit by e2ectl',
                'action_version': version.group(1) if version else '',
                'pid_value': '',
            }),
            timeout=120, headers={'Content-Type': 'application/json'})
        return response.ok and response.json().get('code') == 0

    # -- items ------------------------------------------------------------

    def soft_delete_item(self, recid):
        """Delete an item the way its detail screen does.

        This is WEKO's own delete, which keeps the record row and marks it
        deleted.  ``e2ectl clean --hard`` removes it outright instead.
        """
        response = self.session.post(
            self._url('/records/soft_delete/{0}'.format(recid)), timeout=120)
        return response.ok

    def record_exists(self, recid, session=None):
        """Return whether a record page answers, for the given session.

        :param session: a session to ask with, defaulting to the logged in
            one; pass a fresh :class:`requests.Session` to ask as an
            anonymous visitor
        """
        target = session or self.session
        response = target.get(self._url('/records/{0}'.format(recid)),
                              timeout=120)
        return response.status_code == 200, response

    def search_index(self, index_id, size=100):
        """Return the records the search API finds in an index."""
        response = self.session.get(
            self._url('/api/records/'),
            params={'search_type': 2, 'q': str(index_id), 'size': size},
            timeout=120)
        if not response.ok:
            raise WekoError('search in index {0} -> {1}'.format(
                index_id, response.status_code))
        return response.json().get('hits', {}).get('hits', [])

    def recids_in_index(self, index_id, size=100):
        """Return the ids of the records the search API finds in an index.

        A hit carries its id twice -- as the control number in the metadata
        and as the hit id -- and which of the two is filled in has changed
        between serializers, so both are read.
        """
        found = set()
        for hit in self.search_index(index_id, size=size):
            for value in (hit.get('metadata', {}).get('control_number'),
                          hit.get('id')):
                if value:
                    found.add(str(value))
        return found


def new_session(settings):
    """Return a session set up the way this environment needs.

    :param settings: :class:`weko_e2e.config.Settings`
    """
    session = requests.Session()
    session.verify = settings.verify_tls
    session.headers['Accept-Language'] = 'en'
    if settings.host_ip and settings.host:
        session.mount('https://',
                      PinnedHostAdapter(settings.host, settings.host_ip))
        session.mount('http://',
                      PinnedHostAdapter(settings.host, settings.host_ip))
    return session


def anonymous_session(settings):
    """Return a session that has not logged in, for visibility checks."""
    return new_session(settings)
