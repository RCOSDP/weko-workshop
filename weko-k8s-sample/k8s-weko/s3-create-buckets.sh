#!/bin/bash
# s3-create-buckets.sh — S3 (SeaweedFS, http://s3:9000) にバケットを作る。すでにあるものはそのまま。
#   クラスタ内で aws-cli の Job を1回走らせる。deploy の手順4 (共有バケット) と set-s3-location.sh
#   (テナントごとのバケット) から呼ぶ。作れなかったら 0 以外で終わる。
# s3-create-buckets.sh — create buckets on S3 (SeaweedFS, http://s3:9000); existing ones are left alone.
#   Runs one aws-cli Job inside the cluster. Called by the deploy's step 4 (shared buckets) and by
#   set-s3-location.sh (per-tenant buckets). Exits non-zero when a bucket could not be created.
#
#   bash s3-create-buckets.sh weko-backup weko-content weko-esbackup
set -uo pipefail
[ $# -ge 1 ] || { echo "usage: bash $0 <bucket>..."; exit 2; }
S3_KEY="${S3_KEY:-wekominio}"; S3_SECRET="${S3_SECRET:-wekominio-secret-key}"; S3_ENDPOINT="${S3_ENDPOINT:-http://s3:9000}"
# public.ecr.aws から取るので Docker Hub の pull 制限を受けない。pull-images-*.sh が読み込んでおく。
# Comes from public.ecr.aws, so the Docker Hub rate limit does not apply. pull-images-*.sh preloads it.
S3_CLI_IMAGE="${S3_CLI_IMAGE:-public.ecr.aws/aws-cli/aws-cli:2.40.1}"
JOB=s3-create-buckets
echo "create buckets on $S3_ENDPOINT: $*"
# S3 が応答する前に Job を走らせると失敗するので、先に Ready を待つ
# A Job run before S3 answers just fails, so wait for it to be Ready first
kubectl -n weko3 rollout status deploy/s3 --timeout=300s >/dev/null \
  || { echo "ERROR: S3 (deploy/s3) is not ready"; kubectl -n weko3 get pod -l app=s3; exit 1; }
kubectl delete job -n weko3 "$JOB" --ignore-not-found >/dev/null 2>&1
cat <<YAML | kubectl apply -f - >/dev/null || exit 1
apiVersion: batch/v1
kind: Job
metadata: { name: $JOB, namespace: weko3 }
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      nodeSelector: { nodeType: DATA }
      containers:
      - name: aws
        image: $S3_CLI_IMAGE
        env:
        - { name: AWS_ACCESS_KEY_ID, value: "$S3_KEY" }
        - { name: AWS_SECRET_ACCESS_KEY, value: "$S3_SECRET" }
        - { name: AWS_DEFAULT_REGION, value: us-east-1 }
        command: ["/bin/sh", "-c"]
        args:
        - |
          set -e
          for b in $*; do
            aws --endpoint-url $S3_ENDPOINT s3api head-bucket --bucket "\$b" 2>/dev/null \
              && echo "exists: \$b" || aws --endpoint-url $S3_ENDPOINT s3 mb "s3://\$b"
          done
YAML
# Complete か Failed (backoffLimit を使い切った) のどちらかになるまで待つ。complete だけを待つと、
# 失敗が確定していても timeout まで待たされる。
# Wait until it is Complete or Failed (backoffLimit used up). Waiting for complete alone sits out the
# whole timeout even after the failure is final.
ok=no
for _ in $(seq 1 100); do
  st=$(kubectl get job -n weko3 "$JOB" -o jsonpath='{.status.conditions[?(@.status=="True")].type}' 2>/dev/null)
  case "$st" in *Complete*) ok=yes; break ;; *Failed*) break ;; esac
  sleep 3
done
kubectl logs -n weko3 "job/$JOB" 2>&1 | sed 's/^/  /'
if [ "$ok" = no ]; then
  echo "ERROR: could not create the buckets"
  kubectl get pod -n weko3 -l job-name="$JOB" 2>&1 | sed 's/^/  /'
  exit 1   # Job は調査用に残す / the Job is kept for inspection
fi
kubectl delete job -n weko3 "$JOB" --ignore-not-found >/dev/null 2>&1
