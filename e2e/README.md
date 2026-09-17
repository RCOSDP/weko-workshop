# WEKO3 end to end tests (the base flow)

日本語版: [`README.ja.md`](README.ja.md)

An end to end test that walks a WEKO3 instance through the whole of it:
**create a test index, define a test workflow, register an item on the
default full item type, and publish it**. Derived suites -- DOI
registration, restricted access, the simple item type -- are meant to be
built out of the same parts rather than written from scratch.

The suite lives here rather than in the WEKO checkout, so it can be
pointed at whatever instance you have: a stack brought up by `install.sh`
on this machine, a staging server behind a real host name, a colleague's
box. Nothing about the instance is hard coded; see
[Settings](#settings-environment-variables).

Everything a run creates -- index, flow, workflow, activity, item -- is
written to a ledger, and `./e2ectl clean` removes it again.

## What is here

| File | What it is |
| --- | --- |
| `tests/test_basic_publish.py` | The base suite: one flow cut into 13 steps |
| `tests/test_ark_mint.py` | Optional suite `ark`: an ARK is minted for the item |
| `tests/test_crossref_doi.py` | Optional suite `crossref`: a Crossref DOI is granted |
| `conftest.py` | The browser, the HTTP client and the ledger the run shares |
| `weko_e2e/flow.py` | The registration flow every suite walks |
| `weko_e2e/arkstub.py` | A stand-in ARK server, for the `ark` suite |
| `weko_e2e/config.py` | The settings, read from the environment or an environment file |
| `weko_e2e/client.py` | HTTP client for the endpoints the screens call, for setup and teardown |
| `weko_e2e/ui.py` | Playwright helpers for walking an activity's screens |
| `weko_e2e/ledger.py` | The record of what a run created (`.e2e-state.json`) |
| `weko_e2e/purge.py` | The physical delete, copied into the `web` container and run there |
| `weko_e2e/cli.py`, `e2ectl` | The tool |
| `environments/` | Environment files to copy and change |
| `evidence/` | The last run's report and its screenshots |

## Setting up

```bash
# From the root of this repository.
python3 -m venv .venv-e2e
.venv-e2e/bin/pip install -r e2e/requirements.txt
.venv-e2e/bin/playwright install chromium
```

You also need a WEKO3 instance to test. For a local one, in a WEKO
checkout:

```bash
./install.sh
```

## Pointing it at an instance

Set the variables, or put them in an environment file. There are three to
copy in [`environments/`](environments):

| File | For |
| --- | --- |
| `local-docker.env` | A stack `install.sh` brought up on this machine (also the defaults) |
| `fqdn.env` | An instance on a real host name with a real certificate |
| `fqdn-no-dns.env` | An instance published under a host name DNS does not know |
| `crossref-sandbox.env` | Depositing to Crossref's sandbox with an account of your own |
| `ark-server.env` | Minting against an ARK server of your own |

```bash
cp environments/local-docker.env e2e.env    # read automatically
# or
WEKO_E2E_ENV=environments/fqdn.env ...      # name one per run
```

A variable set in the environment wins over the file, so a single value
can be overridden for one run. `e2ectl env` prints what a run would
actually use -- start there when something does not work.

```console
$ ../.venv-e2e/bin/python ./e2ectl env
environment file         /home/you/weko-workshop/e2e/environments/fqdn.env
base URL                 https://repository.example.org
host                     repository.example.org
host resolver rule       (DNS)
verify TLS               yes
account                  e2e-admin@example.org
item type                デフォルトアイテムタイプ（フル）
...
```

### A host name DNS does not know

WEKO builds its absolute URLs from the Host header, so a run has to
*browse* the host name the instance is configured for, even when only an
address answers. Say where to send it:

```bash
WEKO_BASE_URL=https://weko3.example.org
WEKO_E2E_HOST_IP=127.0.0.1
```

Both the browser and the HTTP client honour it, so this needs no
`/etc/hosts` entry and no root. A certificate for that name will not
verify, so leave `WEKO_E2E_VERIFY_TLS` off in that case.

## Running

```bash
cd e2e

# Check the settings, then that the instance answers and the account works.
../.venv-e2e/bin/python ./e2ectl env
../.venv-e2e/bin/python ./e2ectl ping

# Run the base test.
../.venv-e2e/bin/python -m pytest
```

Set `WEKO_HEADED=1` to watch the browser.

The account has to be a system administrator: the run creates an index, a
flow and a workflow, and approves its own activity.

## Choosing what runs

The base suite always runs. The others have to be asked for by name,
because each needs something of the instance that not every instance has.

| Suite | Checks | Needs |
| --- | --- | --- |
| (base) | index, workflow, item registration, publication | nothing beyond a working instance |
| `ark` | an ARK is minted for the item and becomes its permalink | an ARK server (`e2ectl ark-account enable`), or a stand-in (`e2ectl ark-stub enable`) |
| `crossref` | a Crossref DOI is granted to the item and becomes its permalink | nothing. Depositing to Crossref on top of that needs an account |

```bash
python -m pytest                      # the base suite; the others are skipped
python -m pytest --suite crossref     # and the Crossref suite
python -m pytest --suite all          # everything
WEKO_E2E_SUITES=ark,crossref python -m pytest   # the same, from the environment
```

A suite nobody asked for is **skipped, not hidden**, so a run always says
what it did not do and how to ask for it:

```
tests/test_ark_mint.py::test_01_login SKIPPED (optional suite 'ark' not
enabled; run with --suite ark or WEKO_E2E_SUITES=ark)
```

`--suite` adds to what `WEKO_E2E_SUITES` asked for rather than replacing
it, and each suite creates its own index, flow and workflow, so running
several in one session is no different from running them one at a time.

### The `ark` suite

WEKO mints an ARK when the Item Registration action completes, by calling
an ARK server, and only when the instance is configured for it: the mint
URL, the NAAN and the shoulder, and then either an API key or login
credentials. There is no admin screen for any of it; it is instance
configuration, so the tool writes it.

#### Against an ARK server of your own

```bash
# In an environment file (environments/ark-server.env is a copy to start
# from), or in the environment:
WEKO_E2E_ARK_MINT_URL=https://ark.example.org/api/mint
WEKO_E2E_ARK_NAAN=12345
WEKO_E2E_ARK_SHOULDER=x9
WEKO_E2E_ARK_API_KEY=...                 # or the three LOGIN settings

../.venv-e2e/bin/python ./e2ectl ark-account enable    # writes them, restarts
../.venv-e2e/bin/python -m pytest --suite ark
../.venv-e2e/bin/python ./e2ectl ark-account disable   # takes them away again
```

An API key is sent as `WEKO_E2E_ARK_API_KEY_HEADER` with
`WEKO_E2E_ARK_API_KEY_PREFIX` in front of it (`Authorization: Bearer ...`
by default; `X-API-Key` with an empty prefix for a raw key). Without a
key, WEKO logs in at `WEKO_E2E_ARK_LOGIN_URL` first and uses the token it
gets back -- `enable` writes whichever of the two is configured, and
refuses when neither is complete.

#### Against a stand-in, when there is no ARK server

```bash
../.venv-e2e/bin/python ./e2ectl ark-stub enable    # settings, restart, stub
WEKO_E2E_ARK_NAAN=99999 ../.venv-e2e/bin/python -m pytest --suite ark
../.venv-e2e/bin/python ./e2ectl ark-stub disable   # puts it all back
```

The stub is `weko_e2e/arkstub.py`, run on the loopback interface inside
the `web` container, which is where WEKO mints from -- nothing has to be
reachable over the network and no account anywhere is needed. It mints
`ark:/99999/fk4...`.

Both `enable`s add a marked block to the WEKO checkout's
`scripts/instance.cfg` -- the file the container renders its
`invenio.cfg` from, and where instance settings belong -- and restart
`web` and `worker`; the matching `disable` takes exactly that block away.
They set the same keys, so turning one on turns the other off. `status`
says where things stand.

A container restart takes the stub process with it; `ark-stub start`
puts it back without touching the configuration, and `ark-stub stop` is
the other way round.

Set `WEKO_E2E_ARK_NAAN` to have the suite check the ARK came out under
the NAAN this environment is configured for; without it, any ARK counts.

### The `crossref` suite

Granting needs nothing set up: the suite turns the Crossref grant on
under `/admin/identifier/`, sets the prefix to `WEKO_E2E_CROSSREF_PREFIX`
(`10.5555`, Crossref's documented example, by default), and **puts the
identifier settings back the way it found them** afterwards, pass or
fail -- it checks that it did, too.

```bash
../.venv-e2e/bin/python -m pytest --suite crossref
```

#### Depositing to Crossref

WEKO grants the DOI first and deposits to Crossref afterwards, through
the worker. The suite waits for that deposit and reports what Crossref
said, but only when this environment has an account: without one the last
two steps are skipped, which is the documented behaviour and not a
failure.

The credentials are instance settings -- WEKO has no admin screen for
them -- so the tool writes them:

```bash
# In an environment file, or in the environment:
WEKO_E2E_CROSSREF_DEPOSIT=1
WEKO_E2E_CROSSREF_LOGIN_ID=you@example.org/role
WEKO_E2E_CROSSREF_LOGIN_PASSWD=...
WEKO_E2E_CROSSREF_DEPOSITOR_EMAIL=you@example.org
WEKO_E2E_CROSSREF_PREFIX=10.80000        # a prefix that account may use

../.venv-e2e/bin/python ./e2ectl crossref-account enable   # writes them, restarts
../.venv-e2e/bin/python -m pytest --suite crossref
../.venv-e2e/bin/python ./e2ectl crossref-account disable  # takes them away again
```

Deposits go to **Crossref's test system**,
`https://test.crossref.org/servlet/deposit`, which is what WEKO defaults
to; `WEKO_E2E_CROSSREF_DEPOSIT_URL` and
`WEKO_E2E_CROSSREF_SUBMISSION_LOG_URL` point them somewhere else. The
prefix has to be one the account is allowed to register under, so
`10.5555` will not do once depositing is on.

`enable` adds a marked block to the WEKO checkout's
`scripts/instance.cfg` and restarts `web` and `worker`, the same way
`ark-stub` does; `disable` takes exactly that block away. `status` says
where things stand, and `e2ectl doi-log` shows what WEKO has sent.

The deposit is read from `doi_deposit_log` inside the `web` container, so
these two steps need the WEKO checkout; they skip without it. A deposit
that Crossref refuses fails the step with the reason Crossref gave.

## What the base suite does

| Step | |
| --- | --- |
| 01 | Log in as a system administrator |
| 02 | Create the test index and publish it |
| 03 | Define the test flow (Start / Item Registration / Item Link / Identifier Grant / Approval / End) |
| 04 | Define the test workflow (default full item type + that flow) |
| 05 | Start an activity on that workflow |
| 06 | Attach a file and fill the required metadata (publication date, title, resource type) |
| 07 | Designate the index |
| 08 | Link no other item, and move on |
| 09 | Grant no identifier (Not Grant), and move on |
| 10 | Approve, which is what registers and publishes the item |
| 11 | The item exists, under the title the run gave it |
| 12 | A visitor who has not logged in can see it, so it is published |
| 13 | Search finds it in that index, so the worker and Elasticsearch are doing their job |

What running it against a real instance showed:

- A newly created index is **private**, so step 02 publishes it. Without
  that, step 12 -- the anonymous visitor -- fails.
- A workflow that names an index (`create_workflow(index_id=...)`)
  designates it by itself, and **the index designation screen of step 07
  never appears**. The base test leaves the index unset, as the shipped
  workflows do, and designates it on the screen.
- The 13 steps take about 60 to 110 seconds, depending on the instance.

## Cleaning up (the tool)

A run leaves what it created **in place** by default, so that a failure can
be looked at in the browser. `e2ectl` is what removes it.

```bash
cd e2e

# What is still there.
../.venv-e2e/bin/python ./e2ectl status

# Delete everything in the ledger, the way the screens do.
../.venv-e2e/bin/python ./e2ectl clean

# Just one run.
../.venv-e2e/bin/python ./e2ectl clean --run 20260916-120000

# Say what would be deleted, delete nothing.
../.venv-e2e/bin/python ./e2ectl clean --dry-run

# Also remove the rows WEKO only marks deleted (runs the purge in the container).
../.venv-e2e/bin/python ./e2ectl clean --hard

# Ledger lost: find the leftovers by name (anything starting with the label).
../.venv-e2e/bin/python ./e2ectl clean --discover --hard
```

WEKO's own delete is logical for all of them -- index, workflow, flow and
item keep their row and only disappear from the screens. Use `clean` when
the screens being clean is enough, and `--hard` to get back to how
`install.sh` left the database.

`--hard` is the only part that needs docker: it copies `weko_e2e/purge.py`
into the `web` container and runs it with `invenio shell`. It therefore
needs the WEKO checkout that owns the compose file. That checkout is found
automatically when it sits next to this repository and is named `wekov2`,
`weko3` or `weko`; otherwise set `WEKO_E2E_REPO`. `e2ectl ping` says
whether it was found. Everything else -- running the tests, `clean`,
`status` -- works against a remote instance with no docker at all.

`--hard` follows a workflow to its activities, and an activity to the draft
item it was working on. The activity list screen does not show the activity
id unless the instance is configured to, so an activity cannot be found
over HTTP -- `--hard` is what reliably removes the draft a run that failed
half way left behind.

To clean up as part of the run, ask pytest:

```bash
../.venv-e2e/bin/python -m pytest --clean-after          # clean at the end
../.venv-e2e/bin/python -m pytest --clean-after --clean-hard
```

## Settings (environment variables)

Every one of these can also be a line in an environment file.

### The instance

| Variable | Default | |
| --- | --- | --- |
| `WEKO_BASE_URL` | `https://localhost` | The instance under test |
| `WEKO_E2E_HOST_IP` | (empty) | Send that host name to this address, for the browser and the HTTP client both |
| `WEKO_HOST_MAP` | (empty) | A chromium host resolver rule written out in full, e.g. `MAP weko3.example.org 127.0.0.1`; wins over `WEKO_E2E_HOST_IP` |
| `WEKO_E2E_VERIFY_TLS` | off | Verify the certificate. Turn it on for an instance with a real one |

### The account

| Variable | Default | |
| --- | --- | --- |
| `WEKO_TEST_EMAIL` | `wekosoftware@nii.ac.jp` | A system administrator |
| `WEKO_TEST_PASSWORD` | `uspass123` | |

### What the run makes

| Variable | Default | |
| --- | --- | --- |
| `WEKO_E2E_LABEL` | `E2E` | Prefix every created resource carries; what `--discover` looks for. Give each person their own on a shared instance |
| `WEKO_E2E_ITEM_TYPE` | `デフォルトアイテムタイプ（フル）` | Item type the run registers on |
| `WEKO_E2E_RUN_ID` | the current time | Identifier of one run; it goes into every resource name |
| `WEKO_E2E_STATE` | `e2e/.e2e-state.json` | Where the ledger lives |

### Patience

| Variable | Default | |
| --- | --- | --- |
| `WEKO_E2E_TIMEOUT` | `60000` | Milliseconds for one browser action |
| `WEKO_E2E_STEP_TIMEOUT` | `300` | Seconds to wait for a workflow step |
| `WEKO_E2E_UPLOAD_TIMEOUT` | `180` | Seconds to wait for a file upload |
| `WEKO_E2E_SEARCH_TIMEOUT` | `180` | Seconds to wait for Elasticsearch to catch up |

### The optional suites

| Variable | Default | |
| --- | --- | --- |
| `WEKO_E2E_SUITES` | (none) | Optional suites to run: `ark`, `crossref`, several separated by commas, or `all` |
| `WEKO_E2E_CROSSREF_PREFIX` | `10.5555` | Prefix the `crossref` suite configures and expects |
| `WEKO_E2E_ARK_NAAN` | (empty) | NAAN the `ark` suite expects the minted ARK to be under, and mints under |

### The ARK server (minting)

| Variable | Default | |
| --- | --- | --- |
| `WEKO_E2E_ARK_MINT_URL` | (empty) | Where the ARK is minted |
| `WEKO_E2E_ARK_NAAN` | (empty) | NAAN to mint under |
| `WEKO_E2E_ARK_SHOULDER` | (empty) | Shoulder to mint under |
| `WEKO_E2E_ARK_API_KEY` | (empty) | API key; when set, no login is made |
| `WEKO_E2E_ARK_API_KEY_HEADER` | `Authorization` | Header the key goes in |
| `WEKO_E2E_ARK_API_KEY_PREFIX` | `Bearer ` | What goes in front of the key; empty for a raw key |
| `WEKO_E2E_ARK_LOGIN_URL` | (empty) | Where to log in, when there is no API key |
| `WEKO_E2E_ARK_LOGIN_USER` | (empty) | |
| `WEKO_E2E_ARK_LOGIN_PASSWD` | (empty) | |
| `WEKO_E2E_ARK_TIMEOUT` | `30` | Seconds to wait for the ARK server |

These are written into the instance by `e2ectl ark-account enable`;
setting them alone changes nothing on the instance.

### The Crossref account (depositing)

| Variable | Default | |
| --- | --- | --- |
| `WEKO_E2E_CROSSREF_DEPOSIT` | off | Wait for the deposit and check its outcome |
| `WEKO_E2E_CROSSREF_LOGIN_ID` | (empty) | Crossref login, `user@example.org/role` when the account has roles |
| `WEKO_E2E_CROSSREF_LOGIN_PASSWD` | (empty) | |
| `WEKO_E2E_CROSSREF_DEPOSITOR_EMAIL` | (empty) | Where Crossref mails the outcome |
| `WEKO_E2E_CROSSREF_DEPOSITOR_NAME` | `WEKO E2E` | |
| `WEKO_E2E_CROSSREF_REGISTRANT` | `WEKO E2E` | |
| `WEKO_E2E_CROSSREF_DEPOSIT_URL` | `https://test.crossref.org/servlet/deposit` | Crossref's test system |
| `WEKO_E2E_CROSSREF_SUBMISSION_LOG_URL` | `https://test.crossref.org/servlet/submissionDownload` | Where the outcome is read from |
| `WEKO_E2E_CROSSREF_DEPOSIT_TIMEOUT` | `600` | Seconds to wait for Crossref to answer |

These are written into the instance by `e2ectl crossref-account enable`;
setting them alone changes nothing on the instance.

### `clean --hard` only

| Variable | Default | |
| --- | --- | --- |
| `WEKO_E2E_REPO` | found automatically | The WEKO checkout that owns the compose file |
| `WEKO_E2E_COMPOSE_FILE` | `docker-compose2.yml` | |
| `WEKO_E2E_WEB_SERVICE` | `web` | Compose service running WEKO |
| `WEKO_E2E_CONTAINER_REPO` | `/code` | Where the WEKO checkout is mounted in that container |

### Other

| Variable | Default | |
| --- | --- | --- |
| `WEKO_E2E_ENV` | `e2e/e2e.env` if it exists | Environment file to read |
| `WEKO_HEADED` | off | Watch the browser |

## Environments this has been run against

| | Result |
| --- | --- |
| `https://localhost`, local docker stack from `install.sh` | 13 passed |
| `https://weko3.example.org` with `WEKO_E2E_HOST_IP=127.0.0.1`, no DNS entry | 13 passed |
| The same, as a different system administrator account | 13 passed |
| All three suites in one session (`--suite all`, with the ARK stub) | 27 passed |
| `crossref` with depositing on, against a stand-in for Crossref | 10 passed; deposit reached `success` |
| `ark` against a server configured with `ark-account` (login flow) | 6 passed; minted `ark:/12345/x9...` |

## Deriving a suite from this one

The base test is setup (02-04) and then the flow (05-13); the setup is made
of `weko_e2e.client` and the flow of `weko_e2e.ui`. Add a file under
`tests/` and change only what needs changing.

- **Another item type** -- set `WEKO_E2E_ITEM_TYPE`. The metadata form
  control names contain the item type id, so rewrite what
  `_title_field()` and friends in `test_basic_publish.py` build.
- **Another flow** -- pass your own action names to
  `client.create_flow(name, actions=[...])` (`Start` and `End` are
  required).
- **Another identifier** -- `flow.choose_identifier_grant(page, settings,
  value=...)`: `0` Not Grant, `1` JaLC DOI, `2` Crossref DOI, `3`
  DataCite DOI. `tests/test_crossref_doi.py` is the worked example,
  including turning the grant on and putting the setting back.
- **A new optional suite** -- mark the module
  `pytestmark = pytest.mark.suite('name')`, add the name to
  `OPTIONAL_SUITES` in `weko_e2e/config.py`, and build the flow out of
  `weko_e2e.flow`. Resource names are scoped per suite automatically, so
  it can run alongside the others.
- **Another visibility** -- `client.create_index(..., public=False)` in
  step 02, and invert what step 12 expects.
- **Let the workflow designate the index** -- pass
  `index_id=flow_state['index_id']` in step 04. The index designation
  screen then does not appear, so drop step 07 and the
  `wait_for_index_tree()` call in step 06.

Record everything you create with `record(kind, id, name)`. `e2ectl` can
only delete what is in the ledger, and what `--discover` finds.

## When it does not work

- **Anything unexpected** -- `./e2ectl env` first: most of it is a setting
  pointing somewhere other than where you think.
- **`e2ectl ping` says "does not answer"** -- for a local stack, check the
  containers with `docker compose -f docker-compose2.yml ps`; for a host
  name DNS does not know, set `WEKO_E2E_HOST_IP`.
- **`ping` logs in but the item type is NOT FOUND** -- the instance has
  other item types; `ping` lists them, set `WEKO_E2E_ITEM_TYPE` to one.
- **Item registration stops at Next, or the file upload answers 500** --
  one case we have seen: `user_activity_logs` is partitioned by month, and
  without a partition for the current month every request that writes a
  log fails. Create it:
  ```sql
  CREATE TABLE user_activity_logs_YYYYMM PARTITION OF user_activity_logs
      FOR VALUES FROM ('YYYY-MM-01') TO ('YYYY-MM+1-01');
  ```
- **Only step 13 fails** -- the worker is not running, or the instance is
  slower than `WEKO_E2E_SEARCH_TIMEOUT`.
- **Steps time out on a remote instance** -- raise `WEKO_E2E_TIMEOUT` and
  `WEKO_E2E_STEP_TIMEOUT`; `environments/fqdn.env` has values to start
  from.
- **An activity from an earlier run blocks the new one** -- step 05 quits
  an activity left open by itself; to remove it,
  `./e2ectl clean --discover`.
- **The `ark` suite says no ARK was minted** -- the instance is not
  configured for ARK, or the mint call failed. Check
  `./e2ectl ark-account status` (or `ark-stub status`), and the `web` log
  for what the mint said; WEKO logs the reason and carries on registering
  the item rather than failing it.
- **The `crossref` suite says the grant is not offered** -- the identifier
  settings could not be saved; open `/admin/identifier/` and look.
- **The deposit steps skip** -- `WEKO_E2E_CROSSREF_DEPOSIT` is off, or the
  WEKO checkout was not found; `./e2ectl env` says which.
- **WEKO recorded no deposit** -- the account is not in the instance
  configuration: `./e2ectl crossref-account status`, and check the worker
  is running.
- **Crossref refused the deposit** -- the step prints what Crossref said.
  A prefix the account may not register under is the usual reason;
  `./e2ectl doi-log` shows the deposits and their errors.

## The last run

The report and the screenshots are in
[`evidence/README.md`](evidence/README.md). The test takes the screenshots
itself as it goes, so re-running it refreshes the whole of
`evidence/images/`.
