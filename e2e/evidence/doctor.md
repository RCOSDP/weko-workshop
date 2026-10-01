# What the instance looked like before the run

Written by the run itself, before its first test: every `pytest`
looks the instance over and stops rather than spending a run on
one that cannot pass.  Re-running rewrites this file, so it
cannot drift from what was actually found.

| | |
| --- | --- |
| Looked at | 2026-10-01T07:21:27 |
| Instance | https://localhost |
| Run id | `20261001-072108` |
| Suites | base, shibboleth |
| Result | 13 of 15 checks passed |

| | Check | What was found |
| --- | --- | --- |
| ok | the instance answers | https://localhost |
| ok | the WEKO checkout | /home/mhaya/wekov2 |
| ok | the account logs in | wekosoftware@nii.ac.jp |
| ok | the account administers | the admin screens answer |
| ok | the item type under test | デフォルトアイテムタイプ（フル） |
| ok | the workflow actions | 7 of them, the six the suite uses included |
| ok | a flow to copy from | 3 flow(s), starting with 'E2E Flow 20260930-230611' |
| ok | the index tree | 3 index(es) |
| ok | somewhere to put files | /var/tmp (left as it is) |
| ok | this month's log partition | user_activity_logs_202610 |
| ok | a registered language | en, fil, fr, hi, id, ja, ms, th, vi, zh_Hans, zh_Hant |
| ok | search answers | Elasticsearch is reachable |
| ok | the worker is running | up |
| warn | nothing left from an earlier run | 2 flow, 2 index, 2 item, 2 workflow named E2E* (https://localhost). A run does not collide with them -- every name carries its own run id -- so this is a note, not a fault. Whether they are an earlier run's or somebody's work is not something to guess at, so nothing here removes them: "./e2ectl clean --discover --hard" does, when you mean it. |
| warn | the instance is at its baseline | above it by 2 activities, 4 buckets, 2 flows, 2 indexes, 16 pids, 4 records, 2 workflows. That is normal for a repository in use, and for a run that was cleaned with "clean" rather than "clean --hard". |

Nothing the run itself depends on was missing, so it went ahead; the warnings are what the other suites want, or what an earlier run left behind.
