"""End to end tests for a WEKO3 instance brought up by ``install.sh``.

:mod:`weko_e2e.client` talks to WEKO over HTTP, :mod:`weko_e2e.ui` drives
the screens through a browser, :mod:`weko_e2e.ledger` remembers what a run
created and :mod:`weko_e2e.cli` is the ``e2ectl`` tool that clears it away
again.
"""

__all__ = ('client', 'config', 'ledger', 'ui')
