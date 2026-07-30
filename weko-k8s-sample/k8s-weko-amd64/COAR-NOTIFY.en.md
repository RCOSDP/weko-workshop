# Running COAR Notify (amd64 / k8s-weko-amd64)

How to exercise WEKO3's COAR Notify integration (`weko-notifications`) entirely inside the kind
cluster, with no external dependency.

```bash
WEKO_COAR_NOTIFY=yes bash deploy-amd64.sh
```

Received notifications are visible in a browser at `https://<tenant>.localhost/inbox`.
To watch them go by in the log:

```bash
kubectl -n weko3 logs -f deploy/coar-notify-inbox
```

Japanese version: [COAR-NOTIFY.md](COAR-NOTIFY.md)

---

## Why the inbox has to be provided

**WEKO3 only implements the sending and reading sides of COAR Notify.** The inbox itself is an
external service.

The defaults in `weko-notifications/config.py` say as much:

```python
WEKO_NOTIFICATIONS_INBOX_ADDRESS = "http://inbox:8080"
WEKO_NOTIFICATIONS_INBOX_ENDPOINT = "/inbox"
```

So WEKO POSTs notifications to `http://inbox:8080/inbox` and GETs the same URL to list them.
**Placing a Service named `inbox` in the `weko3` namespace is enough for it to work with no
WEKO-side configuration at all.**

That is all `72-coar-notify-inbox.yaml` does. The implementation is `coar-notify-inbox/inbox.py`
(Python standard library only, about 190 lines) and it keeps notifications in memory, so a Pod
restart loses them. A production inbox is a different implementation with persistence,
authentication and signature verification.

---

## The overall flow

```
   workflow action              WEKO3 (uwsgi)              inbox                 browser
        |                            |                       |                      |
        |  approve                   |                       |                      |
        |--------------------------->|                       |                      |
        |                            |  POST /inbox          |                      |
        |                            |  (application/ld+json)|                      |
        |                            |---------------------->|                      |
        |                            |                 201 Created                  |
        |                            |                       |                      |
        |                            |  GET /api/notifications (the reading side)   |
        |                            |  -> GET /inbox?target=<user uri>             |
        |                            |---------------------->|                      |
        |                            |   the IRIs in ldp:contains                    |
        |                            |                       |                      |
        |                            |    GET https://<tenant>/inbox/<id>            |
        |                            |    (relayed by nginx)                         |
        |                            |<--------------------------------------------->|
```

---

## The pieces

| File | Role |
|---|---|
| `72-coar-notify-inbox.yaml` | The inbox Deployment and Service (**the Service must be named `inbox`**) |
| `coar-notify-inbox/inbox.py` | The inbox itself, handed over as the ConfigMap `coar-notify-inbox-src` |
| `21-nginx-config.yaml` | The `location` relaying the tenant's `/inbox` to the inbox Service |
| `gen-tenant.sh` | Writes the target into invenio.cfg when `WEKO_COAR_NOTIFY=yes` |

`inbox.py` lives in a ConfigMap rather than inline in the manifest so the same code is not kept in
two places; the deploy script builds it with `kubectl create configmap --from-file`.

### What the inbox implements

Only what `py-ldnlib 0.1.3` (`ldnlib/sender.py`, `consumer.py`) actually uses.

| Request | Requirement |
|---|---|
| `POST <inbox>` | `Content-Type: application/ld+json`; **must answer 2xx** (`Sender` calls `raise_for_status()`) |
| `GET <inbox>` | JSON-LD that rdflib can parse; the objects of `ldp:contains` become the notification IRIs |
| `GET <inbox>/<id>` | The notification itself |
| `OPTIONS <inbox>` | The `Accept-Post` header (only consulted when the `Sender` posts a Graph) |
| `HEAD /` | The `ldp#inbox` Link header (for `BaseLDN.discover`) |

The `GET <inbox>?target=<uri>` filter matches against each notification's `target.id`. On the WEKO
side (`weko_notifications/views.py`) the GET carries `?target=<THEME_SITEURL>/users/<id>`.

---

## The notification types

`weko-workflow` emits eight of them (`notify_about_activity` in `weko_workflow/api.py`).

| Case | COAR Notify type | Recipient |
|---|---|---|
| `registered` | `Announce` + `coar-notify:IngestAction` | the registrant |
| `request_approval` | `Offer` + `coar-notify:EndorsementAction` | the approvers |
| `approved` | `Announce` + `coar-notify:EndorsementAction` | the registrant |
| `rejected` | `Reject` | the registrant |
| `deleted` | `Announce` + `coar-notify:IngestAction` + `Delete` | the registrant |
| `deletion_request` | `Offer` + `coar-notify:EndorsementAction` + `Delete` | the approvers |
| `deletion_approved` | `Announce` + `coar-notify:EndorsementAction` + `Delete` | the registrant |
| `deletion_rejected` | `Reject` + `Delete` | the registrant |

SWORD deposits and deletions have their own `notify_item_imported` / `notify_item_deleted`
(`weko-swordserver/utils.py`).

### How the recipients are decided

- **To the registrant** (`_get_params_for_registrant`):
  `activity_login_user` plus the shared users — but **whoever performed the action
  (`activity_update_user`) is removed**. Registering and publishing something yourself therefore
  produces zero notifications. That is the implementation, not a bug.
- **To the approvers** (`_get_params_for_approver`):
  resolved from the database as the users holding the `WEKO_ADMIN_PERMISSION_ROLE_REPO`
  (Repository Administrator) role, refined by the approval action's `action_role` if one is set.

---

## Which action actually fires one

**Not every workflow button sends a notification.** Only a couple of transitions in
`weko_workflow/views.py` do.

```python
if next_action_endpoint == "approval":
    work_activity.notify_about_activity(activity_id, "request_approval")   # when approval is next
...
if next_action_endpoint == "end_action":
    if action_endpoint == "approval":
        work_activity.notify_about_activity(activity_id, "approved")       # when approval just finished
    else:
        work_activity.notify_about_activity(activity_id, "registered")
```

With the default flow (Start → Item Registration → Item Link → Identifier Grant → Approval → End):

| Transition | Notification |
|---|---|
| Item Registration → Item Link | **none** |
| Item Link → Identifier Grant | **none** |
| Identifier Grant → Approval | `request_approval` (approval is next) |
| Approval → End | `approved` (approval just finished) |

If a registration seems to produce no notification, check whether the activity has actually reached
the step before Approval.

---

## Checking it works

```bash
# 1) is the inbox receiving? (each notification is dumped as-is)
kubectl -n weko3 logs -f deploy/coar-notify-inbox

# 2) is the inbox reachable through the tenant? (the notification IRIs are these URLs)
curl -k -H 'accept: application/ld+json' https://tenant1.localhost/inbox

# 3) just one user's
curl -k -H 'accept: application/ld+json' \
  'https://tenant1.localhost/inbox?target=http://tenant1.localhost/users/2'
```

Opening `https://tenant1.localhost/inbox` in a browser shows the received list as HTML.

WEKO's own reading API is `GET /api/notifications` (login required; returns only the logged-in
user's notifications).

---

## Configuration

With `WEKO_COAR_NOTIFY=yes`, `gen-tenant.sh` appends this to invenio.cfg:

```python
WEKO_NOTIFICATIONS = True
WEKO_NOTIFICATIONS_INBOX_ADDRESS = "http://inbox:8080"
WEKO_NOTIFICATIONS_INBOX_ENDPOINT = "/inbox"
```

Those are already `weko-notifications`' defaults, so **it works without them**. They are written out
anyway so that invenio.cfg alone shows where notifications go, and so the target can be swapped for
an external inbox:

```bash
WEKO_COAR_NOTIFY=yes WEKO_INBOX_ADDRESS=https://inbox.example.org bash deploy-amd64.sh
```

| Variable | Default | Meaning |
|---|---|---|
| `WEKO_COAR_NOTIFY` | `no` | `yes` deploys the inbox |
| `WEKO_INBOX_IMAGE` | `python:3.12-alpine` | The inbox base image |
| `WEKO_INBOX_ADDRESS` | `http://inbox:8080` | The target (read by `gen-tenant.sh`) |

---

## What the default (`WEKO_COAR_NOTIFY=no`) does

- No inbox is deployed, and `gen-tenant.sh` appends **nothing** to invenio.cfg.
- `WEKO_NOTIFICATIONS` stays at the module default of `True`, so **sending is still attempted**.
  With no inbox the connection fails, but `_notify_about_activity_wiht_case` swallows it with
  `except Exception` and logs it, so **the workflow still completes as before**.
- The `/inbox` block in `21-nginx-config.yaml` is present in every configuration, but as described
  below it does not affect nginx startup — a request simply gets a 502.

To stop the attempt altogether, add `WEKO_NOTIFICATIONS = False` to invenio.cfg.

---

## Things that actually bit

### 1. A Service named `inbox` injects environment variables

Kubernetes injects Docker-link style variables derived from Service names into **every Pod** in the
namespace. Naming the Service `inbox` produces `INBOX_PORT=tcp://10.96.x.x:8080`, so using
`INBOX_PORT` inside `inbox.py` makes `int()` fail. Use a non-colliding name such as `LISTEN_PORT`.

```
ValueError: invalid literal for int() with base 10: 'tcp://10.96.225.2:8080'
```

### 2. nginx's resolver ignores the search list in `/etc/resolv.conf`

`http://inbox:8080` resolves fine on the WEKO side, but nginx's `resolver` does not append search
suffixes, so the short name fails. **The FQDN is required.**

```
[error] inbox could not be resolved (2: Server failure)
```

`21-nginx-config.yaml` uses `inbox.weko3.svc.cluster.local`.

### 3. A literal host name in `proxy_pass` stops nginx from starting

nginx resolves upstream names at startup, so **nginx itself fails to start** when the inbox Service
is absent. Going through a variable defers resolution to request time, so the default (no inbox)
setup starts exactly as before.

```nginx
location /inbox {
    resolver 10.96.0.10 valid=30s ipv6=off;
    set $coar_inbox http://inbox.weko3.svc.cluster.local:8080;
    proxy_pass $coar_inbox$request_uri;
}
```

### 4. There are two different inbox URLs

`inbox_url()` and `inbox_url(_external=True)` are not the same thing.

| Call | Value | Used for |
|---|---|---|
| `inbox_url()` | `WEKO_NOTIFICATIONS_INBOX_ADDRESS` + `/inbox` | Where WEKO connects, server-side |
| `inbox_url(_external=True)` | `THEME_SITEURL` + `/inbox` | The URL that appears inside notifications and API responses |

`views.py` **string-replaces** the former with the latter on the IRIs it returns. So the base the
inbox builds its IRIs from (`INBOX_BASE_URL`) must match WEKO's configured value **exactly**, and
the nginx relay is what makes the latter (`https://<tenant>/inbox`) actually serve something.

---

## How this differs from production

| Aspect | This setup | Production equivalent |
|---|---|---|
| Persistence | **none** (in memory; lost on Pod restart) | database / files |
| Authentication | **none** (anyone can POST) | tokens or similar |
| Signature verification | **none** | as required |
| Exposure | in-cluster plus the tenant's `/inbox` | a public endpoint |
| Peer | itself (WEKO → its own inbox) | external services (review, recommendation, overlay journals) |

COAR Notify is meant to run **between a repository and external services**, so this setup exists to
confirm that WEKO emits notifications that conform to the specification.

---

## Removing it

```bash
kubectl -n weko3 delete -f 72-coar-notify-inbox.yaml
kubectl -n weko3 delete configmap coar-notify-inbox-src
```

The nginx `/inbox` block can stay (it just answers 502).

---

## Related documents

| Document | Contents |
|---|---|
| [README-amd64.en.md](README-amd64.en.md) | The whole build procedure |
| [SHIBBOLETH-IDP.en.md](SHIBBOLETH-IDP.en.md) | The Shibboleth login (another env-var-gated feature) |
| [ACCESS-kubectl.en.md](ACCESS-kubectl.en.md) | kubectl access to each component |
