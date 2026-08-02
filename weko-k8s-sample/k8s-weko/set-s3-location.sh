#!/bin/bash
# Set each tenant's files_location to the S3 (MinIO) type and create the per-tenant bucket.
# Run it after weko-init.sh (weko only connects s3fs with the location's S3 info when type='s3').
# The S3 credentials match the tenant secret (MinIO by default).
set -uo pipefail
cd "$(dirname "$0")"
TFILE="${1:-tenants.txt}"
S3_KEY="${S3_KEY:-wekominio}"; S3_SECRET="${S3_SECRET:-wekominio-secret-key}"; S3_ENDPOINT="${S3_ENDPOINT:-http://minio:9000}"
# PG master pod (HA operator or standalone)
PG=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
[ -z "$PG" ] && PG=$(kubectl get pod -n weko3 -l app=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
echo "postgres master pod = $PG"

# 1) create all per-tenant buckets at once
BUCKETS=$(grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$TFILE" | awk '{print "l/weko-"$1}' | tr '\n' ' ')
echo "create buckets: $BUCKETS"
cat <<EOF | kubectl apply -f - >/dev/null 2>&1
apiVersion: batch/v1
kind: Job
metadata: { name: mc-s3loc, namespace: weko3 }
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      nodeSelector: { nodeType: DATA }
      containers:
      - name: mc
        image: minio/mc:RELEASE.2025-04-08T15-39-49Z
        command: ["/bin/sh","-c"]
        args: ["mc alias set l ${S3_ENDPOINT} ${S3_KEY} ${S3_SECRET} && mc mb -p ${BUCKETS} && mc ls l"]
EOF
kubectl wait -n weko3 --for=condition=complete job/mc-s3loc --timeout=120s 2>&1 | tail -1
kubectl delete job -n weko3 mc-s3loc --ignore-not-found >/dev/null 2>&1

# 2) switch files_location to the S3 type in each tenant DB
# s3_maximum_number_of_parts は NULL のままにしてはいけない。type='s3' の Location では
# invenio-s3 の set_blocksize が ceil(size / location.s3_maximum_number_of_parts) を計算するため、
# NULL だとサイズのあるアップロードが必ず TypeError (int / NoneType) になり、PUT は 200 を返すのに
# 中身が 0 バイトのまま保存される。アプリ側の既定 S3_MAXIMUM_NUMBER_OF_PARTS と同じ 10000 を入れる。
# s3_maximum_number_of_parts must not be left NULL. On a type='s3' Location invenio-s3's set_blocksize
# computes ceil(size / location.s3_maximum_number_of_parts), so a NULL makes every sized upload raise
# TypeError (int / NoneType): the PUT still answers 200 but the object is stored as 0 bytes. Use 10000,
# the same value as the application-level S3_MAXIMUM_NUMBER_OF_PARTS default.
#
# readonly_access_key / readonly_secret_key も必須。invenio-s3 の init_s3fs_info は書き込み (mode='wb')
# のときだけ access_key / secret_key を使い、読み出しでは readonly_* 系を見る。どちらも未設定だと
# 空文字が渡り、ダウンロードが botocore の NoCredentialsError で 500 になる。デモの MinIO は
# 資格情報が 1 組だけなので同じ値を入れる (本番なら読み取り専用ユーザーを別途作る)。
# readonly_access_key / readonly_secret_key are required as well. invenio-s3's init_s3fs_info only uses
# access_key / secret_key when writing (mode='wb'); reads look at the readonly_* pair. With neither set
# it passes empty strings and downloads fail with botocore's NoCredentialsError as a 500. The demo MinIO
# has a single credential pair, so reuse it here (in production, create a separate read-only user).
grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$TFILE" | while read -r NAME DBNAME HOST _; do
  BUCKET="weko-${NAME}"
  echo "=== $DBNAME: files_location -> s3://$BUCKET (type=s3) ==="
  kubectl exec -n weko3 "$PG" -- psql -U postgres -d "$DBNAME" -c \
    "UPDATE files_location SET type='s3', uri='s3://${BUCKET}', access_key='${S3_KEY}', secret_key='${S3_SECRET}', readonly_access_key='${S3_KEY}', readonly_secret_key='${S3_SECRET}', s3_endpoint_url='${S3_ENDPOINT}', s3_send_file_directly=true, s3_default_block_size=5242880, s3_maximum_number_of_parts=10000, s3_signature_version='s3v4' WHERE name='local';" 2>&1 | sed 's/^/  /'
done
echo "=== done ==="
echo "===       no weko web restart needed (the location is read from the DB immediately) ==="
