#!/bin/bash
# Load the seed data (SQL) shipped with the weko source into each tenant database.
# This is the second half of the weko source's install.sh.
#
# install.sh runs the following *after* populate-instance.sh. Without them the item types, index tree
# and workflows stay empty and nothing can be registered.
#   1. scripts/demo/fix_lang_code_column.sql      normalize the language code column (zh variants)
#   2. scripts/demo/item_type.sql                 item type definitions
#   3. scripts/demo/indextree.sql                 index tree
#   4. invenio workflow init action_status,Action workflow action definitions
#   5. scripts/demo/defaultworkflow.sql           default workflow
#   6. scripts/demo/doi_identifier.sql            DOI identifier settings
#   7. postgresql/ddl/W-OA-user_activity_log.sql  sequence for the activity log
#   8. scripts/demo/restricted_mail_template.sql  mail templates for restricted access
#
# docker cp is not available here, so each file is copied into the Pod and read with psql -f.
# The database name differs per tenant, so it is resolved from tenants.txt.
#
# Run: bash seed-demo.sh   (called right after step 7 of deploy-arm64.sh)
set -uo pipefail
cd "$(dirname "$0")"
TFILE="${1:-tenants.txt}"
WEKO_SRC="${WEKO_SRC:-$HOME/weko}"

PGM=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
[ -n "$PGM" ] || { echo "ERROR: PostgreSQL master pod not found"; exit 1; }
echo "postgres master pod = $PGM"

# Keep install.sh's order; fix_lang_code_column must come before item_type.
SQLS_PRE="scripts/demo/fix_lang_code_column.sql scripts/demo/item_type.sql scripts/demo/indextree.sql"
SQLS_POST="scripts/demo/defaultworkflow.sql scripts/demo/doi_identifier.sql \
           postgresql/ddl/W-OA-user_activity_log.sql scripts/demo/restricted_mail_template.sql"

run_sql() {  # run_sql <db> <relative path>
  local db=$1 rel=$2 f="$WEKO_SRC/$rel" base
  base=$(basename "$rel")
  if [ ! -f "$f" ]; then
    echo "  WARNING: $rel not found, skipped"; return 0
  fi
  # item_type.sql is 16 MB; piping it into `kubectl exec -i` makes the websocket drop with an
  # "i/o timeout". Copy it into the Pod first and read it with psql -f, the same way install.sh
  # uses docker cp (16 MB takes about 0.2 s).
  if ! kubectl cp "$f" "weko3/$PGM:/tmp/$base" >/dev/null 2>&1; then
    echo "  FAIL $rel (copy into the Pod failed)"; return 1
  fi
  # Do not set ON_ERROR_STOP - this matches install.sh. These are pg_dump-style files that drop
  # constraints and indexes before reloading the data. On the current schema a few of those DROPs fail
  # on dependencies, which is expected; the following INSERT/COPY statements still apply.
  # With ON_ERROR_STOP=1 the script aborts on the first failed DROP and no data is loaded at all.
  # Success is judged afterwards by checking the row counts instead (see verify below).
  kubectl exec -n weko3 "$PGM" -- \
    psql -U postgres -d "$db" -f "/tmp/$base" > /tmp/seed-$$.log 2>&1
  # grep -c prints "0" and still exits 1 when there is no match, so `|| echo 0` would yield "0\n0".
  local errs; errs=$(grep -c '^psql:.*ERROR:' /tmp/seed-$$.log 2>/dev/null); errs=${errs:-0}
  if [ "$errs" = "0" ]; then
    echo "  OK   $rel"
  else
    # Expected errors (e.g. dropping a constraint that something depends on) show up here too;
    # report the count but keep going.
    echo "  OK   $rel ($errs ignored SQL errors)"
    grep '^psql:.*ERROR:' /tmp/seed-$$.log | head -2 | sed 's/^/       /'
  fi
  rm -f /tmp/seed-$$.log
  kubectl exec -n weko3 "$PGM" -- rm -f "/tmp/$base" >/dev/null 2>&1
}

FAILED=""
while read -r NAME DBNAME HOST _; do
  echo "=== seed demo data: $NAME (db=$DBNAME) ==="
  for rel in $SQLS_PRE; do run_sql "$DBNAME" "$rel" || FAILED="$FAILED $NAME:$rel"; done

  # The workflow actions come from an invenio command, not SQL, and defaultworkflow.sql depends on them.
  POD=$(kubectl get pod -n weko3 -l app=${NAME}-web -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
  if [ -n "$POD" ]; then
    if kubectl exec -n weko3 "$POD" -c web -- \
         bash -lc 'export PATH=/home/invenio/.virtualenvs/invenio/bin:$PATH; invenio workflow init action_status,Action' \
         > /tmp/wf-$$.log 2>&1; then
      echo "  OK   invenio workflow init action_status,Action"
    else
      echo "  FAIL invenio workflow init"; tail -5 /tmp/wf-$$.log | sed 's/^/       /'
      FAILED="$FAILED $NAME:workflow-init"
    fi
    rm -f /tmp/wf-$$.log
  else
    echo "  WARNING: Pod for ${NAME}-web not found"
    FAILED="$FAILED $NAME:workflow-init"
  fi

  for rel in $SQLS_POST; do run_sql "$DBNAME" "$rel" || FAILED="$FAILED $NAME:$rel"; done

  # Verify by row count. Some SQL errors are expected, so this is what decides success.
  echo "  -- verify --"
  for t in item_type item_type_name index workflow_action workflow_flow_define doi_identifier mail_templates; do
    n=$(kubectl exec -n weko3 "$PGM" -- psql -U postgres -d "$DBNAME" -tAc \
          "select count(*) from \"$t\"" 2>/dev/null | tr -d '[:space:]')
    printf '     %-22s %s\n' "$t" "${n:-?}"
    case "${n:-0}" in 0|"") FAILED="$FAILED $NAME:$t(empty)";; esac
  done
done < <(grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$TFILE")

if [ -n "$FAILED" ]; then
  echo "ERROR: seeding failed for:$FAILED"
  exit 1
fi
echo "=== seed demo data done ==="
