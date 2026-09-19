"""The record of what a run created, so it can be cleaned up afterwards.

A run appends to a JSON file as it goes rather than at the end, so that a
run which fails half way -- or is killed -- still leaves behind a complete
list of what it had created up to that point.  ``e2ectl clean`` reads the
file back and deletes in reverse dependency order.
"""

import json
import os
from datetime import datetime

KINDS = ('item', 'activity', 'workflow', 'flow', 'index')
"""Resource kinds, in the order they have to be deleted in."""


class Ledger(object):
    """A JSON file listing the resources each run created."""

    def __init__(self, path):
        """Open, but do not yet read, the ledger at a path."""
        self.path = path

    def _load(self):
        """Return the whole file, or an empty ledger when there is none."""
        if not os.path.isfile(self.path):
            return {'runs': []}
        with open(self.path, encoding='utf-8') as handle:
            try:
                return json.load(handle)
            except ValueError:
                return {'runs': []}

    def _save(self, data):
        """Write the whole file back, atomically."""
        directory = os.path.dirname(os.path.abspath(self.path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        temporary = self.path + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        os.replace(temporary, self.path)

    def runs(self):
        """Return every run in the ledger, oldest first."""
        return self._load()['runs']

    def run(self, run_id):
        """Return one run, or None when the ledger does not know it."""
        for entry in self.runs():
            if entry['run_id'] == run_id:
                return entry
        return None

    def start_run(self, run_id, base_url, label):
        """Open a run in the ledger, replacing an earlier one of that id."""
        data = self._load()
        data['runs'] = [r for r in data['runs'] if r['run_id'] != run_id]
        data['runs'].append({
            'run_id': run_id,
            'label': label,
            'base_url': base_url,
            'started': datetime.now().isoformat(timespec='seconds'),
            'resources': [],
        })
        self._save(data)

    def add(self, run_id, kind, identifier, name=None, **extra):
        """Record one resource a run created.

        :param run_id: the run that created it
        :param kind: one of :data:`KINDS`
        :param identifier: what the delete call needs -- an index id, a flow
            or workflow uuid, an activity id, a record id
        :param name: what the resource is called, for the tool's output
        """
        if kind not in KINDS:
            raise ValueError('unknown resource kind: {0}'.format(kind))
        data = self._load()
        for entry in data['runs']:
            if entry['run_id'] != run_id:
                continue
            resource = {'kind': kind, 'id': str(identifier)}
            if name:
                resource['name'] = name
            resource.update(extra)
            if resource not in entry['resources']:
                entry['resources'].append(resource)
            self._save(data)
            return resource
        raise KeyError('run {0} is not in the ledger'.format(run_id))

    def resources(self, run_id=None):
        """Return the resources of one run, or of every run.

        :return: list of ``(run_id, resource)`` pairs, in deletion order
        """
        pairs = []
        for entry in self.runs():
            if run_id and entry['run_id'] != run_id:
                continue
            for resource in entry['resources']:
                pairs.append((entry['run_id'], resource))
        pairs.sort(key=lambda pair: KINDS.index(pair[1]['kind']))
        return pairs

    def drop(self, run_id, resource=None):
        """Forget a resource, or a whole run, that no longer exists."""
        data = self._load()
        if resource is None:
            data['runs'] = [r for r in data['runs'] if r['run_id'] != run_id]
        else:
            for entry in data['runs']:
                if entry['run_id'] == run_id:
                    entry['resources'] = [
                        r for r in entry['resources'] if r != resource]
        self._save(data)

    def drop_empty(self):
        """Forget every run that has no resources left."""
        data = self._load()
        data['runs'] = [r for r in data['runs'] if r['resources']]
        self._save(data)
