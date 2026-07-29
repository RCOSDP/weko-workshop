# Shibboleth Identity Provider 5 — ワークショップ用テスト IdP
# Shibboleth Identity Provider 5 - test IdP for the workshop
#
# Docker Hub の既製 Shibboleth IdP イメージ (unicon/i2incommon/tier) はいずれも amd64 専用なので、
# ここでは公式 tarball から自前でビルドする。IdP 本体は純 Java なのでアーキテクチャ非依存であり、
# ベースイメージ (eclipse-temurin / tomcat) がマルチアーキなので arm64 でも amd64 でもそのまま通る。
# The prebuilt Shibboleth IdP images on Docker Hub (unicon/i2incommon/tier) are all amd64-only, so this
# builds from the official tarball instead. The IdP itself is pure Java (architecture independent) and
# both base images (eclipse-temurin / tomcat) are multi-arch, so this builds natively on arm64 and amd64.
#
# IdP 5 は jakarta.servlet なので Tomcat 10.1 以上が必要 (Tomcat 9 は javax で不可)。
# IdP 5 uses jakarta.servlet, so it needs Tomcat 10.1+ (Tomcat 9 is javax-based and will not work).

ARG IDP_VERSION=5.2.3

########## stage 1: インストーラを流して IDP_HOME を作る / run the installer to produce IDP_HOME ##########
FROM eclipse-temurin:17-jdk AS installer
ARG IDP_VERSION
# IdP のホスト名 / entityID / scope。SP メタデータもこれに合わせて生成する (provision-shib.sh)。
# IdP host name / entityID / scope. The SP metadata is generated to match (see provision-shib.sh).
ARG IDP_HOST=idp.localhost
ARG IDP_ENTITYID=https://idp.localhost/idp/shibboleth
ARG IDP_SCOPE=example.org
# デモ用の固定パスワード。鍵は毎ビルド新規生成され、そのビルドの中だけで使われる。
# Fixed demo passwords. The keys are freshly generated per build and only used inside that build.
ARG IDP_KEYSTORE_PASSWORD=changeit
ARG IDP_SEALER_PASSWORD=changeit
WORKDIR /build
ADD https://shibboleth.net/downloads/identity-provider/${IDP_VERSION}/shibboleth-identity-provider-${IDP_VERSION}.tar.gz ./idp.tar.gz
RUN tar xzf idp.tar.gz && mv "shibboleth-identity-provider-${IDP_VERSION}" src && rm idp.tar.gz

# 無人インストール。--noPrompt だけでは scope などを聞かれるので propertyFile で全部渡す。
# Unattended install. --noPrompt alone still needs the scope etc., so everything is passed via propertyFile.
RUN printf '%s\n' \
      "idp.host.name=${IDP_HOST}" \
      "idp.entityID=${IDP_ENTITYID}" \
      "idp.scope=${IDP_SCOPE}" \
      "idp.keystore.password=${IDP_KEYSTORE_PASSWORD}" \
      "idp.sealer.password=${IDP_SEALER_PASSWORD}" \
      "idp.noprompt=true" \
      "idp.target.dir=/opt/shibboleth-idp" \
      > /build/install.properties \
 && cd /build/src && bash bin/install.sh --noPrompt --propertyFile /build/install.properties

# isMemberOf を SSO アサーションで公開するか。同じイメージを 2 つの役割で使い分けるためのスイッチ。
#   yes … 機関 IdP が SSO で isMemberOf も配る (WEKO_SHIB_MAP=sso 相当) / 属性認証局として使う場合
#   no  … SSO では配らない。SimpleAggregation で属性認証局から取らせたいときの機関 IdP 側
# Whether isMemberOf is released in the SSO assertion. This switch lets one image serve both roles.
#   yes … the institutional IdP also hands out isMemberOf over SSO (the WEKO_SHIB_MAP=sso case), and
#         it is what the attribute authority itself needs
#   no  … not released over SSO; used for the institutional IdP when SimpleAggregation should fetch it
#         from the attribute authority instead
ARG IDP_RELEASE_ISMEMBEROF=yes
# isMemberOf のグループ名に埋め込む FQDN の元になるホスト名。既定は自分自身 (IDP_HOST)。
# 学認mAP のグループ名は「所属機関 IdP の FQDN」を含む (jc_<機関IdP の FQDN>_ro_*) ので、
# 属性認証局として立てる場合は自分ではなく機関 IdP のホスト名を渡すこと。
# weko-accounts 側は WEKO_ACCOUNTS_IDP_ENTITY_ID (= 機関 IdP) から同じ変換で FQDN を作って照合する。
#
# The host name that the FQDN embedded in the isMemberOf group names is derived from; defaults to this
# IdP itself (IDP_HOST). GakuNin mAP group names carry the *institutional* IdP's FQDN
# (jc_<institutional IdP FQDN>_ro_*), so when building the attribute authority, pass the institutional
# IdP's host name rather than its own. weko-accounts derives the same FQDN from
# WEKO_ACCOUNTS_IDP_ENTITY_ID (the institutional IdP) when matching.
ARG IDP_GROUP_FQDN_HOST=
# isMemberOf の値の前半 (mAP のグループ URL のベース)。本番の学認mAP は
#   https://cg.gakunin.jp/gr/<グループ名>          … そのグループのメンバー
#   https://cg.gakunin.jp/gr/<グループ名>/admin    … そのグループの管理者
# という URL を返す。ここでは同じ形をローカルのホスト名で作る。
# weko-accounts が見るのは最後のセグメントだけなので、ホスト部分は何でもよい。
# The first half of the isMemberOf values (the base URL of the mAP groups). The real GakuNin mAP returns
#   https://cg.gakunin.jp/gr/<group>          … a member of that group
#   https://cg.gakunin.jp/gr/<group>/admin    … an administrator of that group
# The same shape is reproduced here with a local host name. weko-accounts only looks at the last path
# segment, so the host part is irrelevant.
ARG IDP_GROUP_BASE_URL

# 上の 3 つはインストーラより後ろで宣言している。前に置くとインストーラのレイヤのキャッシュが
# 切れて署名鍵が作り直され、SP 側のメタデータ更新 (provision-shib.sh) が必須になってしまうため。
# The three ARGs above are declared after the installer. Declaring them before it would invalidate the
# installer layer, regenerate the signing keys, and force an SP-side metadata refresh
# (provision-shib.sh) every time one of them changes.

# 設定オーバーレイ。conf/ は IDP_HOME から実行時に読まれるので war の再ビルドは不要。
# Config overlay. conf/ is read from IDP_HOME at runtime, so the war does not need rebuilding.
COPY idp-conf/ /overlay/
# __IDP_FQDN__ は weko-accounts の create_fqdn_from_entity_id() と同じ変換
# (entityID のホスト名の "." と "-" を "_" に置換) にそろえる必要がある。
# __IDP_FQDN__ must match weko-accounts' create_fqdn_from_entity_id() - the entityID host with
# "." and "-" replaced by "_".
RUN IDP_FQDN=$(echo "${IDP_GROUP_FQDN_HOST:-${IDP_HOST}}" | tr '.-' '__') \
 && cp -a /overlay/. /opt/shibboleth-idp/ && rm -rf /overlay \
 && MAP_BASE="${IDP_GROUP_BASE_URL:-https://${IDP_HOST}/gr}" \
 && sed -i -e "s/__IDP_SCOPE__/${IDP_SCOPE}/g" -e "s/__IDP_FQDN__/${IDP_FQDN}/g" \
           -e "s#__MAP_BASE__#${MAP_BASE}#g" \
      /opt/shibboleth-idp/conf/attribute-resolver.xml \
 && ! grep -qE '__IDP_SCOPE__|__IDP_FQDN__|__MAP_BASE__' /opt/shibboleth-idp/conf/attribute-resolver.xml \
 && if [ "${IDP_RELEASE_ISMEMBEROF}" != "yes" ]; then \
      sed -i '/attributeID="isMemberOf"/d' /opt/shibboleth-idp/conf/attribute-filter.xml; \
    fi \
 && echo "isMemberOf released over SSO: ${IDP_RELEASE_ISMEMBEROF}; group FQDN: ${IDP_FQDN}; base: ${MAP_BASE}"

# LDAP を使わないので ldap.properties は無効化する (未使用でも起動時に解決されると警告が出る)。
# LDAP is not used, so neutralize ldap.properties (it is resolved at startup even when unused).
RUN sed -i 's/^idp\.authn\.LDAP/#idp.authn.LDAP/' /opt/shibboleth-idp/conf/ldap.properties

########## stage 2: Tomcat 10.1 に載せる / deploy onto Tomcat 10.1 ##########
FROM tomcat:10.1-jdk17-temurin
ARG IDP_HOST=idp.localhost
ARG IDP_KEYSTORE_PASSWORD=changeit

COPY --from=installer /opt/shibboleth-idp /opt/shibboleth-idp

# idp.war を /idp コンテキストに配置。既定の webapps (ROOT/manager など) は捨てる。
# Deploy idp.war at the /idp context and drop the default webapps (ROOT/manager/...).
RUN rm -rf "$CATALINA_HOME"/webapps/* \
 && cp /opt/shibboleth-idp/war/idp.war "$CATALINA_HOME/webapps/idp.war"

# /idp/status だけは Velocity ではなく JSP (WEB-INF/jsp/status.jsp) で描画される。IdP が本来想定する
# Jetty は JSTL を同梱しているが Tomcat は同梱しないため、無いと jakarta/servlet/jsp/jstl/core/Config が
# NoClassDefFoundError になり /idp/status が 500 を返す (= readinessProbe が通らない)。
# ログイン画面自体は Velocity なのでこの 2 つの jar が要るのは status だけ。
# Only /idp/status renders through a JSP (WEB-INF/jsp/status.jsp) rather than Velocity. Jetty - the
# container the IdP targets - bundles JSTL, but Tomcat does not, so without it
# jakarta/servlet/jsp/jstl/core/Config throws NoClassDefFoundError and /idp/status returns 500
# (which means the readinessProbe never passes). The login screen itself is Velocity, so these two jars
# are needed for status alone.
ADD https://repo1.maven.org/maven2/jakarta/servlet/jsp/jstl/jakarta.servlet.jsp.jstl-api/3.0.0/jakarta.servlet.jsp.jstl-api-3.0.0.jar /usr/local/tomcat/lib/
ADD https://repo1.maven.org/maven2/org/glassfish/web/jakarta.servlet.jsp.jstl/3.0.1/jakarta.servlet.jsp.jstl-3.0.1.jar /usr/local/tomcat/lib/
RUN chmod 0644 /usr/local/tomcat/lib/jakarta.servlet.jsp.jstl*.jar

# Ingress で TLS 終端するので Tomcat は平文 8080 で受ける。IdP は受信リクエストの Destination を
# メタデータ上の https://<host>/idp/... と突き合わせるため、X-Forwarded-Proto を尊重させないと
# "Message Destination" 検証で落ちる。RemoteIpValve でスキーム/ポートを付け替える。
# TLS is terminated at the Ingress so Tomcat serves plain 8080. The IdP compares the inbound request's
# Destination against the https://<host>/idp/... endpoints in its metadata, so without honoring
# X-Forwarded-Proto it fails the message-destination check. RemoteIpValve rewrites the scheme/port.
RUN sed -i 's#</Host>#  <Valve className="org.apache.catalina.valves.RemoteIpValve" remoteIpHeader="X-Forwarded-For" protocolHeader="X-Forwarded-Proto" protocolHeaderHttpsValue="https" httpsServerPort="443" />\n      </Host>#' \
      "$CATALINA_HOME/conf/server.xml" \
 && grep -q RemoteIpValve "$CATALINA_HOME/conf/server.xml"

# Shibboleth 標準のバックチャネル (8443)。SP は SimpleAggregation の SOAP を平文 HTTP では送らず
# "Transport confidentiality required, but not available." で失敗するため、TLS が要る。
# 証明書はインストーラが作る idp-backchannel.p12 を使う。これはメタデータの KeyDescriptor にも
# 載るので、SP はメタデータ内の鍵と突き合わせて (ExplicitKey) サーバを信頼できる。公的な CA も
# ホスト名の一致も不要という、Shibboleth のバックチャネルの流儀。
# The standard Shibboleth back-channel (8443). The SP refuses to send the SimpleAggregation SOAP over
# plain HTTP - it fails with "Transport confidentiality required, but not available." - so TLS is
# required. The certificate is the idp-backchannel.p12 the installer creates; it is also published in
# the metadata KeyDescriptor, so the SP trusts the server by matching the key from metadata
# (ExplicitKey). No public CA and no host name match needed - that is how Shibboleth back-channels work.
RUN printf '%s\n' \
      '        <Connector port="8443" protocol="org.apache.coyote.http11.Http11NioProtocol"' \
      '                   maxThreads="150" SSLEnabled="true" scheme="https" secure="true">' \
      '          <SSLHostConfig>' \
      '            <Certificate certificateKeystoreFile="/opt/shibboleth-idp/credentials/idp-backchannel.p12"' \
      '                         certificateKeystoreType="PKCS12"' \
      "                         certificateKeystorePassword=\"${IDP_KEYSTORE_PASSWORD}\" type=\"RSA\"/>" \
      '          </SSLHostConfig>' \
      '        </Connector>' \
      > /tmp/bc-connector.xml \
 && sed -i "/<\/Service>/e cat /tmp/bc-connector.xml" "$CATALINA_HOME/conf/server.xml" \
 && rm -f /tmp/bc-connector.xml \
 && grep -q 'port="8443"' "$CATALINA_HOME/conf/server.xml"

# tomcat ユーザで動かす (IDP_HOME の logs/metadata に書けるようにしておく)
# Run as the tomcat user (it must be able to write IDP_HOME's logs/metadata)
RUN useradd -r -u 1001 -d /opt/shibboleth-idp tomcat \
 && chown -R 1001:0 /opt/shibboleth-idp "$CATALINA_HOME/webapps" "$CATALINA_HOME/work" "$CATALINA_HOME/temp" "$CATALINA_HOME/logs" \
 && chmod -R g+rwX /opt/shibboleth-idp

ENV JAVA_OPTS="-Didp.home=/opt/shibboleth-idp -Dnet.shibboleth.idp.home=/opt/shibboleth-idp -Djava.security.egd=file:/dev/urandom -Xms512m -Xmx1024m"
ENV IDP_HOME=/opt/shibboleth-idp

USER 1001
EXPOSE 8080 8443
CMD ["catalina.sh", "run"]
