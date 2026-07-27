# Switching HTTPS to Let's Encrypt (amd64 / k8s-weko)

Split out of [HTTPS certificates](./README-amd64.en.md#https-certificates) in `README-amd64.en.md`.
Read this **only when moving to public operation**. Let's Encrypt cannot issue for a test environment
(`*.localhost`), so keep the default automatic issuance (the bundled root CA `weko-ca-issuer`) there.

You keep the mechanism from option A (cert-manager + `WEKO_TLS_ISSUER`) and **only swap the issuer**.
Neither the tenant manifests nor `gen-tenant.sh` need any change.

> **Preconditions (issuance fails without them)**
> - **A real FQDN is required.** `*.localhost` **cannot** be issued: Let's Encrypt only certifies
>   domains that resolve in public DNS.
> - **With HTTP-01**: the FQDN must point at this host's global IP and **80/tcp** must be reachable
>   from the internet (the ACME validation request comes in that way).
> - If you cannot expose it, or you need a wildcard certificate, use **DNS-01** (see below).
> - kind's `extraPortMappings` already publishes host ports 80/443; only your router/firewall and DNS
>   remain.

**1) Switch to a real FQDN.** Put the real domain in the HOST column of `tenants.txt` and point its
DNS A/AAAA record at this host's global IP.
```
# NAME    DBNAME   HOST                    ADMIN_EMAIL           ...
tenant1   wekodb   repo.example.ac.jp      admin@example.ac.jp   ...
```

**2) Create the ClusterIssuer.** Always go through **staging** first: production rate limits are
strict and repeated failures lock you out (50 certificates per domain per week, 5 failures per hour).
```bash
cat <<'YAML' | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: admin@example.ac.jp          # expiry notices go here; use a real address
    privateKeySecretRef:
      name: letsencrypt-staging-account # where the ACME account key is stored (created automatically)
    solvers:
    - http01:
        ingress:
          ingressClassName: nginx
YAML
kubectl get clusterissuer letsencrypt-staging     # wait until READY=True
```

**3) Confirm issuance against staging.**
```bash
WEKO_TLS_ISSUER=letsencrypt-staging bash deploy-amd64.sh
kubectl describe certificate -n weko3 tenant1-tls   # the Events show whether issuance succeeded
```
> A staging certificate is **not trusted by browsers** (its issuer is `(STAGING) Let's Encrypt`).
> The only thing being verified here is that DNS and port 80 are reachable so the ACME challenge passes.

**4) Switch to production.** Once staging succeeds, create the same issuer with the production
`server` URL and re-run with `WEKO_TLS_ISSUER` pointed at it.
```bash
cat <<'YAML' | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.ac.jp
    privateKeySecretRef:
      name: letsencrypt-prod-account
    solvers:
    - http01:
        ingress:
          ingressClassName: nginx
YAML

# Delete the staging certificates first; a leftover Secret means nothing is re-issued
kubectl delete certificate,secret -n weko3 -l app.kubernetes.io/managed-by=cert-manager --ignore-not-found
WEKO_TLS_ISSUER=letsencrypt-prod bash deploy-amd64.sh
```

**5) Verify.**
```bash
echo | openssl s_client -connect localhost:443 -servername repo.example.ac.jp 2>/dev/null \
  | openssl x509 -noout -issuer -enddate
# issuer=C = US, O = Let's Encrypt, CN = ...   <- production has no "(STAGING)" prefix
```
From here cert-manager renews automatically 30 days before the 90-day expiry, and no root CA has to be
added to any trust store.

## DNS-01 (port 80 cannot be exposed, or you need a wildcard)
Prove ownership with a DNS TXT record instead of HTTP-01. This needs API credentials for your DNS
provider.
```yaml
    solvers:
    - dns01:
        cloudflare:                      # example; route53 / clouddns work the same way
          apiTokenSecretRef:
            name: cloudflare-api-token
            key: api-token
```
```bash
kubectl create secret generic cloudflare-api-token -n cert-manager --from-literal=api-token=<TOKEN>
```
A wildcard (`*.example.ac.jp`) **can only be obtained through DNS-01**. To cover every tenant with a
single certificate, use this method and name the shared Secret with `WEKO_TLS_SECRET`.

## Going back to the internal CA
```bash
WEKO_TLS_ISSUER=weko-ca-issuer bash deploy-amd64.sh    # = the default
```

## Common pitfalls

| Symptom | Cause |
|---|---|
| The `Certificate` stays `READY=False` | Look at `kubectl describe certificate -n weko3 <name>` and `kubectl get challenge -A` |
| The challenge stays `pending` | `http://<FQDN>/.well-known/acme-challenge/...` is not reachable from outside. Check DNS, firewall and NAT |
| `too many failed authorizations` | Too many retries against production. **Always pass staging first**; you can only wait it out |
| Cannot issue for `.localhost` | By design: Let's Encrypt only issues for public domains. Use option A |
