# E2E test run report: the `coarnotify` suite

日本語版: [`README.ja.md`](README.ja.md) ·
the run this belongs to: [`../README.md`](../README.md)

The approval request and the approval are announced over COAR Notify, reach
the people they are meant to -- which takes two accounts, because WEKO leaves
the person who acted out of the notification about their own action -- and
arrive at the browser as a Web Push.

The suite is
[`../../tests/test_coar_notify.py`](../../tests/test_coar_notify.py); the
screenshots below are in [`images/`](images), taken by the steps themselves
as they went.

| | |
| --- | --- |
| Run id | `20260930-075808` |
| Result | **14 passed** |
| Asked for with | `--suite coarnotify`, with `e2ectl webpush-stub enable` for the four web push steps |

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
  "id": "urn:uuid:6317322d-7750-468e-94f9-d64e2c690b6f",
  "@context": ["https://www.w3.org/ns/activitystreams", "https://coar-notify.net"],
  "type": ["Offer", "coar-notify:EndorsementAction"],
  "origin": {"id": "https://localhost/", "inbox": "…/inbox", "type": "Service"},
  "target": {"id": "https://weko3.example.org/users/2", "inbox": "…/inbox", "type": "Person"},
  "object": {"id": "https://localhost/records/2000087",
             "type": ["Page", "sorg:WebPage"],
             "name": "E2E item 20260930-075808-coarnotify"},
  "actor":  {"id": "https://weko3.example.org/users/1", "type": "Person"},
  "context": {"id": "https://localhost/workflow/activity/detail/A-20260930-00011",
              "type": ["Page", "sorg:WebPage"]}
}
```

`context` is what ties a notification to one activity, and so the only
thing in the payload that names *this* run's; the suite finds its own by
it rather than by taking whatever arrived last.

### The approver approves (test_10)

The approver opens the activity in a browsing context of their own. WEKO
holds an activity for the window that has it open, so the registrant
moves off the screen first -- as a person handing work over would -- and
the approver lets go of anything an earlier run left them holding.

![The approval screen, as the approver](images/02-approver-screen.png)

![After approval](images/03-approved.png)

### The approval goes back to the registrant (test_11)

```
urn:uuid:c7d8c0ac-0d2d-41a5-ac0f-f010873ab4f2
  Announce+coar-notify:EndorsementAction
  -> https://weko3.example.org/users/1
  about 'E2E item 20260930-075808-coarnotify' (https://localhost/records/2000087)
```

`users/1` is the registrant, and the `actor` is `users/2` -- the account
the offer was addressed to. The step checks exactly that: the person the
item was offered to is the person the announcement names as having
endorsed it, and the announcement did not go back to the person who made
it.

`./e2ectl inbox --run <run id>` shows both ends of the loop:

```console
$ ./e2ectl inbox --run 20260930-075808
registrant: wekosoftware@nii.ac.jp
  announced inbox: https://weko3.example.org/inbox
  2026-09-30 08:02:13  … Announce+…EndorsementAction -> …/users/1 about 'E2E item 20260930-075808-coarnotify'
  2026-09-30 08:02:13  … Announce+…EndorsementAction -> …/users/1 about 'E2E item 20260930-075808-coarnotify'
  2 of 2 notification(s) shown
approver: repoadmin@example.org
  2026-09-30 08:01:54  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260930-075808-coarnotify'
  2026-09-30 08:00:40  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260930-075808'
  2026-09-30 07:59:15  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260930-075808-ark'
  2026-09-30 08:03:40  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260930-075808-crossref'
  4 of 40 notification(s) shown
```

Four offers, because **every** suite that registers an item sends one --
the base suite and the two identifier suites included. The announcement
is the `coarnotify` suite's own, because it is the only suite that has
somebody other than the registrant approve. The registrant's second one
is the copy step 13 offers the inbox to prove that an unsubscribed
browser is sent nothing.

---

## Web push

A notification can also reach the user as a Web Push. WEKO's part is
registering the subscription, the user's profile and the message
templates with the inbox; the inbox is what encrypts a notification for
a subscription and delivers it.

Two things stand in the way of testing that for real, and
`e2ectl webpush-stub enable` deals with both: a real subscription comes
from the browser's own push service, which a local stack cannot reach,
and the shipped compose file leaves the inbox's VAPID keys empty, so it
would sign nothing anyway.

### The instance can sign a push, and something is listening (test_08)

```console
$ curl -sk https://localhost/inbox/subscription/vapid-public-key
BC2j8jsLBLFkhXLT...

$ ./e2ectl webpush-stub status
settings in docker-compose2.yml: present
stand-in in the container: subscribed as http://127.0.0.1:8901/push
pushes received so far: 0
```

The stand-in is `weko_e2e/pushstub.py`, run on the loopback interface of
the `inbox` container, which is where the inbox sends from. It holds
subscription keys of its own, so nothing has to be reachable over the
network and no push service anywhere is involved.

### The registrant subscribes (test_09)

The stand-in registers its subscription and a user profile for
`https://weko3.example.org/users/1`, which is what the notification
settings screen posts when a real browser subscribes. The profile is not
optional: it is what the inbox picks the language of the message by.

### The approval arrives as a web push (test_12)

The payload is encrypted for the subscription's own keys, so what the
stand-in decrypts is what the browser would have shown:

```json
{
  "title": "Your item is now approved",
  "options": {
    "body": "\"E2E item 20260930-075808-coarnotify\" has been approved by Unknown.",
    "tag": "urn:uuid:c7d8c0ac-0d2d-41a5-ac0f-f010873ab4f2",
    "icon": "/static/images/weko-logo-256.png",
    "badge": "/static/images/weko-logo-256.png",
    "requireInteraction": false,
    "data": {"url": "https://localhost/workflow/activity/detail/A-20260930-00011"}
  }
}
```

The step does not carry that text: it reads `push.json` out of the WEKO
checkout, renders it the way the inbox does, and compares. So the words
are the instance's own, and a template that changed without the text
being registered again would show up here.

`tag` is the notification the push is about, which is how the run finds
its own; `data.url` is the activity, which is where clicking the push
would take the user.

**"approved by Unknown"** is WEKO's own doing, not a fault in the run:
the approver has no user profile row, and `actor_name or "Unknown"` is
what `Notification.set_all` falls back to. The notification says the
same, and the step compares the push with the notification, so it
matches.

### Unsubscribing stops the pushes (test_13)

The run has only one approval to give, so the second notification is
offered to the inbox the way any sender offers one -- a POST to
`/inbox` -- and it is the same notification but for its id. Nothing was
pushed for it, which is the only thing that had changed.

### How the user asks to be told (test_14)

![The notification settings screen](images/04-settings.png)

Web push and Email, per user, and the service worker behind the Web push
switch (`/static/gen/sw.js`) is served. Turning the switch on for real
also needs the browser's notification permission and a push service,
which is what the stand-in above is there instead of.
