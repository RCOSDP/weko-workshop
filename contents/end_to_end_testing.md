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

## Run it against an instance docker does not run

Everything the tool does inside a container goes through one command
line, and `WEKO_E2E_EXEC` is what that command line is. Unset, it is
`docker compose exec -T` against the checkout. For an instance on
Kubernetes:

```
WEKO_E2E_EXEC='kubectl exec -i -n weko {service} --'
WEKO_E2E_WEB_SERVICE=deploy/weko-web
WEKO_E2E_DB_SERVICE=statefulset/postgresql
WEKO_E2E_WORKER_SERVICE=deploy/weko-worker
```

`{service}` is where the name goes, and the `WEKO_E2E_*_SERVICE`
settings hold whatever that command calls each container. A setting may
be several words, which is how each one carries its own `-c` where web,
nginx and the worker are three containers of one pod, and its own `-n`
where the database is in a namespace of its own. With it the
doctor asks all of its checks, `--doctor-fix` repairs, `clean --hard`
works, the optional suites run, and no WEKO checkout is needed for any of
it. `./e2ectl env` says which way it will go.

The one thing that does not cross over is the web push stand-in, which
writes keys into the compose file — so the `coarnotify` suite's four push
steps skip. The `ark` suite's stand-in does cross over, but its settings
have to be applied by hand, because where a deployment keeps instance
configuration is its own business: `./e2ectl ark-stub config` prints
them, and `./e2ectl ark-stub start` then runs the stand-in in the web
pod. `./e2ectl crossref-account config` does the same for the Crossref
deposit account — though granting a DOI needs no account at all.
[The suite in full](../e2e/README.md) has the detail, including what a
replicated database needs.

The `coarnotify` suite needs an LDN inbox to exist at all, which a
cluster has to be given:
[`deploy/coar-notify-inbox/`](../deploy/coar-notify-inbox/README.md) has
the manifests for it.

## Repair an instance you cannot reach the containers of

`--doctor-fix` works through `docker compose`, so it is no use for an
instance somewhere else. The tool can write the same repairs out as SQL
instead, to be handed to whoever can run it on that database:

```
WEKO_E2E_WEKO_REF=release_v2.1.0 ../.venv-e2e/bin/python ./e2ectl doctor --sql > repair.sql
```

The reading of the instance goes to stderr and the script to stdout, so
that is a file you can run rather than one you have to edit first. It is
one transaction, it only adds rows, and a row whose id is already in use
undoes the whole of it.

The version matters. The rows are WEKO's own data, and an instance built
from an older WEKO wants that WEKO's — between `v2.0.3` and
`release_v2.1.0` the shipped item types go from 173 rows to 210.
`WEKO_E2E_WEKO_REF` is the branch, tag or commit to take them from; they
are fetched from GitHub over HTTP, nothing is cloned, and what is fetched
is kept, so the second time needs no network. `e2ectl seed <ref>` takes a
version ahead of time, and a distribution package built afterwards
carries it — for a machine that has no network at all.

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
