# E2E test run report

日本語版: [`README.ja.md`](README.ja.md)

A record of running the suite against an instance brought up by
`install.sh`. The tests take the screenshots themselves as they go, so
re-running refreshes them in place and this report cannot drift from the
code.

This is the run, the base flow and the cleaning up. Each optional suite has
a report of its own, [listed below](#the-optional-suites), beside the
screenshots it is written from.

## Result

| | |
| --- | --- |
| Run at | 2026-09-30 07:58:08 – 08:04:11 (UTC) |
| Run id | `20260930-075808` |
| Result | **41 passed, 2 skipped** (345.63 s) |
| Against | `https://localhost` (`install.sh` / `docker-compose2.yml`) |
| Suites | base, `ark` (against the stand-in ARK server), `coarnotify`, `crossref` |
| Cleaned up with | `./e2ectl clean --hard`; the database, and the inbox, went back to how `install.sh` left them |

```
============================= test session starts ==============================
platform linux -- Python 3.11.12, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/mhaya/weko-workshop/e2e
configfile: pytest.ini
collected 43 items

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

tests/test_coar_notify.py::test_01_login PASSED
tests/test_coar_notify.py::test_02_the_instance_announces_its_inbox PASSED
tests/test_coar_notify.py::test_03_notifications_are_not_public PASSED
tests/test_coar_notify.py::test_04_the_approver_can_read_their_notifications PASSED
tests/test_coar_notify.py::test_05_set_up PASSED
tests/test_coar_notify.py::test_06_send_the_item_for_approval PASSED
tests/test_coar_notify.py::test_07_the_approver_is_offered_the_item PASSED
tests/test_coar_notify.py::test_08_the_instance_can_send_a_web_push PASSED
tests/test_coar_notify.py::test_09_the_registrant_subscribes_to_web_push PASSED
tests/test_coar_notify.py::test_10_the_approver_approves PASSED
tests/test_coar_notify.py::test_11_the_registrant_is_told_it_was_approved PASSED
tests/test_coar_notify.py::test_12_the_approval_arrives_as_a_web_push PASSED
tests/test_coar_notify.py::test_13_unsubscribing_stops_the_pushes PASSED
tests/test_coar_notify.py::test_14_the_user_can_choose_how_to_be_notified PASSED

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

============ 41 passed, 2 skipped, 22 warnings in 345.63s (0:05:45) ============
```

The two skips are the Crossref deposit: this instance was given no
Crossref account, so WEKO grants the DOI and sends nothing, which is the
documented behaviour. The deposit path is verified separately; see
[`crossref/README.md`](crossref/README.md).

The warnings are all `InsecureRequestWarning` for the self signed
certificate, and say nothing about the behaviour under test.

## The environment

```
suite     : weko-workshop  feature/e2e-tests  61e0174
WEKO      : wekov2  feature/nii_WACREN_crossref_doi  594e070cf
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
four suites can share one session:

| Suite | index | flow / workflow | activity | item |
| --- | --- | --- | --- | --- |
| base | `1790755177600` | `c546c21f…` / `701079a1…` | `A-20260930-00010` | `2000086` |
| `ark` | `1790755110129` | `755de1a1…` / `4b7c3fbc…` | `A-20260930-00009` | `2000085` |
| `coarnotify` | `1790755269712` | `b7a8a433…` / `a027ec8a…` | `A-20260930-00011` | `2000087` |
| `crossref` | `1790755372450` | `7e28cfee…` / `cc822665…` | `A-20260930-00012` | `2000088` |

What the optional suites were after:

| | |
| --- | --- |
| ARK minted | `ark:/99999/fk400002` |
| Crossref DOI granted | `10.5555/0002000088` |
| COAR Notify sent | 5 notifications: one approval request per suite that registered an item, and the approval announcement the `coarnotify` suite asked for |

---

## Before the run

`pytest` looks the instance over before its first test, and stops rather
than spending a run on one that cannot pass. What it found is in
[`doctor.md`](doctor.md) -- written by the run itself, so, like the
screenshots, it cannot drift from what actually happened.

Every check passed here, which is why there is a run to report at all.
The file is rewritten on every run, including the runs that stop: those
are the ones worth having a record of.

---

## The base suite, step by step

### 01. Log in (test_01_login)

As the system administrator `wekosoftware@nii.ac.jp`.

![The front page after logging in](images/01-logged-in.png)

### 02. Create the test index (test_02_create_index)

Create the index and publish it. The admin Index Tree shows
`E2E Index 20260930-075808` next to the shipped `Sample Index`.

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

Tick `E2E Index 20260930-075808` in the index tree; DESIGNATE INDEX shows
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

`/records/2000086` exists and shows the title the run registered.

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

## The optional suites

Each has a report of its own, with the screenshots it is written from
beside it -- the same split the suites have in the code, so a suite can be
read, or added, without the others.

| Suite | Report | Result | What it checks |
| --- | --- | --- | --- |
| `ark` | [`ark/README.md`](ark/README.md) | 6 passed | an ARK is minted for the item and becomes its permalink |
| `coarnotify` | [`coarnotify/README.md`](coarnotify/README.md) | 14 passed | the approval request and the approval are announced over COAR Notify, reach the people they are meant to, and arrive as a web push |
| `crossref` | [`crossref/README.md`](crossref/README.md) | 8 passed, 2 skipped | a Crossref DOI is granted to the item and becomes its permalink |

The two skips are the Crossref deposit, which this instance has no account
for; `crossref/README.md` records the deposit path being verified
separately.

---

## Cleaning up

A run leaves what it created in place by default, so that a failure can be
looked at. The ledger says what is still there.

```console
$ ./e2ectl status          # the run_id on the Settings line is this call's, not the run's
Settings(base_url='https://localhost', run_id='20260930-080500', label='E2E')
ledger: /home/mhaya/weko-workshop/e2e/.e2e-state.json
  run 20260930-075808  started 2026-09-30T07:58:30  20 resource(s)
    index     1790755110129            E2E Index 20260930-075808-ark
    flow      755de1a1-2504-47b4-abe7-7daf57e831ab E2E Flow 20260930-075808-ark
    workflow  4b7c3fbc-9d94-4b33-897d-01041af3871a E2E Workflow 20260930-075808-ark
    activity  A-20260930-00009         E2E Workflow 20260930-075808-ark
    item      2000085                  E2E item 20260930-075808-ark
    index     1790755177600            E2E Index 20260930-075808
    ...                                (the base suite's five)
    index     1790755269712            E2E Index 20260930-075808-coarnotify
    ...                                (the coarnotify suite's five)
    index     1790755372450            E2E Index 20260930-075808-crossref
    ...                                (the crossref suite's five)
```

```console
$ ./e2ectl clean --hard
deleted  item 2000085 E2E item 20260930-075808-ark
deleted  item 2000086 E2E item 20260930-075808
deleted  item 2000087 E2E item 20260930-075808-coarnotify
deleted  item 2000088 E2E item 20260930-075808-crossref
deleted  activity A-20260930-00009 ...
deleted  workflow 4b7c3fbc-9d94-4b33-897d-01041af3871a ...
deleted  flow 755de1a1-2504-47b4-abe7-7daf57e831ab ...
deleted  index 1790755110129 E2E Index 20260930-075808-ark
deleted  index 1790755177600 E2E Index 20260930-075808
deleted  index 1790755269712 E2E Index 20260930-075808-coarnotify
deleted  index 1790755372450 E2E Index 20260930-075808-crossref
hard purge: docker compose -f docker-compose2.yml exec -T web invenio shell /tmp/weko-e2e-purge.py /tmp/weko-e2e-purge.json
purged items: 2000085, 2000086, 2000087, 2000088
purged activities: A-20260930-00009, A-20260930-00010, A-20260930-00011, A-20260930-00012
purged workflows: 4b7c3fbc-..., 701079a1-..., a027ec8a-..., cc822665-...
purged flows: 755de1a1-..., c546c21f-..., b7a8a433-..., 7e28cfee-...
purged indexes: 1790755110129, 1790755177600, 1790755269712, 1790755372450
purged notifications: 6
```

The last line is the inbox: it is a service of its own with a database of
its own, so it does not come back to its baseline when WEKO's database
does. `--hard` copies `weko_e2e/inboxpurge.py` into the `inbox` container
and removes the notifications whose `context` names one of the run's
activities -- the four approval requests, the announcement, and the copy
the `coarnotify` suite offered the inbox to test unsubscribing -- and
nothing else.

### What the database gained, and gave back

Measured against how `install.sh` leaves it -- one sample index, one
default flow, two default workflows -- everything the run added is gone
after `--hard`, and nothing else with it.

| | index | flow | workflow | activity | records | bucket | pid | inbox |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Before the run | 1 | 1 | 2 | 0 | 0 | 0 | 0 | 36 |
| After the run | 5 | 5 | 6 | 4 | 8 | 8 | 37 | 42 |
| After `clean --hard` | **1** | **1** | **2** | **0** | **0** | **0** | **0** | **36** |

Four of each, one per suite. Two records and two buckets per item,
because WEKO keeps an item as a version-less record and a Ver.1 record.
The pid store came back to 0 rows as well, granted DOI and minted ARK
included, and the inbox to the 36 notifications it held before the run.

The item's page is gone too.

```console
$ curl -s -o /dev/null -w '%{http_code}\n' --insecure https://localhost/records/2000086
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
| `coarnotify` on its own, with the web push stand-in | 14 passed; the push arrived and decrypted to what `push.json` says |
| `coarnotify` with no web push stand-in running | 10 passed, 4 skipped; the four web push steps said how to ask for them |

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
the run id *and* the suite, which is why the four above could share one
session.

## Reproducing this report

```bash
cd e2e
../.venv-e2e/bin/python ./e2ectl ark-stub enable     # the ark suite needs a server
../.venv-e2e/bin/python ./e2ectl webpush-stub enable # and the push steps a browser
../.venv-e2e/bin/python ./e2ectl clean --hard        # back to the baseline
WEKO_E2E_ARK_NAAN=99999 \
  ../.venv-e2e/bin/python -m pytest --suite all      # the screenshots are retaken
../.venv-e2e/bin/python ./e2ectl status              # what the ledger holds
../.venv-e2e/bin/python ./e2ectl clean --hard        # clean up
../.venv-e2e/bin/python ./e2ectl webpush-stub disable
../.venv-e2e/bin/python ./e2ectl ark-stub disable
```

The rest of the `coarnotify` suite needs nothing turned on: the `inbox`
service and `repoadmin@example.org` are both part of what `install.sh`
brings up. Only the four web push steps want the stand-in, and they skip
without it.

The screenshots are written to `images/` under fixed names, so each run
replaces them. The numbers in this document -- the run id, the item id, the
timings -- change with every run.
