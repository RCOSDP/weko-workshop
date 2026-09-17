# E2E test run report (the base flow)

日本語版: [`README.ja.md`](README.ja.md)

A record of running [`../tests/test_basic_publish.py`](../tests/test_basic_publish.py)
against an instance brought up by `install.sh`. The test takes the
screenshots itself as it goes, so re-running it refreshes them in place and
this report cannot drift from the code.

## Result

| | |
| --- | --- |
| Run at | 2026-09-17 22:55:32 – 22:59:46 (UTC) |
| Run id | `20260917-225532` |
| Result | **27 passed, 2 skipped** (253.72 s) |
| Against | `https://localhost` (`install.sh` / `docker-compose2.yml`) |
| Suites | base, `ark` (against the stand-in ARK server), `crossref` |
| Cleaned up with | `./e2ectl clean --hard`; the database went back to how `install.sh` left it |

```
============================= test session starts ==============================
platform linux -- Python 3.11.12, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/mhaya/weko-workshop/e2e
configfile: pytest.ini
collected 13 items

tests/test_basic_publish.py::test_01_login PASSED
tests/test_basic_publish.py::test_02_create_index PASSED
tests/test_basic_publish.py::test_03_define_flow PASSED
tests/test_basic_publish.py::test_04_define_workflow PASSED
tests/test_basic_publish.py::test_05_start_activity PASSED
tests/test_basic_publish.py::test_06_register_metadata PASSED
tests/test_basic_publish.py::test_07_designate_index PASSED
tests/test_basic_publish.py::test_08_item_link PASSED
tests/test_basic_publish.py::test_09_identifier_grant PASSED
tests/test_basic_publish.py::test_10_approve PASSED
tests/test_basic_publish.py::test_11_record_is_registered PASSED
tests/test_basic_publish.py::test_12_record_is_public PASSED
tests/test_basic_publish.py::test_13_record_is_in_index PASSED

tests/test_ark_mint.py::test_01_login PASSED
tests/test_ark_mint.py::test_02_set_up PASSED
tests/test_ark_mint.py::test_03_register_item PASSED
tests/test_ark_mint.py::test_04_ark_was_minted PASSED
tests/test_ark_mint.py::test_05_ark_is_the_permalink PASSED
tests/test_ark_mint.py::test_06_ark_is_published PASSED

tests/test_crossref_doi.py::test_01_prefix_is_set PASSED
tests/test_crossref_doi.py::test_02_set_up PASSED
tests/test_crossref_doi.py::test_03_register_item PASSED
tests/test_crossref_doi.py::test_04_choose_crossref_grant PASSED
tests/test_crossref_doi.py::test_05_approve PASSED
tests/test_crossref_doi.py::test_06_doi_was_granted PASSED
tests/test_crossref_doi.py::test_07_doi_is_the_permalink PASSED
tests/test_crossref_doi.py::test_08_doi_is_published PASSED
tests/test_crossref_doi.py::test_09_deposit_was_recorded SKIPPED
tests/test_crossref_doi.py::test_10_deposit_reached_crossref SKIPPED

============ 27 passed, 2 skipped, 12 warnings in 253.72s (0:04:13) ============
```

The two skips are the Crossref deposit: this instance was given no
Crossref account, so WEKO grants the DOI and sends nothing, which is the
documented behaviour. The deposit path is verified separately, below.

The warnings are all `InsecureRequestWarning` for the self signed
certificate, and say nothing about the behaviour under test.

## The environment

```
suite     : weko-workshop  main  4b196dd
WEKO      : wekov2  feature/nii_WACREN_crossref_doi  a3e62bb4e
python    : 3.11.12 (the side running the tests)
playwright: 1.63.0 / chromium-1243
pytest    : 9.1.1
requests  : 2.34.2 / beautifulsoup4 4.15.0
```

| Service | Image | State |
| --- | --- | --- |
| web | wekov2-web | Up |
| worker | wekov2-worker | Up |
| nginx | wekov2-nginx | Up |
| elasticsearch | wekov2-elasticsearch | Up |
| postgresql | postgres:12 | Up |
| pgpool | pgpool/pgpool:4.2.2 | Up |
| redis | redis:7.4.1 | Up |
| rabbitmq | rabbitmq:4.0.2 | Up |
| mongo | mongo:7.0.14 | Up |
| inbox | wekov2-inbox | Up |
| flower | mher/flower:0.9.5 | Up |

What this run created -- five resources per suite, named apart so that
three suites can share one session:

| Suite | index | flow / workflow | activity | item |
| --- | --- | --- | --- | --- |
| base | `1789685805378` | `9c280c40…` / `64a76a31…` | `A-20260917-00038` | `2000038` |
| `ark` | `1789685738011` | `8d54c78d…` / `25e54e7a…` | `A-20260917-00037` | `2000037` |
| `crossref` | `1789685904514` | `e0613f20…` / `8afac721…` | `A-20260917-00039` | `2000039` |

The identifiers the optional suites were after:

| | |
| --- | --- |
| ARK minted | `ark:/99999/fk400003` |
| Crossref DOI granted | `10.5555/0002000039` |

---

## The base suite, step by step

### 01. Log in (test_01_login)

As the system administrator `wekosoftware@nii.ac.jp`.

![The front page after logging in](images/01-logged-in.png)

### 02. Create the test index (test_02_create_index)

Create the index and publish it. The admin Index Tree shows
`E2E Index 20260917-225532` next to the shipped `Sample Index`.

A newly created index is private, which is why this step publishes it;
without that, step 12 fails.

![The new index in Edit Tree](images/02-index-created.png)

### 03. Define the test flow (test_03_define_flow)

Six actions in order: Start / Item Registration / Item Link / Identifier
Grant / Approval / End. The flow's status is `Available`.

![The flow with its six actions](images/03-flow-defined.png)

### 04. Define the test workflow (test_04_define_workflow)

The item type デフォルトアイテムタイプ（フル） together with the flow from
step 03. **No index is designated** on the workflow: one that names an
index designates it by itself and the screen in step 07 never appears.

![The workflow](images/04-workflow-defined.png)

### 05. Start the activity (test_05_start_activity)

The workflow appears in the list of workflows an activity can start on.

![The workflow list](images/05-workflow-list.png)

Starting it opens the activity on Item Registration.

![The activity, just started](images/06-activity-started.png)

### 06. Fill the metadata (test_06_register_metadata)

Attach the sample PDF and fill what this item type requires: PubDate,
Title and Resource Type.

![The metadata form, filled in](images/07-item-metadata.png)

### 07. Designate the index (test_07_designate_index)

Tick `E2E Index 20260917-225532` in the index tree; DESIGNATE INDEX shows
it.

![The index designated](images/08-index-designated.png)

### 08. Item link (test_08_item_link)

Link no other item, and move on.

![The item link screen](images/09-item-link.png)

### 09. Identifier grant (test_09_identifier_grant)

The base test grants no DOI; `Not Grant` is what is selected. A DOI
belongs in a derived suite -- there is a worked example in
`works/crossref-doi-manual/e2e/`.

![Not Grant selected](images/10-identifier-grant.png)

### 10. Approve, which publishes (test_10_approve)

The approval screen.

![The approval screen](images/11-approval.png)

Approving takes the activity to End: all six actions Done, and the history
running from Start to End. This is where the item is registered and
published.

![After approval: status End, every action Done](images/12-approved.png)

### 11. The item is registered (test_11_record_is_registered)

`/records/2000038` exists and shows the title the run registered.

![The item page, as the administrator](images/13-record-page.png)

### 12. The item is published (test_12_record_is_public)

The same page from a browser context that has **never logged in** -- note
`Log in` in the top right. The title, the file and the item type
デフォルトアイテムタイプ（フル） are all there, which is what "published"
means.

![The item page, anonymous](images/14-record-page-anonymous.png)

### 13. Search finds it (test_13_record_is_in_index)

Still anonymous, search the index the run created: `Found 1 result.`
Indexing is asynchronous, so this is the one step that waits -- up to three
minutes -- and it is also what shows the worker and Elasticsearch are
doing their job.

![Searching the index, anonymous](images/15-search-in-index.png)

---

## The `ark` suite

Run against the stand-in ARK server -- `e2ectl ark-stub enable` -- because
this instance has no ARK server of its own. The same suite run against a
real one, configured with `e2ectl ark-account enable`, is what the
"Other environments" table below records.

### Register an item, granting no DOI (test_03)

The ARK is minted on the way through, when Item Registration completes,
so nothing on screen asks for one.

![The approval screen of the ARK run](images/ark-02-approval.png)

![After approval](images/ark-03-approved.png)

### The item carries an ARK (test_04, test_05)

The permalink of an item with no DOI and no CNRI is its ARK, so the
record page is where a minted ARK shows up -- here `ark:/99999/fk400003`,
under the NAAN this environment was configured for.

![The record page, showing the ARK as its permalink](images/ark-04-record-page.png)

---

## The `crossref` suite

### The prefix is configured (test_01)

The suite turns the Crossref grant on and sets the prefix, and puts both
back the way it found them when it is done.

![The identifier settings with the prefix set](images/crossref-01-identifier-settings.png)

### The metadata a deposit needs (test_03)

Crossref will not take a journal article without the journal, its ISSN
and the date it was issued, so the suite fills those in where the base
flow does not.

![The metadata form with the journal fields filled in](images/crossref-02-item-metadata.png)

### The Crossref grant is offered, and taken (test_04)

![The identifier grant screen offering the Crossref DOI](images/crossref-03-grant-chosen.png)

### Approve, and read the DOI (test_05 to test_08)

![The approval screen](images/crossref-04-approval.png)

![After approval](images/crossref-05-approved.png)

The item carries `10.5555/0002000039`, under the prefix the suite
configured, and shows it as its permalink.

![The record page, showing the DOI](images/crossref-06-record-page.png)

### The deposit (test_09, test_10)

Skipped here, for want of an account. Verified separately against a
stand-in for Crossref, which is what showed the whole path works:

```
granted DOI: 10.5555/0002000032
deposit: {'id': 1, 'agency': 'Crossref', 'status': 'submitted', 'attempt': 1,
          'poll': 0, 'http': 200, 'tracking_id': 'weko-82309c1d…-20260917222135'}
deposit: {'id': 1, 'agency': 'Crossref', 'status': 'success', 'attempt': 1,
          'poll': 1, 'http': 200, 'error': 'Crossref registered the DOI.'}
→ 10 passed
```

With `WEKO_E2E_CROSSREF_DEPOSIT` set and an account written into the
instance by `e2ectl crossref-account enable`, those two steps wait for
the worker to deposit and report what Crossref said.

---

## Cleaning up

A run leaves what it created in place by default, so that a failure can be
looked at. The ledger says what is still there.

```console
$ ./e2ectl status          # the run_id on the Settings line is this call's, not the run's
Settings(base_url='https://localhost', run_id='20260917-225955', label='E2E')
ledger: /home/mhaya/weko-workshop/e2e/.e2e-state.json
  run 20260917-225532  started 2026-09-17T22:55:38  15 resource(s)
    index     1789685738011            E2E Index 20260917-225532-ark
    flow      8d54c78d-bb42-43cf-9eb1-a3c4c60bd08e E2E Flow 20260917-225532-ark
    workflow  25e54e7a-2163-4a99-9f1f-75716613c215 E2E Workflow 20260917-225532-ark
    activity  A-20260917-00037         E2E Workflow 20260917-225532-ark
    item      2000037                  E2E item 20260917-225532-ark
    index     1789685805378            E2E Index 20260917-225532
    ...                                (the base suite's five)
    index     1789685904514            E2E Index 20260917-225532-crossref
    ...                                (the crossref suite's five)
```

```console
$ ./e2ectl clean --hard
deleted  item 2000037 E2E item 20260917-225532-ark
deleted  item 2000038 E2E item 20260917-225532
deleted  item 2000039 E2E item 20260917-225532-crossref
deleted  activity A-20260917-00037 ...
deleted  workflow 25e54e7a-2163-4a99-9f1f-75716613c215 ...
deleted  flow 8d54c78d-bb42-43cf-9eb1-a3c4c60bd08e ...
deleted  index 1789685738011 E2E Index 20260917-225532-ark
deleted  index 1789685805378 E2E Index 20260917-225532
deleted  index 1789685904514 E2E Index 20260917-225532-crossref
hard purge: docker compose -f docker-compose2.yml exec -T web invenio shell /tmp/weko-e2e-purge.py /tmp/weko-e2e-purge.json
purged items: 2000037, 2000038, 2000039
purged activities: A-20260917-00037, A-20260917-00038, A-20260917-00039
purged workflows: 25e54e7a-..., 64a76a31-..., 8afac721-...
purged flows: 8d54c78d-..., 9c280c40-..., e0613f20-...
purged indexes: 1789685738011, 1789685805378, 1789685904514
```

### What the database gained, and gave back

Measured against how `install.sh` leaves it -- one sample index, one
default flow, two default workflows -- everything the run added is gone
after `--hard`, and nothing else with it.

| | index | flow | workflow | activity | records | bucket |
| --- | --- | --- | --- | --- | --- | --- |
| Before the run | 1 | 1 | 2 | 0 | 0 | 0 |
| After the run | 4 | 4 | 5 | 3 | 6 | 6 |
| After `clean --hard` | **1** | **1** | **2** | **0** | **0** | **0** |

Three of each, one per suite. Two records per item, because WEKO keeps
an item as a version-less record and a Ver.1 record. The pid store came
back to 0 rows as well, granted DOI and minted ARK included.

The item's page is gone too.

```console
$ curl -s -o /dev/null -w '%{http_code}\n' --insecure https://localhost/records/2000038
404
```

## Other environments

The same suite, unchanged, was run against the same instance reached in
different ways. This is what the settings are for: nothing below needed a
code change.

| Settings | Result |
| --- | --- |
| Defaults: `https://localhost` | 13 passed |
| `WEKO_BASE_URL=https://weko3.example.org` + `WEKO_E2E_HOST_IP=127.0.0.1`, no DNS entry and no `/etc/hosts` | 13 passed |
| The same, with `WEKO_TEST_EMAIL` / `WEKO_TEST_PASSWORD` set to a second system administrator account and `WEKO_E2E_LABEL=E2E-user2` | 13 passed |
| `ark` against a server configured with `e2ectl ark-account enable`, login flow rather than API key | 6 passed; minted `ark:/12345/x900002` under the configured NAAN and shoulder |
| `crossref` with `WEKO_E2E_CROSSREF_DEPOSIT=1` against a stand-in for Crossref | 10 passed; the deposit reached `success` |

The second row goes through the host resolver rule in the browser and the
pinned-host adapter in the HTTP client; the third proves the run does not
depend on the account the instance ships with. The temporary account was
removed afterwards, and the database was back at the baseline after each.

## Running it repeatedly

Runs do not collide, because every resource name carries the run id. Two
back to back cycles with `--clean-after --clean-hard` both passed, and both
left the database at the baseline.

```console
$ for i in 1 2; do ../.venv-e2e/bin/python -m pytest --clean-after --clean-hard -q; done
================== 13 passed, 6 warnings in 82.08s (0:01:22) ===================
================== 13 passed, 6 warnings in 82.27s (0:01:22) ===================
```

Suites do not collide with each other either: every resource name carries
the run id *and* the suite, which is why the three above could share one
session.

## Reproducing this report

```bash
cd e2e
../.venv-e2e/bin/python ./e2ectl ark-stub enable # the ark suite needs a server
../.venv-e2e/bin/python ./e2ectl clean --hard   # back to the baseline
WEKO_E2E_ARK_NAAN=99999 \
  ../.venv-e2e/bin/python -m pytest --suite all   # the screenshots are retaken
../.venv-e2e/bin/python ./e2ectl status         # what the ledger holds
../.venv-e2e/bin/python ./e2ectl clean --hard    # clean up
../.venv-e2e/bin/python ./e2ectl ark-stub disable
```

The screenshots are written to `images/` under fixed names, so each run
replaces them. The numbers in this document -- the run id, the item id, the
timings -- change with every run.
