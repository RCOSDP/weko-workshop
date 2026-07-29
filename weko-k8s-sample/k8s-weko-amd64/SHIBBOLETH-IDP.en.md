# Running a Shibboleth IdP and logging in to WEKO3 with it (amd64 / k8s-weko-amd64)

How to stand up a **real Shibboleth Identity Provider (IdP 5.2.3)** inside the kind cluster and exercise
the WEKO3 Shibboleth login (the GakuNin-equivalent path) with no external dependencies.

```bash
WEKO_SHIB=yes bash deploy-amd64.sh
# verify (walks the whole flow the way a browser would)
python3 check-shib-login.py
```

The entry point for the login is `https://<tenant>.localhost/weko/shib/sp/login`.
To make `/login` itself go to the IdP, use `WEKO_SHIB_LOGIN_ONLY=yes` (see below; the default is `no`).

| demo user | password | wekoSocietyAffiliation | WEKO role |
|---|---|---|---|
| `admin` | `admin123` | 管理者 | System Administrator |
| `libadmin` | `libadmin123` | 図書館員 | Repository Administrator |
| `teacher` | `teacher123` | 教員 | Contributor |

The e-mail address is `<login id>@example.org` (the IdP's `idp.scope`). The administrator in
`tenants.txt` is `admin@example.org`, so logging in as `admin` links straight to the default tenant
administrator.

---

## Why build the image here

The prebuilt Shibboleth IdP images on Docker Hub (`unicon/shibboleth-idp`, `i2incommon/shib-idp`,
`tier/shib-idp`) do exist for amd64, but all of them are unmaintained and none covers IdP 5. They also
have no arm64 build, which would make this set diverge from the arm64 one (`../k8s-weko`). The IdP
itself ships as a pure-Java tarball and is architecture independent, so `shib-idp-build/Dockerfile`
assembles it from the **official tarball + Tomcat 10.1 (multi-arch)**. It is byte-for-byte the same
setup as the arm64 variant and builds natively on both.

> IdP 5 uses `jakarta.servlet`, so it needs **Tomcat 10.1 or newer** (Tomcat 9 is `javax`-based and will
> not work). Also, `/idp/status` alone renders through a JSP rather than Velocity, so on Tomcat - which,
> unlike Jetty, does not bundle JSTL - it returns 500 until two JSTL jars are added (the Dockerfile
> pulls them from Maven Central). The login screen itself is Velocity, so those jars matter only for
> `/idp/status`.

Authentication does not involve a directory server: the stock IdP 5 `shibboleth.HTPasswdValidator` reads
an htpasswd file (`shib-idp-build/idp-conf/credentials/demo.htpasswd`).
`HTPasswdCredentialValidator` only understands `$apr1$` / `{SHA}` / `crypt(3)` and **does not support
bcrypt**, so generate additional users with `htpasswd -nbm`.

---

## The overall flow

```
browser                 nginx + shibd (SP)              WEKO3 (uwsgi)            IdP
   |                          |                             |                    |
   |  /weko/shib/sp/login     |                             |                    |
   |------------------------->|---------------------------->|                    |
   |            302 /secure/login.py?next=/                  |                    |
   |<--------------------------------------------------------|                   |
   |  /secure/login.py        |                             |                    |
   |------------------------->| shib_request /shibauthorizer|                    |
   |            302 /idp/profile/SAML2/Redirect/SSO?SAMLRequest=...               |
   |<-------------------------|                             |                    |
   |  login form                                                                  |
   |----------------------------------------------------------------------------->|
   |  auto-submitting form carrying the SAMLResponse                               |
   |<-----------------------------------------------------------------------------|
   |  POST /Shibboleth.sso/SAML2/POST                                             |
   |------------------------->| shibd validates the assertion, creates a session   |
   |            302 /secure/login.py?next=/                  |                    |
   |<-------------------------|                             |                    |
   |  /secure/login.py (now with attributes)                |                    |
   |------------------------->| login.py collects them and   |                    |
   |                          | POSTs /weko/shib/login ----->|                    |
   |            302 /weko/shib/login?Shib-Session-ID=...     |                    |
   |<-------------------------|                             |                    |
   |  WEKO account-linking screen -> logged in               |                    |
```

The first login shows the **WEKO account-linking screen**:
- link to an existing WEKO account → enter its e-mail address and password
- create a new WEKO user → "Login (New WEKO users)"

Subsequent logins skip that screen.

---

## The pieces

| file | role |
|---|---|
| `shib-idp-build/Dockerfile` | the IdP image (unattended install of the official tarball → deployed onto Tomcat 10.1) |
| `shib-idp-build/idp-conf/` | the IdP config overlay (authentication, attribute definitions, release policy, metadata) |
| `70-shibboleth-idp.yaml` | the institutional IdP's Deployment / Service / Ingress (`idp.localhost`) |
| `71-shibboleth-map.yaml` | the mAP-equivalent attribute authority (`map.localhost`); used only with `WEKO_SHIB_MAP=aggregation` |
| `provision-shib.sh` | generates the SP key, extracts the IdP and attribute authority metadata, registers the SP metadata, places it all on NFS |
| `shib-sp-template/shibboleth2.xml` | the SP (shibd) configuration template; the FQDN is substituted per tenant |
| `shib-sp-template/attribute-map-weko.xml` | SP-side mapping for the WEKO-specific attributes (`wekoId` / `wekoSocietyAffiliation`) |
| `shib-sp-template/simple-aggregation.xml` | the SimpleAggregation block (inserted only with `aggregation`) |
| `shib-sp-template/map-metadata-provider.xml` | the `<MetadataProvider>` reading the attribute authority's metadata (same) |
| `default-shib.conf` in `21-nginx-config.yaml` | the nginx configuration carrying `shibauthorizer` / `/secure/login.py` / `/weko/shib` |

### How the trust is established

No federation metadata feed is involved; **everything is local files**.

- **SP → IdP**: `provision-shib.sh` extracts `idp-metadata.xml` from the IdP image and places it in each
  tenant's `/fs-shibboleth/<tenant>/`. Taking it from the image guarantees it matches the IdP's signing key.
- **IdP → SP**: the SP metadata for every tenant in `tenants.txt` is combined into a single
  `EntitiesDescriptor` and mounted into the IdP as the ConfigMap `weko-idp-sp-metadata`.
- **The SP key**: `provision-shib.sh` creates exactly one pair under `.shib-sp/` and reuses it
  afterwards (it is `.gitignore`d; deleting it re-establishes the trust).

Rebuilding the IdP image changes its signing key, so **always re-run `provision-shib.sh`** afterwards.

### Attribute plumbing

| IdP attribute | SAML name | SP id | use in WEKO |
|---|---|---|---|
| `eduPersonPrincipalName` | `urn:oid:1.3.6.1.4.1.5923.1.1.1.6` | `eppn` | `shib_eppn` (the key identifying the person) |
| `mail` | `urn:oid:0.9.2342.19200300.100.1.3` | `mail` | `shib_mail` (matched against WEKO accounts) |
| `displayName` | `urn:oid:2.16.840.1.113730.3.1.241` | `displayName` | `shib_user_name` |
| `wekoSocietyAffiliation` | `urn:oid:1.3.6.1.4.1.32264.2.1.6` | `wekoSocietyAffiliation` | role assignment (`WEKO_ACCOUNTS_SHIB_ROLE_RELATION`) |
| `wekoId` | `urn:oid:1.3.6.1.4.1.32264.2.1.1` | `wekoId` | `SHIB_ATTR_USER_NAME` |

Per-user values come from the login id rather than from LDAP
(`shib-idp-build/idp-conf/conf/attribute-resolver.xml`). The role comes from a `Mapped` attribute
definition: `admin` → 管理者, `libadmin` → 図書館員, everyone else → 教員 (the default value).
To add users or roles, edit that file and `demo.htpasswd`.

---

## Choosing how `/login` behaves (`WEKO_SHIB_LOGIN_ONLY`)

weko-accounts' login screen has two shapes, selected by
`WEKO_ACCOUNTS_SHIB_INST_LOGIN_DIRECTLY_ENABLED`. `WEKO_SHIB_LOGIN_ONLY` does nothing but flip it.

| | `no` (default) | `yes` |
|---|---|---|
| `/login/` | the local login form (plus the GakuNin WAYF widget) | `<meta http-equiv="Refresh">` to `/secure/login.py` -> the IdP |
| Shibboleth entry point | `/weko/shib/sp/login` | either `/login/` or `/weko/shib/sp/login` |
| Logging in with a WEKO password | possible | **not possible** |

```bash
WEKO_SHIB=yes WEKO_SHIB_LOGIN_ONLY=yes bash deploy-amd64.sh
```

This is "pattern 4: Shibboleth (IdP) only" in instance.cfg's comments. **The login itself succeeds
either way**, but `yes` has the following side effects (all observed on a running cluster).

**1. A stopped IdP locks everyone out of the browser.**
`/login/` no longer renders a local form, so with the IdP down all you get is a 503. Recovery means
rewriting `invenio.cfg` through `kubectl exec`.

**2. Logging out logs you straight back in as the same user.**
WEKO's logout clears neither the SP session cookie (`_shibsession_*`) nor the IdP session, so visiting
`/login/` afterwards completes a fresh login without ever reaching the IdP - there is no way to switch
to a different account.

**3. Failures are reported silently.**
weko-accounts signals every failure with `flash()` plus a redirect to the login page
(`_redirect_method()`). With `yes` that login page is itself an immediate redirect, so the flash is
never rendered. For example, entering the wrong WEKO password on the account-linking screen:

| | lands on | what the page shows |
|---|---|---|
| `no` | `/login/` | `check_weko_user` is displayed |
| `yes` | the same linking screen | **nothing - it just returns to the form** |

2 and 3 are inherent to choosing "Shibboleth only" and would behave the same in production, so they are
an operational trade-off rather than a bug. The default here is `no` because 1 hurts most in a workshop.

---

## The GakuNin mAP integration (`WEKO_SHIB_MAP`)

WEKO decides its roles from `isMemberOf` (the mAP group membership). `WEKO_SHIB_MAP` selects where that
`isMemberOf` comes from.

| | What it does | Pods |
|---|---|---|
| `no` (default) | not used | `weko-shib-idp` |
| `sso` | the IdP carries `isMemberOf` in the SSO assertion | `weko-shib-idp` |
| `aggregation` | **as in production**: the SP sends a SAML2 AttributeQuery to an attribute authority via SimpleAggregation | `weko-shib-idp` + `weko-shib-map` |

```bash
WEKO_SHIB=yes WEKO_SHIB_MAP=aggregation bash deploy-amd64.sh
```

### Why the attribute authority is a separate Pod

**The SP deliberately skips querying an entity it already obtained attributes from.** Naming the login
IdP itself in `<Entity>` never produces an AttributeQuery. shibd says so directly:

```
DEBUG SimpleAggregation: using input attribute (eppn) as identifier for queries
DEBUG SimpleAggregation: skipping previously queried attribute source (https://idp.localhost/idp/shibboleth)
```

Production works because the GakuNin cloud gateway is a different entity from the institutional IdP, so
`map.localhost` is deployed separately here too (`71-shibboleth-map.yaml`). It is the same image with
different build ARGs.

Division of labour:

| | Attributes released |
|---|---|
| `idp.localhost` (institutional IdP) | authentication plus `eppn` / `mail` / `displayName` / `wekoId` / `wekoSocietyAffiliation` |
| `map.localhost` (attribute authority) | `isMemberOf` only, in response to an AttributeQuery |

With `aggregation` the institutional IdP does not release `isMemberOf` over SSO (it is built with
`IDP_RELEASE_ISMEMBEROF=no`), so `isMemberOf` appearing in the SP session proves the AttributeQuery
succeeded.

### The SP-side configuration (the same shape as the production procedure)

```xml
<MetadataProvider type="XML" validate="true" path="map-metadata.xml"/>

<AttributeResolver type="SimpleAggregation" attributeId="eppn"
                   format="urn:oid:1.3.6.1.4.1.5923.1.1.1.6">
    <Entity>https://map.localhost/idp/shibboleth</Entity>
    <saml2:Attribute xmlns:saml2="urn:oasis:names:tc:SAML:2.0:assertion"
                     Name="urn:oid:1.3.6.1.4.1.5923.1.5.1.1"
                     NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
                     FriendlyName="isMemberOf"/>
</AttributeResolver>
```

The `isMemberOf` entry in `attribute-map.xml` does **not** need adding - the image already ships it.

### What it took to make this work (all found by running it)

| Symptom | Cause and fix |
|---|---|
| no AttributeQuery is ever sent | it was the same entity as the login IdP → stand up a separate entity (`map.localhost`) |
| `MessageAuthenticationError` | the query was unsigned → `<ApplicationDefaults signing="back">` makes the SP sign back-channel messages |
| `Transport confidentiality required, but not available.` | the SP refuses plain HTTP → add the standard Shibboleth back-channel (8443, `idp-backchannel.p12`) to Tomcat |
| `No peer encryption credential found` | no encryption key in the metadata → put all three KeyDescriptors into the `AttributeAuthorityDescriptor` |
| TLS host name mismatch | the certificate is `CN=map.localhost` → pin the Service ClusterIP and point `map.localhost` at it with `hostAliases` in the tenant Pods |
| `no MetadataProvider available` | `mktemp`'s 0600 survived the `mv` so `_shibd` could not read it → chmod 0644 after placing |

### What WEKO needs configured

`gen-tenant.sh` appends this to `invenio.cfg`. **Overriding `WEKO_ACCOUNTS_ATTRIBUTE_MAP` is the crucial
part**: the stock map has no `shib_is_member_of` entry, and without one `parse_attributes()` looks for a
field named `SHIB_ATTR_IS_MEMBER_OF` while `login.py` actually posts `isMemberOf` (the name from
`/etc/nginx/shib_fastcgi_params`), so **the value is silently dropped**.

```python
WEKO_ACCOUNTS_SHIB_BIND_GAKUNIN_MAP_GROUPS = True
WEKO_ACCOUNTS_IDP_ENTITY_ID = "https://idp.localhost/idp/shibboleth"
WEKO_ACCOUNTS_ATTRIBUTE_MAP = {..., "shib_is_member_of": "isMemberOf"}
```

### Group names and roles

`create_fqdn_from_entity_id()` derives an FQDN from `WEKO_ACCOUNTS_IDP_ENTITY_ID` (`idp.localhost` →
`idp_localhost`) and matches it against the last path segment of the group name. The attribute authority
bakes the **institutional** IdP's FQDN into the group names, not its own (`IDP_GROUP_FQDN_HOST`).

| demo user | isMemberOf | WEKO role |
|---|---|---|
| `admin` | `/gakunin/idp_localhost/jc_roles_sysadm` | System Administrator |
| `libadmin` | `/gakunin/idp_localhost/jc_idp_localhost_ro_radm` | Repository Administrator |
| `teacher` | `/gakunin/idp_localhost/jc_idp_localhost_ro_cont` | Contributor |

### Syncing the role table (`sync_shib_gakunin_map_groups`)

The mAP group list is read from the Redis DB 4 hash `<FQDN>_gakunin_groups`, and the `jc_*` roles are
created and deleted from it. weko-accounts never writes that cache itself (a separate batch does in
production), so you can seed it by hand.

```bash
kubectl exec -n weko3re redis-0 -- redis-cli -n 4 hset idp_localhost_gakunin_groups \
  groups "jc_idp_localhost_ro_radm,jc_idp_localhost_ro_cont,jc_roles_sysadm"
```

After seeding it, logging in grants the role named after the group itself in addition to the one from
the pattern match:

```
admin@example.org    | jc_roles_sysadm, System Administrator
libadmin@example.org | jc_idp_localhost_ro_radm, Repository Administrator
```

### Checking

```bash
# did the attribute authority receive the AttributeQuery?
kubectl -n weko3 exec deploy/weko-shib-map -- \
  grep "Shibboleth-Audit.AttributeQuery" /opt/shibboleth-idp/logs/idp-process.log | tail -1

# did isMemberOf land in the SP session?
kubectl -n weko3 exec deploy/tenant1-web -c nginx -- \
  sh -c 'grep TRANSACTION.Login /var/log/shibboleth/transaction.log | tail -1'
```

---

## Adding users and changing isMemberOf

There are only two files to edit.

| What you want to change | File | Applies to |
|---|---|---|
| login ids and passwords | `shib-idp-build/idp-conf/credentials/demo.htpasswd` | the institutional IdP |
| `isMemberOf` (mAP groups) | the `isMemberOf` definition in `shib-idp-build/idp-conf/conf/attribute-resolver.xml` | the **attribute authority** with `aggregation`, the institutional IdP with `sso` |
| `wekoSocietyAffiliation` (the other role source) | the same file | the institutional IdP |

> **There are two sources of roles.** `check_in()` first assigns roles from `wekoSocietyAffiliation`,
> then adds the ones derived from `isMemberOf`. Changing only one leaves the other's roles in place, so
> look at both.

### 1) Adding a user

`HTPasswdCredentialValidator` only understands `$apr1$` / `{SHA}` / `crypt(3)` - **not bcrypt**.

```bash
htpasswd -nbm taro taro123    # use -m (apr1); -B (bcrypt) will not work
# taro:$apr1$qwMNHJL1$nHtH9wxr7rfaEBk8xL5MG0
```

Append the output to `demo.htpasswd`. With nothing added to `attribute-resolver.xml`, that user falls
through to the `<DefaultValue>` of `isMemberOf` / `wekoSocietyAffiliation` (Contributor).

### 2) Changing isMemberOf

`isMemberOf` is a `Mapped` attribute definition; add a `ValueMap` per login id.

```xml
<AttributeDefinition id="isMemberOf" xsi:type="Mapped">
    <InputAttributeDefinition ref="uid" />
    <DefaultValue passThru="false">__MAP_BASE__/jc___IDP_FQDN___ro_cont</DefaultValue>
    <ValueMap>
        <ReturnValue>__MAP_BASE__/jc_roles_sysadm</ReturnValue>
        <SourceValue>taro</SourceValue>       <!-- add this -->
    </ValueMap>
    ...
</AttributeDefinition>
```

Write `__IDP_FQDN__` as-is; it is substituted at build time. Only the last path segment is evaluated:

| last segment | WEKO role |
|---|---|
| `jc_roles_sysadm` | System Administrator |
| `jc_<institutional IdP FQDN>_ro_radm` | Repository Administrator |
| `jc_<institutional IdP FQDN>_ro_cadm` | Community Administrator |
| `jc_<institutional IdP FQDN>_ro_cont` | Contributor |

To also grant the role named after the group itself (`jc_idp_localhost_ro_radm` and friends), that role
has to exist in the Role table. Adding it to the Redis group list creates it (see below).

### 3) Applying the change

```bash
# aggregation: rebuild the attribute authority image
docker build --build-arg IDP_HOST=map.localhost \
             --build-arg IDP_ENTITYID=https://map.localhost/idp/shibboleth \
             --build-arg IDP_GROUP_FQDN_HOST=idp.localhost \
             -t weko3-shib-map:amd64 shib-idp-build
kind load docker-image weko3-shib-map:amd64 --name weko3
kubectl -n weko3 rollout restart deploy/weko-shib-map

# the institutional IdP (for new users or wekoSocietyAffiliation changes)
docker build --build-arg IDP_RELEASE_ISMEMBEROF=no -t weko3-shib-idp:amd64 shib-idp-build
kind load docker-image weko3-shib-idp:amd64 --name weko3
kubectl -n weko3 rollout restart deploy/weko-shib-idp
```

> **Rebuilding after editing `idp-conf/` does not change the signing keys** - only the layers after the
> installer `RUN` are invalidated - so there is no need to re-run `provision-shib.sh`.
> **Touching the Dockerfile above the installer line (an ARG, say) does regenerate the keys**, and then
> you must run `provision-shib.sh` to refresh the SP-side metadata. Forgetting it makes SSO fail with
> `Message was signed, but signature could not be verified.` and a 500.

### 4) Trying something out without rebuilding

Edit inside the Pod and have the IdP reload the configuration - no build needed (**it is lost on Pod
restart**).

```bash
# adding a user needs no reload at all - the htpasswd file is re-read every time
kubectl -n weko3 exec deploy/weko-shib-idp -- sh -c \
  "echo 'taro:\$apr1\$qwMNHJL1\$nHtH9wxr7rfaEBk8xL5MG0' >> /opt/shibboleth-idp/credentials/demo.htpasswd"

# after changing isMemberOf, reload just the attribute resolver
kubectl -n weko3 exec deploy/weko-shib-map -- sh -c \
  'vi /opt/shibboleth-idp/conf/attribute-resolver.xml'     # edit with whatever you like
kubectl -n weko3 exec deploy/weko-shib-map -- sh -c \
  'cd /opt/shibboleth-idp && IDP_BASE_URL=http://localhost:8080/idp bash bin/reload-service.sh -id shibboleth.AttributeResolverService'

# see what it now returns, without logging in
kubectl -n weko3 exec deploy/weko-shib-map -- sh -c \
  'cd /opt/shibboleth-idp && IDP_BASE_URL=http://localhost:8080/idp bash bin/aacli.sh -n taro -r https://tenant1.localhost/shibboleth-sp'
```

Reloadable services: `shibboleth.AttributeResolverService` / `shibboleth.AttributeFilterService` /
`shibboleth.MetadataResolverService` / `shibboleth.RelyingPartyResolverService`.

### 5) Making isMemberOf multi-valued (group information and so on)

#### The value shape the real GakuNin mAP returns

mAP returns **group URLs**, and for the same group it sends two flavours - one for members and one for
administrators.

```
https://cg.gakunin.jp/gr/research-project-a         … a member of that group
https://cg.gakunin.jp/gr/research-project-a/admin   … an administrator of that group
```

weko-accounts' `_assign_roles_to_user()` then

1. **skips** values ending in `/admin` and values containing `/sp/` (being a group admin is deliberately
   not reflected in the WEKO roles),
2. takes **only the last path segment** of the rest (`research-project-a`),
3. and uses that for the `jc_<FQDN>_ro_*` pattern match and the same-name role lookup.

So **the host part does not matter**. This set builds the values from `__MAP_BASE__` (default
`https://<the IdP host>/gr`), which the `IDP_GROUP_BASE_URL` build argument overrides.

#### Writing the definitions

Define each category separately and bundle them with a `Simple` definition.

```xml
<!-- (1) decides the role (one per user) -->
<AttributeDefinition id="mapRoleGroup" xsi:type="Mapped">
    <InputAttributeDefinition ref="uid" />
    <DefaultValue passThru="false">__MAP_BASE__/jc___IDP_FQDN___ro_cont</DefaultValue>
    <ValueMap><ReturnValue>__MAP_BASE__/jc_roles_sysadm</ReturnValue>
              <SourceValue>admin</SourceValue></ValueMap>
</AttributeDefinition>

<!-- (2) ordinary groups such as research projects (several may match; SourceValue is a regex) -->
<AttributeDefinition id="mapOrgGroup" xsi:type="Mapped">
    <InputAttributeDefinition ref="uid" />
    <ValueMap><ReturnValue>__MAP_BASE__/research-project-a</ReturnValue>
              <SourceValue>libadmin|teacher</SourceValue></ValueMap>
    <ValueMap><ReturnValue>__MAP_BASE__/lib-staff</ReturnValue>
              <SourceValue>libadmin</SourceValue></ValueMap>
</AttributeDefinition>

<!-- (3) the "administrator of that group" flavour; mAP sends it alongside the membership value -->
<AttributeDefinition id="mapOrgAdminGroup" xsi:type="Mapped">
    <InputAttributeDefinition ref="uid" />
    <ValueMap><ReturnValue>__MAP_BASE__/research-project-a/admin</ReturnValue>
              <SourceValue>libadmin</SourceValue></ValueMap>
</AttributeDefinition>

<!-- (4) a common group everyone gets (a Static connector; add <Value> entries for more) -->
<AttributeDefinition id="mapCommonGroup" xsi:type="Simple">
    <InputDataConnector ref="staticAttributes" attributeNames="commonGroup" />
</AttributeDefinition>

<!-- bundle (1)-(4); inputs with no value are simply skipped -->
<AttributeDefinition id="isMemberOf" xsi:type="Simple">
    <InputAttributeDefinition ref="mapRoleGroup" />
    <InputAttributeDefinition ref="mapOrgGroup" />
    <InputAttributeDefinition ref="mapOrgAdminGroup" />
    <InputAttributeDefinition ref="mapCommonGroup" />
</AttributeDefinition>
```

Add the value to `staticAttributes` as well (do not forget `exportAttributes`):

```xml
<DataConnector id="staticAttributes" xsi:type="Static"
               exportAttributes="schacHomeOrganization commonGroup">
    ...
    <Attribute id="commonGroup">
        <Value>__MAP_BASE__/all_users</Value>
    </Attribute>
</DataConnector>
```

The behaviour to keep in mind (all observed):

| | Behaviour |
|---|---|
| `ValueMap` in `Mapped` | **every match is returned**; repeat the same `SourceValue` to give one user several values |
| `SourceValue` | a **regular expression**, so `libadmin\|teacher` works |
| omitting `DefaultValue` | users matching nothing get **no value** - handy when bundling with `Simple` |
| multiple inputs to `Simple` | the values of all inputs are concatenated |
| SP → WEKO | the SP joins a multi-valued attribute into one environment variable separated by **`;`**, and `ShibUser.__init__` splits it back |

#### The result

```
$ python3 list-shib-users.py --table
eppn                  isMemberOf
--------------------  --------------------------------------------
admin@example.org     https://map.localhost/gr/all_users
admin@example.org     https://map.localhost/gr/jc_roles_sysadm
libadmin@example.org  https://map.localhost/gr/all_users
libadmin@example.org  https://map.localhost/gr/research-project-a/admin
libadmin@example.org  https://map.localhost/gr/research-project-a
libadmin@example.org  https://map.localhost/gr/lib-staff
libadmin@example.org  https://map.localhost/gr/jc_idp_localhost_ro_radm
teacher@example.org   https://map.localhost/gr/all_users
teacher@example.org   https://map.localhost/gr/research-project-a
teacher@example.org   https://map.localhost/gr/jc_idp_localhost_ro_cont
```

Only the `jc_*` one drives the role decision; the others are granted as **roles named after the group**
(when such a role exists in the Role table). What `libadmin` actually ends up with:

```
libadmin@example.org | Repository Administrator, all_users, jc_idp_localhost_ro_radm,
                       lib-staff, research-project-a
```

`Repository Administrator` comes from the `jc_..._ro_radm` pattern match; `all_users`, `lib-staff` and
`research-project-a` are granted because roles with those exact names exist.

**`research-project-a/admin` grants nothing.** Even with a role literally named `admin` present in the
Role table it stays unassigned, which shows the `/admin` skip is doing its job.

### 6) Adding more jc_* roles

The roles named after the groups come from the Redis group list, so add any new group there.

```bash
kubectl exec -n weko3re redis-0 -- redis-cli -n 4 hset idp_localhost_gakunin_groups \
  groups "jc_idp_localhost_ro_radm,jc_idp_localhost_ro_cont,jc_roles_sysadm,research-project-a,lib-staff,all_users"
```

Note that roles starting with `jc_` that are missing from the list are **deleted** on the next login.

### 7) Listing the current users with their groups

The user data and the group data **live in different places**. `isMemberOf` is never stored in WEKO's
database (`ShibUser.__init__` reads it and then `del`s it), so the IdP is the only place to see groups.

| What you want | Where it lives |
|---|---|
| eppn / mail / displayName / wekoSocietyAffiliation / `isMemberOf` | the IdP and the attribute authority (`aacli.sh`) |
| the linked WEKO account and the granted roles | WEKO's database (`shibboleth_user` x `accounts_role`) |

A script that joins the two is included.

```bash
python3 list-shib-users.py              # every user in htpasswd
python3 list-shib-users.py --user teacher
python3 list-shib-users.py --table      # just eppn and isMemberOf, as a table
python3 list-shib-users.py --tsv        # the same, tab separated (for grep/sort)
```

`--table` prints one row per group:

```
eppn                  isMemberOf
--------------------  --------------------------------------------
admin@example.org     /gakunin/idp_localhost/all_users
admin@example.org     /gakunin/idp_localhost/jc_roles_sysadm
libadmin@example.org  /gakunin/idp_localhost/all_users
libadmin@example.org  /gakunin/idp_localhost/lib_staff
libadmin@example.org  /gakunin/idp_localhost/dept_science
libadmin@example.org  /gakunin/idp_localhost/jc_idp_localhost_ro_radm
teacher@example.org   /gakunin/idp_localhost/all_users
teacher@example.org   /gakunin/idp_localhost/dept_science
teacher@example.org   /gakunin/idp_localhost/jc_idp_localhost_ro_cont
```

`--tsv` feeds into filtering and aggregation:

```bash
python3 list-shib-users.py --tsv | grep '/jc_'              # only the role-deciding groups
python3 list-shib-users.py --tsv | awk -F'\t' '{print $2}' | sort -u   # every group in use
```

```
IdP            : weko-shib-idp
グループの出どころ / groups from : weko-shib-map

== libadmin ==
  eppn                   : libadmin@example.org
  mail                   : libadmin@example.org
  displayName            : libadmin
  wekoSocietyAffiliation : 図書館員
  isMemberOf (4)         : /gakunin/idp_localhost/all_users
                           /gakunin/idp_localhost/lib_staff
                           /gakunin/idp_localhost/dept_science
                           /gakunin/idp_localhost/jc_idp_localhost_ro_radm
  --- WEKO (ログイン済み / logged in) ---
  WEKO アカウント        : libadmin@example.org
  付与済みロール         : all_users, dept_science, jc_idp_localhost_ro_radm, lib_staff, Repository Administrator
```

**No login is required** - `aacli.sh` only resolves attributes - so this is the quick way to check an
`attribute-resolver.xml` edit. The tail of the output also lists users that were removed from htpasswd
but still have a link in WEKO.

For a single user these are enough:

```bash
# what the IdP would issue
kubectl -n weko3 exec deploy/weko-shib-map -- sh -c \
  'cd /opt/shibboleth-idp && IDP_BASE_URL=http://localhost:8080/idp \
     bash bin/aacli.sh -n libadmin -r https://tenant1.localhost/shibboleth-sp'

# turn that JSON into an eppn / isMemberOf table
kubectl -n weko3 exec deploy/weko-shib-map -- sh -c \
  'cd /opt/shibboleth-idp && IDP_BASE_URL=http://localhost:8080/idp \
     bash bin/aacli.sh -n libadmin -r https://tenant1.localhost/shibboleth-sp' 2>/dev/null \
| python3 -c '
import sys, json, re
d = json.loads(re.search(r"\{.*\}", sys.stdin.read(), re.S).group(0))
a = {x["name"]: x.get("values", []) for x in d.get("attributes", [])}
eppn = (a.get("eduPersonPrincipalName") or ["-"])[0]
print("%-24s %s" % ("eppn", "isMemberOf"))
for g in a.get("isMemberOf") or ["-"]:
    print("%-24s %s" % (eppn, g))
'

# the WEKO-side link and roles
PGM=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n weko3 "$PGM" -- psql -U postgres -d wekodb -c \
  "select s.shib_eppn, u.email, s.shib_role_authority_name, string_agg(r.name, ', ' order by r.name)
     from shibboleth_user s join accounts_user u on u.id = s.weko_uid
     left join accounts_userrole ur on ur.user_id = u.id
     left join accounts_role r on r.id = ur.role_id
    group by 1,2,3 order by 1;"
```

### 8) A worked example

After adding `taro` and pointing its `isMemberOf` at `jc_roles_sysadm`, a fresh login gives:

```
taro@example.org | Contributor, System Administrator, jc_roles_sysadm
```

`System Administrator` and `jc_roles_sysadm` come from `isMemberOf`, while `Contributor` comes from the
`wekoSocietyAffiliation` default (教員) - both sources are visibly in play.

---

## How this differs from production

| item | production (GakuNin / weko-k8s) | here |
|---|---|---|
| IdP | the GakuNin IdPs | one test IdP inside the cluster |
| attribute authority | the GakuNin cloud gateway (mAP) | one test AA from the same image (with `aggregation`) |
| group data | mAP manages the real groups | derived statically from the login id (a `Mapped` definition) |
| IdP selection | chosen through a DS (WAYF) | pinned to a single IdP (`<SSO entityID=...>`) |
| metadata | fetched from the federation, signature verified | a local file, trusted unconditionally |
| attribute release | policy scoped per SP | released to every registered SP |
| authentication | LDAP | htpasswd |
| nginx | `weko.conf` (IP restrictions, WAF-like rules) | `default-shib.conf` (only the locations needed) |
| `NO_CHECK_WEKOSOCIETYAFFILIATION` | `FALSE` (reject when the attribute is missing) | `TRUE` (let the login through anyway) |

To make `NO_CHECK_WEKOSOCIETYAFFILIATION` match production (`FALSE`), edit `default-shib.conf` in
`21-nginx-config.yaml` and run `kubectl rollout restart deploy/<tenant>-web -n weko3`.

---

## A caveat about TLS

TLS terminates at the Ingress and nginx itself serves plaintext. shibd, however, builds the ACS URL and
the SAML `Destination` from the FastCGI parameters it receives, so **unless it is told https the
validation fails**. `default-shib.conf` therefore rewrites `HTTPS` / `REQUEST_SCHEME` / `SERVER_PORT`
based on the `X-Forwarded-Proto` the Ingress adds. The IdP has `RemoteIpValve` in Tomcat for the same
reason.

Emptying `WEKO_TLS_ISSUER=` to turn HTTPS off breaks that assumption and SAML stops working.
**Keep HTTPS enabled** when using the Shibboleth login.

---

## Checking and troubleshooting

```bash
# is the IdP loading its configuration? (200 = yes; 403 = a gap in access-control.xml)
curl -sk -o /dev/null -w '%{http_code}\n' -H 'Host: idp.localhost' https://localhost/idp/status

# IdP logs
kubectl logs -n weko3 deploy/weko-shib-idp --tail=100
kubectl exec -n weko3 deploy/weko-shib-idp -- tail -100 /opt/shibboleth-idp/logs/idp-process.log

# SP (shibd) logs - this is where you see whether the attributes arrived
kubectl logs -n weko3 deploy/tenant1-web -c nginx --tail=100

# can the SP read the IdP metadata?
kubectl exec -n weko3 deploy/tenant1-web -c nginx -- ls -l /etc/shibboleth/

# the attribute authority (with WEKO_SHIB_MAP=aggregation)
kubectl logs -n weko3 deploy/weko-shib-map --tail=100
kubectl exec -n weko3 deploy/weko-shib-map -- \
  grep "Shibboleth-Audit.AttributeQuery" /opt/shibboleth-idp/logs/idp-process.log | tail -3

# what the SP actually received (isMemberOf present = the AttributeQuery worked)
kubectl exec -n weko3 deploy/tenant1-web -c nginx -- \
  sh -c 'grep TRANSACTION.Login /var/log/shibboleth/transaction.log | tail -1'
```

| symptom | where to look |
|---|---|
| `/secure/login.py` returns 502 | is `fcgiwrap` installed (the nginx image build in `deploy-amd64.sh`)? is the patch rewriting the CGI status line to `Status:` applied? |
| 403/500 instead of a redirect to the IdP | shibd is not running, or `/etc/shibboleth/` is incomplete. Check that the manifests were regenerated with `WEKO_SHIB=yes` |
| the IdP reports a `Message Destination` error | `X-Forwarded-Proto` is not reaching it (did you disable HTTPS?) |
| the SP rejects the assertion | the IdP image was rebuilt without re-running `provision-shib.sh` (signing key mismatch) |
| the login works but no role is assigned | `wekoSocietyAffiliation` is not being released. Check `attribute-filter.xml` and `attribute-resolver.xml` |
| `isMemberOf` never arrives | is `shib_is_member_of` in `WEKO_ACCOUNTS_ATTRIBUTE_MAP`? (without it the value is silently dropped). With `aggregation`, is there an AttributeQuery in the attribute authority's audit log? |
| `Transport confidentiality required` | the request is not reaching the attribute authority's 8443 back-channel. Check the Service port 8443 and the `map.localhost` `hostAliases` entry |

---

## Cleaning up

To remove just the IdP (and the attribute authority):

```bash
kubectl delete -f 70-shibboleth-idp.yaml
kubectl delete -f 71-shibboleth-map.yaml --ignore-not-found
kubectl delete configmap weko-idp-sp-metadata -n weko3
```

To put WEKO3 back to Shibboleth-disabled, redeploy without `WEKO_SHIB`.

```bash
bash deploy-amd64.sh
```
