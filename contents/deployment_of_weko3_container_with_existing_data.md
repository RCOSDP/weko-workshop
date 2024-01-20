# Deployment of WEKO3 container with existing data

## Copying content files

When deploying as a separate organization, copy the files to avoid file inconsistencies.

The following methods are available for copying.

### Using the rclone command

```
$ rclone sync -v <copy source bucket>://<copy source prefix> <copy destination bucket>://<copy destination prefix
```

### Using OCI command

Once you have downloaded the file, you need to download it locally.

```
$ oci os object bulk-download --namespace <namespace> --bucket-name <copy source bucket name> --download-dir <download destination directory> --prefix <copy source prefix>.
```

Upload the locally downloaded file to the destination.

```
$ oci os object bulk-upload --namespace <namespace> --bucket-name <destination bucket name> --src-dir <destination directory>
```

## Deployment of WEKO3


If DB does not exist in PostgreSQL, create it.

```
$ DB=<DB name> #Name of the institution with ". Name with "-" replaced by "_".
$ PG_MASTER=$(kubectl get po -n weko3pg -l spilo-role=master -o jsonpath="{.items[].metadata.name}")
$ kubectl exec -n weko3pg $PG_MASTER -c postgres -- psql -U invenio postgres -c "create database $DB"
```

## Restoring PostgreSQL

Since the data for restore does not contain schema definitions, create schema definitions for the target DB.

From the Web POD, invenio db init and invenio db create can be executed.

```
$ WEB_POD=<institution's WEB POD name to create schema definition>.
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio db init
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio db create
```

Restore using the prepared restore data.

```
$ kubectl get pods -l application=spilo -L spilo-role -n weko3pg
NAME READY STATUS RESTARTS AGE SPILO-ROLE
weko3pg-cluster-0 2/2 Running 0 37d replica
weko3pg-cluster-1 2/2 Running 0 32d replica
weko3pg-cluster-2 2/2 Running 0 37d master
$ pg_master=weko-postgresql-2
$ repo=xxxxxx.repo.nii.ac.jp
$ db=$(echo ${repo} | tr . - _)
$ sql=/var/lib/postgresql/backup/path/to/weko.sql # kubectl:/fs-pgbackup/ -> pg_cluster:/var/lib/postgresql/backup/
$ declare -p pg_master repo db sql
```

```
$ kubectl exec -n weko3pg ${pg_master} -c postgres -- psql -U postgres ${db} -f ${sql}
$ kubectl exec -n weko3pg ${pg_master} -c postgres -- psql -U postgres postgres -c "select * from pg_stat_replication"
 
# If the delay (write_lag, flush_lag, replay_lag) is large time during select, it may be failing.
```


The error "ERROR: relation "public.accounts_role" does not exist" during restore can be ignored.

Change the settings in the contents file.

```
$ PG_MASTER=$(kubectl get po -n weko3pg -l spilo-role=master -o jsonpath="{.items[].metadata.name}")
$ kubectl exec -n weko3pg $PG_MASTER -- psql -U invenio <DB name> -c "update files_location set uri='s3://<destination bucket name>/<DB name>', access_key='<destination bucket access_key>', secret_key='<secret key for destination bucket>';"
$ kubectl exec -n weko3pg $PG_MASTER -- psql -U invenio <DB name> -c "update files_files set uri=replace(uri,'<copy source bucket name>/<copy source DB name>','<copy destination bucket name/<copy destinationDB name>');"
```

Use the following command to check if the settings have been changed.

```
$ PG_MASTER=$(kubectl get po -n weko3pg -l spilo-role=master -o jsonpath="{.items[].metadata.name}")
$ kubectl exec -n weko3pg $PG_MASTER -c postgres -- psql -U invenio <DB name> -c "select uri from files_location"
```

Make sure #uri is changed to the destination bucket.

```
$ kubectl exec -n weko3pg $PG_MASTER -c postgres -- psql -U invenio <DB name> -c "select uri from files_files limit 1"
```

Make sure #uri is changed to the destination bucket.

Also, consider whether to change the mail sending setting, depending on the purpose of deployment.

If you do not need to send mails, you can set the mail server to localhost so that mails are not sent.

```
$ PG_MASTER=$(kubectl get po -n weko3pg -l spilo-role=master -o jsonpath="{.items[].metadata.name}")
$ kubectl exec -n weko3pg $PG_MASTER -c postgres -- psql -U invenio <DB name> -c "update mail_config set mail_server='localhost';"
```

The mail server configuration can be checked with the following command.

```
$ PG_MASTER=$(kubectl get po -n weko3pg -l spilo-role=master -o jsonpath="{.items[].metadata.name}")
$ kubectl exec -n weko3pg $PG_MASTER -c postgres -- psql -U postgres <DB name> -c 'select * from mail_config'
```

## Elasticsearch Backup and Restore


## Initialization process in WEB container

Depending on the version of the WEB container, the following commands need to be executed.

```
$ WEB_POD=<name of WEB POD of the institution to create schema definition>.
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio shell scripts/demo/register_oai_schema.py overwrite_all
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio shell tools/update/addjpcoar_v1_mapping.py
```
