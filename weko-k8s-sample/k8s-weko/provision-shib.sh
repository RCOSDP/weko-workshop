#!/bin/bash
# Shibboleth SP <-> IdP の信頼関係を作る / establish the Shibboleth SP <-> IdP trust.
#
# やること / what it does:
#   1. SP の署名・暗号鍵を 1 組だけ生成し .shib-sp/ に保存する (再実行しても同じ鍵を使う)
#      Generate a single SP signing/encryption key pair into .shib-sp/ (reused on re-runs)
#   2. IdP イメージから idp-metadata.xml を取り出す (IdP の署名鍵と必ず一致する)。
#      WEKO_SHIB_MAP=aggregation なら属性認証局の map-metadata.xml も作り、SOAP の
#      AttributeService を追記する
#      Extract idp-metadata.xml from the IdP image (guaranteed to match the IdP's signing key).
#      With WEKO_SHIB_MAP=aggregation, also build the attribute authority's map-metadata.xml and append
#      its SOAP AttributeService
#   3. tenants.txt の全テナント分の SP メタデータを 1 つの EntitiesDescriptor にまとめ、
#      ConfigMap weko-idp-sp-metadata として IdP に渡す
#      Combine the SP metadata of every tenant in tenants.txt into one EntitiesDescriptor and hand it to
#      the IdP as the ConfigMap weko-idp-sp-metadata
#   4. 各テナントの /fs-shibboleth/<tenant> (NFS) に shibboleth2.xml / idp-metadata.xml /
#      attribute-map-weko.xml / SP 鍵を配置する
#      Place shibboleth2.xml / idp-metadata.xml / attribute-map-weko.xml / the SP key into each tenant's
#      /fs-shibboleth/<tenant> on NFS
#
# 実行順 / ordering: gen-tenant.sh -> provision-nfs.sh -> provision-shib.sh -> kubectl apply (tenants, 70-*)
#
# Usage:
#   bash provision-shib.sh [tenants.txt]
#   WEKO_IDP_IMAGE=weko3-shib-idp:arm64 bash provision-shib.sh
set -uo pipefail
cd "$(dirname "$0")"
TFILE="${1:-tenants.txt}"
WEKO_IDP_IMAGE="${WEKO_IDP_IMAGE:-weko3-shib-idp:arm64}"
# shib-idp-build/Dockerfile の ARG と一致させること / must match the ARGs in shib-idp-build/Dockerfile
WEKO_IDP_HOST="${WEKO_IDP_HOST:-idp.localhost}"
WEKO_IDP_ENTITYID="${WEKO_IDP_ENTITYID:-https://${WEKO_IDP_HOST}/idp/shibboleth}"
# 学認mAP 連携の再現方法 / how the GakuNin mAP integration is reproduced:
#   no          … isMemberOf を使わない (既定)                          / do not use isMemberOf (default)
#   sso         … isMemberOf を SSO アサーションに載せる                / carry isMemberOf in the SSO assertion
#   aggregation … 本番と同じく SP が SimpleAggregation で問い合わせる   / the SP queries for it via SimpleAggregation
WEKO_SHIB_MAP="${WEKO_SHIB_MAP:-no}"
# 属性認証局 (学認mAP 相当) 側。WEKO_SHIB_MAP=aggregation のときだけ使う。
# WEKO_MAP_AA_LOCATION は SimpleAggregation のバックチャネル (SOAP) の宛先。shibd は Pod 内で動くので
# クラスタ内 Service を平文 HTTP で直接叩く。Ingress 経由の https にすると、ローカル CA の証明書を
# shibd のトラストストアに入れる必要が生じるため、あえてこちらにしている。
# The attribute authority (GakuNin mAP equivalent); only used with WEKO_SHIB_MAP=aggregation.
# WEKO_MAP_AA_LOCATION is where the SimpleAggregation back-channel (SOAP) points. shibd runs inside a
# Pod, so it talks to the in-cluster Service over plain HTTP. Going through the Ingress over https would
# mean installing the local CA certificate into shibd's trust store, which is why this route is used.
WEKO_MAP_IMAGE="${WEKO_MAP_IMAGE:-weko3-shib-map:arm64}"
WEKO_MAP_HOST="${WEKO_MAP_HOST:-map.localhost}"
WEKO_MAP_ENTITYID="${WEKO_MAP_ENTITYID:-https://${WEKO_MAP_HOST}/idp/shibboleth}"
WEKO_MAP_AA_LOCATION="${WEKO_MAP_AA_LOCATION:-https://${WEKO_MAP_HOST}:8443/idp/profile/SAML2/SOAP/AttributeQuery}"
# 鍵とメタデータの保存先。gen-tenant.sh の .secret-seed と同じく、消さない限り信頼関係は安定する。
# Where the key and metadata live. Like gen-tenant.sh's .secret-seed, the trust stays stable unless deleted.
SPDIR="${WEKO_SHIB_SP_DIR:-.shib-sp}"

mkdir -p "$SPDIR"

########## 1) SP の鍵 / the SP key ##########
if [ ! -s "$SPDIR/sp-key.pem" ] || [ ! -s "$SPDIR/sp-cert.pem" ]; then
  echo "=== generating the SP signing/encryption key pair ($SPDIR) ==="
  openssl req -x509 -nodes -newkey rsa:3072 -days 3650 \
    -keyout "$SPDIR/sp-key.pem" -out "$SPDIR/sp-cert.pem" \
    -subj "/CN=weko3-shibboleth-sp" 2>/dev/null || { echo "ERROR: openssl failed"; exit 1; }
  chmod 600 "$SPDIR/sp-key.pem"
else
  echo "=== reusing the existing SP key pair ($SPDIR) ==="
fi
# メタデータに埋める証明書本体 (PEM のヘッダ/フッタを除いたもの)
# The certificate body embedded in the metadata (PEM without the header/footer lines)
SP_CERT_BODY=$(sed -e '/-----BEGIN CERTIFICATE-----/d' -e '/-----END CERTIFICATE-----/d' "$SPDIR/sp-cert.pem")

########## 2) IdP のメタデータ / the IdP metadata ##########
echo "=== extracting idp-metadata.xml from $WEKO_IDP_IMAGE ==="
if ! docker run --rm "$WEKO_IDP_IMAGE" cat /opt/shibboleth-idp/metadata/idp-metadata.xml \
     > "$SPDIR/idp-metadata.xml" 2>/dev/null || [ ! -s "$SPDIR/idp-metadata.xml" ]; then
  echo "ERROR: could not read the metadata from $WEKO_IDP_IMAGE (build it first: shib-idp-build/)"
  exit 1
fi
# インストーラが生成するメタデータは冒頭に "example metadata only" のコメントが付くだけで内容は正しい。
# 実際に使う entityID が想定と違うと SP が IdP を見つけられないので、そこだけ検証しておく。
# The installer-generated metadata only carries an "example metadata only" comment; the content is valid.
# A mismatching entityID would leave the SP unable to find the IdP, so verify just that.
if ! grep -q "entityID=\"$WEKO_IDP_ENTITYID\"" "$SPDIR/idp-metadata.xml"; then
  echo "ERROR: the entityID in the image metadata does not match WEKO_IDP_ENTITYID=$WEKO_IDP_ENTITYID"
  grep -o 'entityID="[^"]*"' "$SPDIR/idp-metadata.xml" | head -1
  exit 1
fi
echo "  idp entityID = $WEKO_IDP_ENTITYID"

# 属性認証局のメタデータを作る。インストーラが生成するメタデータには IDPSSODescriptor
# (front-channel の SSO/SLO) しか無く AttributeAuthorityDescriptor が存在しないため、SP は
# 問い合わせ先を決められない。SOAP の AttributeService を追記し、署名鍵は IDPSSODescriptor の
# ものを再利用する (同じエンティティが署名する)。
#
# Build the attribute authority's metadata. The installer-generated metadata only has an
# IDPSSODescriptor (front-channel SSO/SLO) and no AttributeAuthorityDescriptor, so the SP has nowhere
# to send the query. This appends the SOAP AttributeService, reusing the signing key from the
# IDPSSODescriptor (the same entity signs).
if [ "$WEKO_SHIB_MAP" = "aggregation" ]; then
  echo "=== extracting map-metadata.xml from $WEKO_MAP_IMAGE ==="
  if ! docker run --rm "$WEKO_MAP_IMAGE" cat /opt/shibboleth-idp/metadata/idp-metadata.xml \
       > "$SPDIR/map-metadata.xml" 2>/dev/null || [ ! -s "$SPDIR/map-metadata.xml" ]; then
    echo "ERROR: could not read the metadata from $WEKO_MAP_IMAGE (build it first: shib-idp-build/)"
    exit 1
  fi
  if ! grep -q "entityID=\"$WEKO_MAP_ENTITYID\"" "$SPDIR/map-metadata.xml"; then
    echo "ERROR: the entityID in the image metadata does not match WEKO_MAP_ENTITYID=$WEKO_MAP_ENTITYID"
    grep -o 'entityID="[^"]*"' "$SPDIR/map-metadata.xml" | head -1
    exit 1
  fi
  if ! grep -q 'AttributeAuthorityDescriptor' "$SPDIR/map-metadata.xml"; then
    # IDPSSODescriptor の KeyDescriptor を全部そのまま取り出す。3 つとも役割が違い、どれも要る:
    #   signing (1つ目)    … バックチャネル TLS のサーバ証明書 (idp-backchannel.crt)
    #   signing (2つ目)    … 応答アサーションの署名検証 (idp-signing.crt)
    #   encryption         … SP が NameID を暗号化するのに使う。無いと
    #                        "No peer encryption credential found" になる
    # Lift every KeyDescriptor out of the IDPSSODescriptor verbatim. All three have distinct roles and
    # all are needed:
    #   signing (1st) … the back-channel TLS server certificate (idp-backchannel.crt)
    #   signing (2nd) … verifying the signature on the response assertion (idp-signing.crt)
    #   encryption    … used by the SP to encrypt the NameID; without it you get
    #                   "No peer encryption credential found"
    KEYDESC=$(awk '/<md:KeyDescriptor/{f=1} f{print} /<\/md:KeyDescriptor>/{f=0}' \
                "$SPDIR/map-metadata.xml")
    if [ -z "$KEYDESC" ]; then
      echo "ERROR: could not extract the KeyDescriptors from the AA metadata"; exit 1
    fi
    AA=$(printf '%s\n' \
      '    <md:AttributeAuthorityDescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">' \
      "$KEYDESC" \
      "        <md:AttributeService Binding=\"urn:oasis:names:tc:SAML:2.0:bindings:SOAP\" Location=\"$WEKO_MAP_AA_LOCATION\"/>" \
      '        <md:NameIDFormat>urn:oid:1.3.6.1.4.1.5923.1.1.1.6</md:NameIDFormat>' \
      '    </md:AttributeAuthorityDescriptor>')
    # </md:EntityDescriptor> の直前に差し込む / insert just before </md:EntityDescriptor>
    TMPMD=$(mktemp)
    awk -v aa="$AA" '/<\/md:EntityDescriptor>/{print aa} {print}' "$SPDIR/map-metadata.xml" > "$TMPMD" \
      && mv "$TMPMD" "$SPDIR/map-metadata.xml"
    # mktemp は 0600 で作り mv はそのモードを保つ。shibd は _shibd ユーザなので読めなくなり
    # "Unable to access local file" → "no MetadataProvider available" で SSO ごと 500 になる。
    # mktemp creates the file 0600 and mv keeps that mode. shibd runs as _shibd and would lose read
    # access, giving "Unable to access local file" -> "no MetadataProvider available" and a 500 on SSO.
    chmod 0644 "$SPDIR/map-metadata.xml"
    grep -q 'AttributeAuthorityDescriptor' "$SPDIR/map-metadata.xml" \
      || { echo "ERROR: failed to inject the AttributeAuthorityDescriptor"; exit 1; }
  fi
  echo "  map entityID = $WEKO_MAP_ENTITYID"
  echo "  AttributeService -> $WEKO_MAP_AA_LOCATION"
fi

########## 3) SP メタデータ (全テナント) -> ConfigMap ##########
SPMETA="$SPDIR/sp-metadata.xml"
{
  echo '<?xml version="1.0" encoding="UTF-8"?>'
  echo '<!-- generated by provision-shib.sh from '"$TFILE"' - do not edit -->'
  echo '<EntitiesDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata"'
  echo '                    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"'
  echo '                    Name="urn:weko3:kind:sps">'
} > "$SPMETA"
TENANTS=""
while read -r NAME DBNAME HOST EMAIL PASS INIT _; do
  [ -n "${NAME:-}" ] || continue
  TENANTS="$TENANTS $NAME:$HOST"
  cat >> "$SPMETA" <<XML
  <EntityDescriptor entityID="https://$HOST/shibboleth-sp">
    <SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
      <KeyDescriptor use="signing">
        <ds:KeyInfo><ds:X509Data><ds:X509Certificate>
$SP_CERT_BODY
        </ds:X509Certificate></ds:X509Data></ds:KeyInfo>
      </KeyDescriptor>
      <KeyDescriptor use="encryption">
        <ds:KeyInfo><ds:X509Data><ds:X509Certificate>
$SP_CERT_BODY
        </ds:X509Certificate></ds:X509Data></ds:KeyInfo>
      </KeyDescriptor>
      <SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                           Location="https://$HOST/Shibboleth.sso/SLO/Redirect"/>
      <SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                           Location="https://$HOST/Shibboleth.sso/SLO/POST"/>
      <NameIDFormat>urn:oasis:names:tc:SAML:2.0:nameid-format:transient</NameIDFormat>
      <AssertionConsumerService index="1" isDefault="true"
                                Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                Location="https://$HOST/Shibboleth.sso/SAML2/POST"/>
      <AssertionConsumerService index="2"
                                Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST-SimpleSign"
                                Location="https://$HOST/Shibboleth.sso/SAML2/POST-SimpleSign"/>
    </SPSSODescriptor>
  </EntityDescriptor>
XML
done < <(grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$TFILE")
echo '</EntitiesDescriptor>' >> "$SPMETA"
echo "=== generated $SPMETA for:$TENANTS ==="

kubectl create configmap weko-idp-sp-metadata -n weko3 \
  --from-file=sp-metadata.xml="$SPMETA" --dry-run=client -o yaml | kubectl apply -f - >/dev/null \
  || { echo "ERROR: failed to apply the ConfigMap weko-idp-sp-metadata"; exit 1; }
echo "  applied ConfigMap weko3/weko-idp-sp-metadata"

########## 4) 各テナントの /fs-shibboleth へ配置 / place into each tenant's /fs-shibboleth ##########
# provision-nfs.sh と同じく、export ボリュームをマウントした busybox の Pod 経由で書き込む。
# As in provision-nfs.sh, write through a busybox Pod that mounts the same export volume.
SEED_POD=weko-shib-seed
kubectl -n nfs-system delete pod "$SEED_POD" --ignore-not-found >/dev/null 2>&1
kubectl apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata: { name: $SEED_POD, namespace: nfs-system }
spec:
  nodeSelector: { nodeType: DATA }
  restartPolicy: Never
  containers:
  - name: seed
    image: busybox:1.36
    command: ["sh","-c","sleep 3600"]
    volumeMounts:
    - { name: export-volume, mountPath: /export }
  volumes:
  - name: export-volume
    persistentVolumeClaim: { claimName: nfs-export }
EOF
kubectl -n nfs-system wait --for=condition=ready pod/"$SEED_POD" --timeout=180s >/dev/null || {
  echo "ERROR: seed pod not ready"; exit 1; }
trap 'kubectl -n nfs-system delete pod "$SEED_POD" --ignore-not-found >/dev/null 2>&1' EXIT

while read -r NAME DBNAME HOST EMAIL PASS INIT _; do
  [ -n "${NAME:-}" ] || continue
  echo "=== provision shibboleth SP config: $NAME (host=$HOST) ==="
  TMP=$(mktemp -d)
  # WEKO_SHIB_MAP=aggregation のときだけ SimpleAggregation のブロックを差し込む。
  # sed の r コマンドは「その行の後」に挿入するので、プレースホルダ行自体は d で消す。
  # Insert the SimpleAggregation block only with WEKO_SHIB_MAP=aggregation. sed's r command appends
  # after the line, so the placeholder line itself is deleted with d.
  SA_SED=""; MD_SED=""
  if [ "$WEKO_SHIB_MAP" = "aggregation" ]; then
    SA_SED="/__SIMPLE_AGGREGATION__/r shib-sp-template/simple-aggregation.xml"
    MD_SED="/__MAP_METADATA__/r shib-sp-template/map-metadata-provider.xml"
    cp "$SPDIR/map-metadata.xml" "$TMP/map-metadata.xml"
  fi
  # 2 パスに分ける。sed の r は挿入した内容をその周期の s コマンドに通さないので、差し込みを
  # 済ませてからでないと挿入したファイル内の __MAP_ENTITYID__ が置換されない。
  # Two passes: sed's r does not run the same cycle's s commands over the inserted text, so
  # __MAP_ENTITYID__ inside the inserted files is only substituted after the insertion is done.
  sed ${SA_SED:+-e "$SA_SED"} ${MD_SED:+-e "$MD_SED"} \
      -e "/__SIMPLE_AGGREGATION__/d" -e "/__MAP_METADATA__/d" \
      shib-sp-template/shibboleth2.xml \
    | sed -e "s#__WEKO3_VHOST__#${HOST}#g" \
          -e "s#__IDP_ENTITYID__#${WEKO_IDP_ENTITYID}#g" \
          -e "s#__MAP_ENTITYID__#${WEKO_MAP_ENTITYID}#g" \
    > "$TMP/shibboleth2.xml"
  if grep -qE '__WEKO3_VHOST__|__IDP_ENTITYID__|__MAP_ENTITYID__' "$TMP/shibboleth2.xml"; then
    echo "ERROR: unsubstituted placeholder left in shibboleth2.xml for $NAME"; exit 1
  fi
  cp shib-sp-template/attribute-map-weko.xml "$TMP/attribute-map-weko.xml"
  cp "$SPDIR/idp-metadata.xml" "$TMP/idp-metadata.xml"
  cp "$SPDIR/sp-cert.pem" "$TMP/sp-cert.pem"
  cp "$SPDIR/sp-key.pem"  "$TMP/sp-key.pem"
  # ここは常に上書きする (信頼関係の実体なので、古い鍵が残っていると SAML が通らない)
  # Always overwrite here: this is the trust material itself, and a stale key breaks SAML
  kubectl exec -n nfs-system "$SEED_POD" -- mkdir -p "/export/fs-shibboleth/$NAME" >/dev/null 2>&1
  tar -C "$TMP" -cf - . | kubectl exec -i -n nfs-system "$SEED_POD" -- \
    tar -C "/export/fs-shibboleth/$NAME" -xf - 2>/dev/null
  # shibd は _shibd ユーザで動くので、置いたファイルは全部読めるようにしておく
  # (kind のローカル検証用の緩い権限)。鍵だけを対象にすると、他のファイルのモードが
  # 生成過程で 0600 になったときに "no MetadataProvider available" 等で気づきにくく壊れる。
  # shibd runs as the _shibd user, so everything placed here must be readable (loose permissions for
  # local kind testing). Restricting this to the keys alone makes it easy to break silently - e.g. with
  # "no MetadataProvider available" - if some other file ends up 0600 during generation.
  kubectl exec -n nfs-system "$SEED_POD" -- sh -c \
    "chmod 0644 /export/fs-shibboleth/$NAME/*" >/dev/null 2>&1
  echo "  placed shibboleth2.xml / idp-metadata.xml / attribute-map-weko.xml / sp-{key,cert}.pem${WEKO_SHIB_MAP:+$( [ "$WEKO_SHIB_MAP" = aggregation ] && echo " / map-metadata.xml" )}"
  rm -rf "$TMP"
done < <(grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$TFILE")

echo "=== shibboleth provisioning done ==="
