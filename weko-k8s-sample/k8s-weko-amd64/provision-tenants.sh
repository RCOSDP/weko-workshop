#!/bin/bash
# Create the PostgreSQL DB and the RabbitMQ vhost for each tenant.
# - PG   : CREATE DATABASE (owner=weko) when DBNAME does not exist yet
# - MQ   : rabbitmqctl add_vhost "<NAME>/" + set_permissions weko (same naming as upstream make_rabbitmq_vhost.sh)
set -uo pipefail
cd "$(dirname "$0")"
TFILE="${1:-tenants.txt}"

PG=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master -o jsonpath='{.items[0].metadata.name}')
MQ=$(kubectl get pod -n weko3 -l app.kubernetes.io/name=weko-rabbitmq  -o jsonpath='{.items[0].metadata.name}')
echo "postgres pod=$PG  rabbitmq pod=$MQ"

# The RabbitMQ weko user: the Cluster Operator only creates its generated default user, so create the
# user weko (used by celery/web) here (or reset its password when it already exists).
kubectl exec -n weko3 "$MQ" -c rabbitmq -- rabbitmqctl add_user weko weko 2>&1 | sed 's/^/  MQ: /'
kubectl exec -n weko3 "$MQ" -c rabbitmq -- rabbitmqctl change_password weko weko 2>&1 | sed 's/^/  MQ: /'
kubectl exec -n weko3 "$MQ" -c rabbitmq -- rabbitmqctl set_user_tags weko administrator 2>&1 | sed 's/^/  MQ: /'
kubectl exec -n weko3 "$MQ" -c rabbitmq -- rabbitmqctl set_permissions -p / weko ".*" ".*" ".*" 2>&1 | sed 's/^/  MQ: /' 

grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$TFILE" | while read -r NAME DBNAME HOST EMAIL PASS INIT _; do
  echo "=== provision tenant: $NAME (db=$DBNAME vhost=$NAME/) ==="
  # PostgreSQL DB
  exists=$(kubectl exec -n weko3 "$PG" -- psql -U weko -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DBNAME'" 2>/dev/null)
  if [ "$exists" = "1" ]; then
    echo "  PG: database '$DBNAME' already exists (skip)"
  else
    kubectl exec -n weko3 "$PG" -- psql -U weko -d postgres -c "CREATE DATABASE \"$DBNAME\" OWNER weko;" && echo "  PG: created '$DBNAME'"
  fi
  # RabbitMQ vhost (with the trailing slash)
  kubectl exec -n weko3 "$MQ" -c rabbitmq -- rabbitmqctl add_vhost "$NAME/" 2>&1 | sed 's/^/  MQ: /'
  kubectl exec -n weko3 "$MQ" -c rabbitmq -- rabbitmqctl set_permissions -p "$NAME/" weko ".*" ".*" ".*" 2>&1 | sed 's/^/  MQ: /'
done
echo "=== provisioning done ==="
