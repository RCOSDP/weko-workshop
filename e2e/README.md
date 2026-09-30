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
| `tests/test_coar_notify.py` | Optional suite `coarnotify`: the workflow is announced over COAR Notify |
| `tests/test_crossref_doi.py` | Optional suite `crossref`: a Crossref DOI is granted |
| `conftest.py` | The browser, the HTTP client and the ledger the run shares |
| `weko_e2e/flow.py` | The registration flow every suite walks |
| `weko_e2e/arkstub.py` | A stand-in ARK server, for the `ark` suite |
| `weko_e2e/notify.py` | Reading what the instance announced over COAR Notify |
| `weko_e2e/pushstub.py` | A stand-in browser subscription, for the web push steps |
| `weko_e2e/config.py` | The settings, read from the environment or an environment file |
| `weko_e2e/doctor.py` | What "fit to be tested" means, as checks |
| `weko_e2e/dataload.py` | Taking the rows out of a dump, and leaving the rest of it |
| `weko_e2e/inspect.py` | What the instance looks like from inside, run in the `web` container |
| `weko_e2e/client.py` | HTTP client for the endpoints the screens call, for setup and teardown |
| `weko_e2e/ui.py` | Playwright helpers for walking an activity's screens |
| `weko_e2e/ledger.py` | The record of what a run created (`.e2e-state.json`) |
| `weko_e2e/purge.py` | The physical delete, copied into the `web` container and run there |
| `weko_e2e/inboxpurge.py` | The same for the LDN inbox, run in the `inbox` container |
| `weko_e2e/cli.py`, `e2ectl` | The tool |
| `environments/` | Environment files to copy and change |
| `evidence/` | The last run's report and its screenshots, one folder per optional suite |

## Setting up

```bash
# From the root of this repository.
python3 -m venv .venv-e2e
.venv-e2e/bin/pip install -r e2e/requirements.txt
.venv-e2e/bin/playwright install chromium
```

Python 3.10 or newer, which is what playwright and pytest ask for; the
suite's own code is not what needs it.

**On Windows**, a virtual environment keeps its programs in `Scripts`
rather than in `bin`, and `e2ectl` is handed to the interpreter rather
than run as a program. So, in PowerShell:

```powershell
py -3 -m venv .venv-e2e
.venv-e2e\Scripts\python -m pip install -r e2e\requirements.txt
.venv-e2e\Scripts\python -m playwright install chromium

cd e2e
..\.venv-e2e\Scripts\python .\e2ectl env
..\.venv-e2e\Scripts\python -m pytest
```

That is the whole of the difference: the suite itself -- the browser, the
HTTP, the tool -- does nothing that is not the same on either. The
commands below are written the Linux way; read `bin/python` as
`Scripts\python` and `./e2ectl` as `.\e2ectl` on Windows.
`./e2ectl package` builds an archive that carries a `setup.ps1` for it.

You also need a WEKO3 instance to test. For a local one, in a WEKO
checkout:

```bash
./install.sh
```

## Pointing it at an instance

Set the variables, or put them in an environment file. There are copies to
start from in [`environments/`](environments):

| File | For |
| --- | --- |
| `local-docker.env` | A stack `install.sh` brought up on this machine (also the defaults) |
| `fqdn.env` | An instance on a real host name with a real certificate |
| `fqdn-no-dns.env` | An instance published under a host name DNS does not know |
| `crossref-sandbox.env` | Depositing to Crossref's sandbox with an account of your own |
| `ark-server.env` | Minting against an ARK server of your own |
| `coar-notify.env` | The two accounts the COAR Notify suite works between |

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

# What a run would use, and whether the instance answers as that account.
../.venv-e2e/bin/python ./e2ectl env
../.venv-e2e/bin/python ./e2ectl ping

# The base flow. The run looks the instance over first, by itself.
../.venv-e2e/bin/python -m pytest

# Everything, once the two stand-ins are up (see the suites below).
../.venv-e2e/bin/python ./e2ectl ark-stub enable
../.venv-e2e/bin/python ./e2ectl webpush-stub enable
WEKO_E2E_ARK_NAAN=99999 ../.venv-e2e/bin/python -m pytest --suite all

# What the run created, and taking it away again.
../.venv-e2e/bin/python ./e2ectl status
../.venv-e2e/bin/python ./e2ectl clean --hard
```

What happens, in order:

1. **The instance is looked over.** Every run checks that what the suites
   depend on is there and **stops if it is not**, rather than failing a
   minute in for a reason that is not on screen. `--doctor-fix` repairs
   what can be repaired first; `--no-doctor` skips it. See
   [Is the instance fit to be tested?](#is-the-instance-fit-to-be-tested)
2. **The suites run.** The base flow always; the others only when asked
   for by name. See [Choosing what runs](#choosing-what-runs).
3. **What each step saw is written to `evidence/`** -- the screenshots,
   and the look from step 1. Re-running refreshes them in place.
4. **What the run created stays**, so that a failure can be looked at,
   until `clean` takes it away. `--clean-after --clean-hard` does that at
   the end of the run instead. See [Cleaning up](#cleaning-up-the-tool).

Set `WEKO_HEADED=1` to watch the browser.

The account has to be a system administrator: the run creates an index, a
flow and a workflow, and registers an item through them. The `coarnotify`
suite needs a second account to approve, which `WEKO_E2E_APPROVER_EMAIL`
names and `doctor` checks.

## Choosing what runs

The base suite always runs. The others have to be asked for by name,
because each needs something of the instance that not every instance has.

| Suite | Checks | Needs |
| --- | --- | --- |
| (base) | index, workflow, item registration, publication | nothing beyond a working instance |
| `ark` | an ARK is minted for the item and becomes its permalink | an ARK server (`e2ectl ark-account enable`), or a stand-in (`e2ectl ark-stub enable`) |
| `coarnotify` | the approval request and the approval are announced over COAR Notify, reach the people they are meant to, and arrive as a web push | an LDN inbox (the `inbox` service) and a second account to approve; the web push steps also want `e2ectl webpush-stub enable` |
| `crossref` | a Crossref DOI is granted to the item and becomes its permalink | nothing. Depositing to Crossref on top of that needs an account |

```bash
python -m pytest                      # the base suite; the others are skipped
python -m pytest --suite crossref     # and the Crossref suite
python -m pytest --suite all          # everything
WEKO_E2E_SUITES=ark,coarnotify python -m pytest # the same, from the environment
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

### The `coarnotify` suite

WEKO turns workflow events into COAR Notify messages and POSTs them to an
LDN inbox, which is a service of its own -- the `inbox` container in a
stack from `install.sh`. WEKO is only the sender; it reads them back for
the person they were addressed to at `GET /api/notifications`.

**Who receives what is the point.** WEKO leaves the person who acted out
of the notification about their own action, so a run in which one account
did everything would prove nothing. This suite therefore uses two
accounts and walks the loop between them:

| | | |
| --- | --- | --- |
| the registrant sends the item for approval | → | the approver is sent `Offer` + `EndorsementAction` |
| the approver approves it | → | the registrant is sent `Announce` + `EndorsementAction` |

Both are read the way a user reads them -- `GET /api/notifications` as
that user -- and then fetched from the inbox and checked field by field:
the `@context`, the `urn:uuid:` id, who it is addressed to, the item it
is about and the activity it belongs to. It also checks that the site
announces its inbox (`Link: rel="ldp#inbox"`, on a HEAD of the top page),
that a visitor who has not logged in gets a 401 rather than somebody's
notifications, and that the user has a screen for saying how they want to
be told.

```bash
../.venv-e2e/bin/python -m pytest --suite coarnotify
../.venv-e2e/bin/python ./e2ectl inbox --run <run id>   # what it announced
```

Nothing has to be configured on a stack from `install.sh`:
`WEKO_NOTIFICATIONS` is already on in `scripts/instance.cfg` and
`repoadmin@example.org` is the repository administrator every approval
request goes to. Where the approver is somebody else, set
`WEKO_E2E_APPROVER_EMAIL` and `WEKO_E2E_APPROVER_PASSWORD`;
`environments/coar-notify.env` is a copy to start from.

The notifications live in the inbox's own database, not in WEKO's, so
they do not go away when the WEKO database goes back to its baseline:
`clean --hard` clears the run's own out of the `inbox` container as well.

#### Web push

A notification can also reach the user as a Web Push. WEKO's part of that
is registering the subscription, the user's profile and the message
templates with the inbox; the inbox is what encrypts a notification for a
subscription and delivers it. The suite checks the whole of it: the push
arrives, is decrypted, and says what `push.json` says, rendered with this
item and this approver.

Two things are in the way of doing that for real, and `e2ectl
webpush-stub` deals with both. A real subscription comes from the
browser's own push service -- Google's or Mozilla's -- which a run
against a local stack cannot reach; and the shipped compose file leaves
the inbox's VAPID keys empty, so it would sign nothing anyway.

```bash
../.venv-e2e/bin/python ./e2ectl webpush-stub enable   # keys, recreate, stand-in
../.venv-e2e/bin/python -m pytest --suite coarnotify
../.venv-e2e/bin/python ./e2ectl webpush-stub disable  # puts it all back
```

`enable` generates a VAPID key pair, writes it into the WEKO checkout's
compose file between markers -- the keys belong to the `inbox` service
rather than to WEKO, which is why they are not in `instance.cfg` --
recreates the inbox so it reads them, and runs `weko_e2e/pushstub.py` on
the loopback interface of that container. The stand-in holds subscription
keys of its own, registers them with the inbox the way the notification
settings screen registers a real subscription, and decrypts what arrives
so the suite can read what a browser would have shown. `disable` takes
the block away and puts the original lines back; `status` says where
things stand, and `start` / `stop` are the stub process alone.

Without the stand-in the four web push steps skip, with the reason and
how to ask for them -- the same way the Crossref deposit does.

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

## Is the instance fit to be tested?

The suites assume an instance `install.sh` has just finished setting up.
When a piece of that is missing the failure usually lands somewhere
unhelpful -- an item registration that stops at Next, a search that finds
nothing -- so this is asked first.

**A run asks by itself.** Every `pytest` looks the instance over before
it starts, and stops rather than spending a minute or more finding out
the hard way:

```
https://localhost: 14 of 15 checks passed
  FAIL  this month's log partition
      there is no user_activity_logs_202609. WEKO writes a log row for most
      requests, so without it the file upload answers 500 and item
      registration stops at Next.

Exit: this instance is not in a state to be tested: this month's log
partition. Put it right with "./e2ectl doctor --fix", or run with
--no-doctor to go ahead anyway.
```

It costs about fifteen seconds -- most of it starting `invenio shell` in
the container -- and only a **failure** stops a run. A warning is
something one of the other suites wants, or somebody's leftovers, and
neither is this run's business; only the checks that matter to the suites
being run are looked at.

| Option | |
| --- | --- |
| `--no-doctor` | do not look at all |
| `--doctor-fix` | put right what can be put right, then run |
| `--doctor-fix-accounts` | with `--doctor-fix`, accounts and roles too |

```bash
python -m pytest --doctor-fix          # repair what is missing, then run
python -m pytest --no-doctor           # go ahead regardless
```

A run that stops this way exits 4, which is pytest's "usage error" --
distinct from the 1 a failing test gives, so a script can tell them
apart.

`e2ectl doctor` is the same thing on its own:

```bash
cd e2e
../.venv-e2e/bin/python ./e2ectl doctor        # what is wrong, if anything
../.venv-e2e/bin/python ./e2ectl doctor --verbose   # and what is right
```

```
https://localhost  (inspected)
ok    the instance answers
ok    the WEKO checkout
ok    the account logs in
...
FAIL  this month's log partition
      there is no user_activity_logs_202609. WEKO writes a log row for most
      requests, so without it the file upload answers 500 and item
      registration stops at Next.
warn  nothing left from an earlier run
      1 index left behind (E2E). A run does not collide with them -- every
      name carries its own run id -- but they are somebody's leftovers.

2 of these can be put right: run "doctor --fix"
```

It looks at eighteen things: that the instance answers and the account
logs in and administers; that the item type, the workflow actions, a flow
to copy from, an index tree, a file location, this month's log partition
and a registered language are all there; that search answers and the
worker is up; and, for the optional suites, the identifier settings row,
the approver and the inbox. It finishes by saying how far the instance is
from the baseline `install.sh` leaves.

A check marked `[crossref]` or `[coarnotify]` only matters to that suite,
and warns rather than fails.

### Repairing

```bash
../.venv-e2e/bin/python ./e2ectl doctor --fix                  # what can be filled in
../.venv-e2e/bin/python ./e2ectl doctor --fix --fix-accounts   # accounts and roles too
```

**Nothing here deletes.** The check itself only reads — a run that takes
it changes nothing on the instance — and every repair adds what is
missing and replaces nothing. A fault that could only be put right by
removing something is reported and left alone: whether an index called
`E2E ...` is an earlier run's leftover or somebody's work is not a thing
for a tool to guess at, and `clean --discover --hard` is there for when
you mean it.

The repairs:

| What is wrong | What `--fix` does |
| --- | --- |
| no partition for this month | `CREATE TABLE ... PARTITION OF user_activity_logs` |
| no workflow actions | `invenio workflow init action_status,Action` |
| no flow at all | adds the rows of `scripts/demo/defaultworkflow.sql` |
| an empty index tree | adds the rows of `scripts/demo/indextree.sql` |
| no identifier settings row | adds the rows of `scripts/demo/doi_identifier.sql` |
| no file location | creates one; **an instance that has one keeps it** |
| no language registered | `invenio language create --active --registered en English 001` |
| leftovers from an earlier run | `clean --discover --hard` |
| the item type under test is missing | adds the rows of `scripts/demo/item_type.sql` |
| the account or the approver is missing, or lacks its role | creates it and adds the role -- only with `--fix-accounts` |

### Adding rows without running the file

Four of those repairs load data `install.sh` loads, and none of them runs
the file. `scripts/demo/item_type.sql` is a dump, not a seed: it **drops
the item type tables** and builds them again before filling them, which
is right for an empty database and wrong for an instance with item types
of its own.

So `weko_e2e/dataload.py` reads out of each file only the statements that
*add* rows, and the repair runs those against the schema the instance
already has. Nothing is dropped, no constraint is altered, and every row
that was there stays exactly as it was.

Three things make that safe:

- **One transaction.** The rows carry the ids they insert. Where the
  instance is already using one of those ids the insert fails, the whole
  load is undone, and the tool says so -- there is no half-loaded item
  type.
- **Primary keys still apply.** The load puts foreign key checking aside
  for its own transaction (`session_replication_role`, which is what
  `pg_restore --disable-triggers` does) because a dump lists its rows in
  the order it wrote them rather than parent before child. Primary keys
  and unique constraints are not triggers, so they still stop a load
  landing on top of what is there.
- **Sequences only move forward.** A dump puts its sequences back where
  the dump ended; replaying that on an instance that has gone further
  would hand out ids it has already used, so each `setval` is rewritten
  to take the greater of the two.

An account that already exists keeps its password, in the same spirit:
`--fix-accounts` fills a gap, it does not take an instance's accounts
over.

Anything `--fix` will not touch is reported with what to run by hand. An
instance that is broken further than this is quicker to rebuild with
`install.sh`.

### Repairing an instance you cannot reach the containers of

`--fix` works through `docker compose`, so it is no use for an instance
somewhere else. `--sql` writes the same repairs out instead, to be taken
to whoever can run SQL on it:

```bash
WEKO_E2E_WEKO_REF=v2.0.4 ../.venv-e2e/bin/python ./e2ectl doctor --sql \
    > repair.sql
```

The reading of the instance goes to stderr and the script to stdout, so
that is a file which can be run rather than one that has to be edited
first. It is one transaction, it only adds rows, and a row whose id is
already in use undoes the whole of it -- the same properties `--fix` has.

**The version matters.** The rows are WEKO's own data, and an instance
built from an older WEKO wants that WEKO's: between `v2.0.3` and
`release_v2.1.0` the shipped item types go from 173 rows to 210.
`WEKO_E2E_WEKO_REF` is the branch, tag or commit to take them from, and
naming one is asking for it -- they are fetched from GitHub over HTTP
(nothing is cloned) and kept, so the second time needs no network.

| | |
| --- | --- |
| `e2ectl seed <ref>` | take a version now, to have it later |
| `e2ectl seed --list` | what has been taken |
| `e2ectl seed --from-checkout` | take it from the WEKO checkout here instead |
| `WEKO_E2E_WEKO_REPO_URL` | somewhere other than GitHub to take it from |

A package built after `seed` carries what was taken, so one can be handed
to somebody with the version their instance needs already in it, for a
machine with no network.

`doctor` exits non-zero when something failed, so it works as a gate in
front of a run.

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
into the `web` container and runs it with `invenio shell`, and
`weko_e2e/inboxpurge.py` into the `inbox` container to take the run's
COAR Notify notifications out of the inbox's own database. It therefore
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

## Handing it to somebody else

```bash
cd e2e
../.venv-e2e/bin/python ./e2ectl package
```

A zip of the suite and the tool, for somebody who has not got this
repository — `weko-e2e-<date>.zip`, about 370 kB. Unpack it and run
`./setup.sh`, which makes the Python environment and installs chromium;
the commands in it are the same ones this file gives, because the package
keeps the same shape.

What goes in is **named rather than filtered**, so that the things which
must not travel cannot do so by accident: `e2e.env` is somebody's own
settings and may hold a Crossref password or an ARK key, `.e2e-state.json`
is one instance's ledger, and `evidence/` is three megabytes of
screenshots of a run the reader did not make. A list of what to leave out
would let the next file added here ship by mistake; a list of what to
take cannot.

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
| `WEKO_E2E_APPROVER_EMAIL` | `repoadmin@example.org` | Somebody else, for the `coarnotify` suite to have approve |
| `WEKO_E2E_APPROVER_PASSWORD` | `uspass123` | |

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
| `WEKO_E2E_SUITES` | (none) | Optional suites to run: `ark`, `coarnotify`, `crossref`, several separated by commas, or `all` |
| `WEKO_E2E_CROSSREF_PREFIX` | `10.5555` | Prefix the `crossref` suite configures and expects |
| `WEKO_E2E_ARK_NAAN` | (empty) | NAAN the `ark` suite expects the minted ARK to be under, and mints under |
| `WEKO_E2E_NOTIFY_TIMEOUT` | `120` | Seconds the `coarnotify` suite waits for a notification to reach the inbox |

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
| `WEKO_E2E_INBOX_SERVICE` | `inbox` | Compose service running the LDN inbox: cleared of the run's notifications, and where the web push stand-in runs |
| `WEKO_E2E_DB_SERVICE` | `postgresql` | Compose service running the database, which `doctor --fix` applies SQL through |
| `WEKO_E2E_DB_USER` | `invenio` | |
| `WEKO_E2E_DB_NAME` | `invenio` | |
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
| All four suites in one session (`--suite all`, with the ARK stub) | 37 passed |
| `crossref` with depositing on, against a stand-in for Crossref | 10 passed; deposit reached `success` |
| `coarnotify` against the stack's own `inbox` service | 10 passed; both notifications reached the right account |
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

- **The browser will not start: `error while loading shared libraries`**
  -- playwright fetches chromium but not the system libraries it links
  against, so the browser is there and cannot run. On Debian and Ubuntu,
  `.venv-e2e/bin/playwright install --with-deps chromium` as root
  installs them. **On RHEL, Rocky and Alma that does not work** --
  `install-deps` shells out to `apt-get` -- so install them by hand:
  ```bash
  sudo dnf install -y nss nspr atk at-spi2-atk at-spi2-core cups-libs \
      libdrm libxkbcommon libXcomposite libXdamage libXext libXfixes \
      libXrandr libXi libXrender mesa-libgbm pango cairo alsa-lib
  ```
  The `setup.sh` in `e2ectl package`'s archive starts the browser once
  before it finishes, so a package sets up or says this; a venv built by
  hand from this README does not, and finds out during the first run.
- **Anything unexpected** -- `./e2ectl doctor` first, then `./e2ectl env`:
  between them they cover both halves of it, the instance not being in a
  fit state and a setting pointing somewhere other than where you think.
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
- **The `coarnotify` suite says nothing was offered to the approver** --
  the `inbox` container is not up (`docker compose -f docker-compose2.yml
  ps inbox`), `WEKO_NOTIFICATIONS` is off in `scripts/instance.cfg`, or
  the approver is not the account this instance sends approval requests
  to. `./e2ectl inbox` shows what each account has been sent.
- **The `coarnotify` suite says the approver is not shown the approval
  screen** -- the account is not allowed to approve on this instance, or
  it is still holding an activity an earlier run left open; the suite
  releases that hold itself, and `./e2ectl clean --discover` removes the
  activity.
- **The web push steps skip** -- no stand-in is running;
  `./e2ectl webpush-stub enable` sets one up and
  `./e2ectl webpush-stub status` says where things stand. They also skip
  without the WEKO checkout, because the stand-in lives in the `inbox`
  container.
- **The announcement arrives but the push does not** -- the inbox sends
  in a background task and only writes a failure to its log, so look
  there (`docker compose -f docker-compose2.yml logs inbox`). It needs
  three things for one push: a subscription, a user profile for the same
  URI, and a template whose `type` matches the notification. The
  stand-in registers the first two; WEKO registers the third from
  `push.json` when it first starts, so an instance that has not been
  restarted since that file changed still has the old text.
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

[`evidence/README.md`](evidence/README.md) is the run, the base flow and
the cleaning up. Each optional suite has a report of its own, beside the
screenshots it is written from:

```
evidence/
├── README.md, README.ja.md      the run, and the base flow
├── doctor.md                    what the instance looked like beforehand
├── images/                      what the base flow's steps photographed
├── ark/README.md, images/       the ark suite, and its own screenshots
├── coarnotify/README.md, …
└── crossref/README.md, …
```

The tests take the screenshots themselves as they go, under fixed names,
and the run writes `doctor.md` before its first test, so re-running
refreshes both in place and the report cannot drift from the code.
