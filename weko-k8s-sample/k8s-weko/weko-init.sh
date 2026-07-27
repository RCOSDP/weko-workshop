#!/bin/bash
# Initialize a weko3 tenant. Runs inside the web container (step 7 of deploy-arm64.sh pipes it in).
#
# Approach: do not re-implement the sequence; run the image's own scripts/populate-instance.sh.
#   This file used to transcribe only part of it, so the 10 languages, widget types, author prefixes
#   and affiliations, facet search settings, report units/targets, admin_settings, API certificates,
#   billing and most `access allow` grants were never created, leaving the admin screens empty
#   (for example, no language settings at all).
#   Calling the real script also keeps us in sync with upstream weko. The environment variables it
#   needs are already set in the web container.
set -x

POPULATE=/code/scripts/populate-instance.sh
if [ ! -x "$POPULATE" ]; then
  echo "ERROR: $POPULATE not found"; exit 1
fi

# populate-instance.sh runs with `set -o errexit`, so it fails on e.g. `users create` when the data
# already exists. Drop the database first so that a retry after a partial failure still works
# (populate-instance.sh drops it as well).
export PATH=/home/invenio/.virtualenvs/invenio/bin:$PATH
invenio db drop --yes-i-know || true

# Drop the Elasticsearch indices too. install.sh starts from `docker compose down -v`, which wipes ES;
# here ES is persistent, so leftover indices make populate-instance.sh's `index init` fail with
# resource_already_exists_exception. Only this tenant's SEARCH_INDEX_PREFIX is destroyed.
invenio index destroy --yes-i-know || true
# The stats/events indices are concrete indices behind aliases and survive `index destroy`; remove them.
ES="${INVENIO_ELASTICSEARCH_HOST}"; PFX="${SEARCH_INDEX_PREFIX}"
for ev in celery-task item-create top-view record-view file-download file-preview search; do
  curl -sS -XDELETE "http://${ES}:9200/${PFX}-events-stats-${ev}-*" >/dev/null 2>&1
  curl -sS -XDELETE "http://${ES}:9200/${PFX}-stats-${ev}-*"        >/dev/null 2>&1
done

# populate-instance.sh needs bash (it uses arrays); it sources virtualenvwrapper itself.
if ! bash "$POPULATE"; then
  echo "ERROR: populate-instance.sh failed"; exit 1
fi

echo "===== WEKO_INIT_DONE ====="
