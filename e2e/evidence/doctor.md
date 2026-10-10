# What the instance looked like before the run

Written by the run itself, before its first test: every `pytest`
looks the instance over and stops rather than spending a run on
one that cannot pass.  Re-running rewrites this file, so it
cannot drift from what was actually found.

| | |
| --- | --- |
| Looked at | 2026-10-10T09:20:34 |
| Instance | https://localhost |
| Run id | `20261010-092015` |
| Suites | base |
| Result | 15 of 15 checks passed |

| | Check | What was found |
| --- | --- | --- |
| ok | the instance answers | https://localhost |
| ok | a way into the containers | /home/mhaya/wekov2 |
| ok | the account logs in | wekosoftware@nii.ac.jp |
| ok | the account administers | the admin screens answer |
| ok | the item type under test | デフォルトアイテムタイプ（フル） |
| ok | the workflow actions | 7 of them, the six the suite uses included |
| ok | a flow to copy from | 1 flow(s), starting with 'Registration Flow' |
| ok | the index tree | 1 index(es) |
| ok | somewhere to put files | /var/tmp (left as it is) |
| ok | this month's log partition | user_activity_logs_202610 |
| ok | a registered language | en, fil, fr, hi, id, ja, ms, th, vi, zh_Hans, zh_Hant |
| ok | search answers | Elasticsearch is reachable |
| ok | the worker is running | up |
| ok | nothing left from an earlier run | nothing is named E2E* |
| ok | the instance is at its baseline | exactly what install.sh leaves |

Everything the suites depend on was there, so the run went ahead.
