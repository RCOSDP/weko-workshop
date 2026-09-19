# E2E test run report: the `coarnotify` suite

日本語版: [`README.ja.md`](README.ja.md) ·
the run this belongs to: [`../README.md`](../README.md)

The approval request and the approval are announced over COAR Notify, and
reach the people they are meant to -- which takes two accounts, because WEKO
leaves the person who acted out of the notification about their own action.

The suite is
[`../../tests/test_coar_notify.py`](../../tests/test_coar_notify.py); the
screenshots below are in [`images/`](images), taken by the steps themselves
as they went.

| | |
| --- | --- |
| Run id | `20260919-043749` |
| Result | **10 passed** |
| Asked for with | `--suite coarnotify` |

---

WEKO turns workflow events into COAR Notify messages and POSTs them to the
LDN inbox -- the `inbox` container of this stack -- and reads them back
for the person they were addressed to at `GET /api/notifications`.

**Who receives what is the point.** WEKO leaves the person who acted out
of the notification about their own action, so this suite uses two
accounts: `wekosoftware@nii.ac.jp` registers, and
`repoadmin@example.org` -- the repository administrator approval
requests go to -- approves.

### The site announces its inbox (test_02)

```console
$ curl -sI --insecure https://localhost/ | grep -i '^link:'
Link: <https://weko3.example.org/inbox>; rel="http://www.w3.org/ns/ldp#inbox"
```

The URL is built from `THEME_SITEURL`, which is what the instance calls
itself and need not be the address the run is testing -- so the suite
fetches a notification by its *path* from the instance under test. WEKO
adds the header to a HEAD of the top page and not to a GET, which is what
the step asks for accordingly.

A visitor who has not logged in gets a 401 from `/api/notifications`
rather than somebody else's notifications (test_03).

### The item goes to the approver (test_06, test_07)

Moving on from the identifier grant puts the activity on the Approval
action, which is where WEKO offers it to the approvers.

![The activity waiting for approval](images/01-awaiting-approval.png)

Read back as `repoadmin@example.org`, and then fetched from the inbox:

```json
{
  "id": "urn:uuid:d98ca136-e8dd-42ca-ad2b-2d76b3f2efe0",
  "@context": ["https://www.w3.org/ns/activitystreams", "https://coar-notify.net"],
  "type": ["Offer", "coar-notify:EndorsementAction"],
  "origin": {"id": "https://localhost/", "inbox": "…/inbox", "type": "Service"},
  "target": {"id": "https://weko3.example.org/users/2", "inbox": "…/inbox", "type": "Person"},
  "object": {"id": "https://localhost/records/2000054",
             "type": ["Page", "sorg:WebPage"],
             "name": "E2E item 20260919-043749-coarnotify"},
  "actor":  {"id": "https://weko3.example.org/users/1", "type": "Person"},
  "context": {"id": "https://localhost/workflow/activity/detail/A-20260919-00015",
              "type": ["Page", "sorg:WebPage"]}
}
```

`context` is what ties a notification to one activity, and so the only
thing in the payload that names *this* run's; the suite finds its own by
it rather than by taking whatever arrived last.

### The approver approves (test_08)

The approver opens the activity in a browsing context of their own. WEKO
holds an activity for the window that has it open, so the registrant
moves off the screen first -- as a person handing work over would -- and
the approver lets go of anything an earlier run left them holding.

![The approval screen, as the approver](images/02-approver-screen.png)

![After approval](images/03-approved.png)

### The approval goes back to the registrant (test_09)

```
urn:uuid:7f989264-5966-4cc0-847f-6aefb97887d2
  Announce+coar-notify:EndorsementAction
  -> https://weko3.example.org/users/1
  about 'E2E item 20260919-043749-coarnotify' (https://localhost/records/2000054)
```

`users/1` is the registrant, and the `actor` is `users/2` -- the account
the offer was addressed to. The step checks exactly that: the person the
item was offered to is the person the announcement names as having
endorsed it, and the announcement did not go back to the person who made
it.

`./e2ectl inbox --run <run id>` shows both ends of the loop:

```console
$ ./e2ectl inbox --run 20260919-043749
registrant: wekosoftware@nii.ac.jp
  announced inbox: https://weko3.example.org/inbox
  2026-09-19 04:41:45  … Announce+…EndorsementAction -> …/users/1 about 'E2E item 20260919-043749-coarnotify'
  1 of 1 notification(s) shown
approver: repoadmin@example.org
  2026-09-19 04:41:28  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-043749-coarnotify'
  2026-09-19 04:42:54  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-043749-crossref'
  2026-09-19 04:38:52  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-043749-ark'
  2026-09-19 04:40:15  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-043749'
  4 of 40 notification(s) shown
```

Four offers, because **every** suite that registers an item sends one --
the base suite and the two identifier suites included. The announcement
is the `coarnotify` suite's own, and the only one in this run, because it
is the only suite that has somebody other than the registrant approve.

### How the user asks to be told (test_10)

![The notification settings screen](images/04-settings.png)

Web push and Email, per user. The suite checks the screen offers both;
turning web push on needs a browser notification permission and VAPID
keys on the inbox container, which this stack does not have set.
