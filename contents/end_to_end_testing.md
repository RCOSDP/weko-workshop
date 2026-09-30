# Testing WEKO3 end to end

The `e2e` directory holds a test suite that drives a WEKO3 instance
through a browser, the way a person would. It creates an index, defines a
flow and a workflow, registers an item on the default full item type,
approves it, and then checks that a visitor who has not logged in can see
the item and that search finds it.

Run it after installing WEKO3 to see that the instance really works, and
after changing WEKO3 to see that it still does. It runs against whatever
instance you point it at: the one `install.sh` brought up on this
machine, or a server somewhere else.

## Install the test suite

The tests run outside the containers, so they need a Python environment
of their own. From the root of this repository:

```
python3 -m venv .venv-e2e
.venv-e2e/bin/pip install -r e2e/requirements.txt
.venv-e2e/bin/playwright install chromium
```

## Point it at an instance

Everything about the instance comes from environment variables, or from
an environment file. For a stack `install.sh` brought up on this machine
the defaults are already right; `environments/` holds files to copy for
anything else.

```
cd e2e
cp environments/local-docker.env e2e.env
```

Check what a run would use, and that the instance answers as that
account:

```
../.venv-e2e/bin/python ./e2ectl env
../.venv-e2e/bin/python ./e2ectl ping
```

## Run the tests

```
../.venv-e2e/bin/python -m pytest
```

Before its first test the run looks the instance over, and stops if what
the tests depend on is not there — a missing item type, an account
without the right role, a month with no log partition. Looking changes
nothing; it says which one it is, and `--doctor-fix` puts right what can
be put right by **adding** it. Nothing the tests do to your instance is
ever a deletion you did not ask for:

```
../.venv-e2e/bin/python -m pytest --doctor-fix
```

Thirteen steps, a minute or two. Set `WEKO_HEADED=1` to watch the browser
do it.

## Run the optional suites too

Four more suites sit beside the base flow, each asked for by name,
because each needs something of the instance that not every instance has.

| Suite | What it checks |
| --- | --- |
| `ark` | an ARK is minted for the item and becomes its permalink |
| `coarnotify` | the approval request and the approval are announced over COAR Notify, and arrive as a web push |
| `crossref` | a Crossref DOI is granted to the item |
| `shibboleth` | a Shibboleth user logs in, and `mail` — not `eppn` — becomes the account's email |

Two of them want a stand-in server, which the tool runs for you:

```
../.venv-e2e/bin/python ./e2ectl ark-stub enable
../.venv-e2e/bin/python ./e2ectl webpush-stub enable
WEKO_E2E_ARK_NAAN=99999 ../.venv-e2e/bin/python -m pytest --suite all
```

A suite nobody asked for is skipped rather than hidden, so a run always
says what it did not do and how to ask for it.

The `shibboleth` suite needs no IdP and nothing configured. WEKO is not
what speaks SAML — the Service Provider does, in nginx — so the suite
stands where the SP stands, inside the `nginx` container, and sends what
the SP sends. It turns Shibboleth login on itself and puts the switch
back afterwards, takes only the way through that *makes* an account
rather than the one that renames an existing one, and removes what it
made:

```
../.venv-e2e/bin/python -m pytest --suite shibboleth
```

## Clean up afterwards

A run leaves what it created in place, so that a failure can be looked at
in the browser. The tool is what removes it.

```
../.venv-e2e/bin/python ./e2ectl status      # what is still there
../.venv-e2e/bin/python ./e2ectl clean --hard   # take it away
```

`clean` deletes the way the screens do, which in WEKO is a logical
delete. `--hard` also removes the rows WEKO only marks deleted, so the
database goes back to how `install.sh` left it — granted DOIs, minted
ARKs and draft items included.

To have the run clean up after itself instead:

```
../.venv-e2e/bin/python -m pytest --clean-after --clean-hard
```

Turn the stand-in servers off when you are done with them:

```
../.venv-e2e/bin/python ./e2ectl webpush-stub disable
../.venv-e2e/bin/python ./e2ectl ark-stub disable
```

## What a run leaves behind

`e2e/evidence/` holds the report of the last run: what the instance
looked like beforehand, and the screenshots every step took of itself.
Re-running refreshes them in place, so the report cannot drift from what
the tests actually do.

## Reading further

- [The test suite in full](../e2e/README.md) — every setting, each suite,
  deriving a suite of your own, and what to do when it does not work.
  [日本語版](../e2e/README.ja.md)
- [The last run](../e2e/evidence/README.md) — the report, step by step,
  with the screenshots. [日本語版](../e2e/evidence/README.ja.md)
