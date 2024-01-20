# Building PostgreSQL environment

## Building Pgdump image

Execute folloing commands

```
$ cd <cloned directory>/weko-k8s/src/pgdump/
$ docker build -t pgdump .
$ docker tag pgdump:latest <repository path>/pgdump:<tag>
$ docker push <repository path>/pgdump:<tag>
```

## Building busybox-curl

Execute following commands

```
$ cd <cloned directory>/weko-k8s/src/busybox-curl/
$ docker build -t <repository path>/busybox-curl:<tag> . --no-cache
$ docker push <repository path>/busybox-curl:<tag>
```

## Deploying PostgreSQL

### Deploying PostgreSQL cluster

```
$ cd weko-k8s/deploy/postgresql/overlay/
```

```
$ XDG_CONFIG_HOME=../../../../kustomize-plugin SECRET_PATH=/usr/local/share/keys/secret.properties kustomize build --enable-alpha-plugins . | kubectl apply -f -
```

First time deploying, an error may occur when creating a custom resource. It is possible to deploy by executing the command again.

### Check cluster status

```
$ kubectl get pod -n weko3pg -o wide
NAME                                 READY   STATUS    RESTARTS      AGE   IP              NODE            NOMINATED NODE   READINESS GATES
postgres-operator-665bc4c8bb-mdw5v   1/1     Running   0             24m   10.64.121.57    10.65.208.216   <none>           <none>
weko-pgpool-bf75cb4fb-r57n4          2/2     Running   1 (21m ago)   24m   10.64.205.124   10.65.39.47     <none>           <none>
weko-pgpool-bf75cb4fb-v52sx          2/2     Running   0             24m   10.64.18.87     10.65.39.47     <none>           <none>
weko-postgresql-0                    2/2     Running   0             23m   10.64.223.207   10.65.107.69    <none>           <none>
weko-postgresql-1                    2/2     Running   0             23m   10.64.100.101   10.65.187.208   <none>           <none>
weko-postgresql-2                    2/2     Running   0             22m   10.64.216.145   10.65.220.40    <none>           <none>
```

Check the following items
- READY of each POD should be 1/1 or 2/2.
- STATUS of each POD should be Running.

```
$ kubectl get pods -l application=spilo -L spilo-role -n weko3pg #SPILO-ROLEにmaster,
```

Check that the replica is displayed.


```
NAME                READY   STATUS    RESTARTS   AGE   SPILO-ROLE
weko-postgresql-0   2/2     Running   0          25m   master
weko-postgresql-1   2/2     Running   0          24m   replica
weko-postgresql-2   2/2     Running   0          24m   replica
```

Check the following items
- READY of each POD should be 2/2.
- STATUS of each POD should be "Running".
- master" or "replica" is listed in the SPILO-ROLE column of each POD.

```
$ kubectl get svc -l application=spilo -L spilo-role -n weko3pg
NAME                     TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE   SPILO-ROLE
weko-postgresql          ClusterIP   10.67.55.182    <none>        5432/TCP   26m   master
weko-postgresql-config   ClusterIP   None            <none>        <none>     25m
weko-postgresql-repl     ClusterIP   10.67.141.133   <none>        5432/TCP   26m   replica
```

Check that master and replica appear in SPILO-ROLE.


```
$ kubectl logs -n weko3pg weko-pgpool-xxx 
```

Check that there are no error logs in each pgpool POD


```
$ kubectl logs -n weko3pg weko-postgresql-0 -c postgres 
```

Check that there are no error logs.

```
$ kubectl logs -n weko3pg weko-postgresql-1 -c postgres
```

Check that there are no error logs.

```
$ kubectl logs -n weko3pg weko-postgresql-2 -c postgres
```

Check that there are no error logs.

```
$ kubectl get postgresql -n weko3pg
NAME              TEAM   VERSION   PODS   VOLUME   CPU-REQUEST   MEMORY-REQUEST   AGE   STATUS
weko-postgresql   weko   12        3      100Gi    1000m         4Gi              40m   Running
```

Check that STATUS is Running.

```

$ kubectl exec -n weko3pg weko-pgpool-xxx -- psql -h localhost -U postgres -c "show pool_nodes;" 
Defaulted container "pgpool" out of: pgpool, pgpool-stats, wait-operator (init), wait-postgresql (init)
 node_id |           hostname           | port | status | lb_weight |  role   | select_cnt | load_balance_node | replication_delay | replication_state | replication_sync_state | last_status_change
---------+------------------------------+------+--------+-----------+---------+------------+-------------------+-------------------+-------------------+------------------------+---------------------
 0       | weko-postgresql.weko3pg      | 5432 | up     | 0.000000  | primary | 0          | false             | 0                 |                   |                        | 2022-09-14 01:51:47
 1       | weko-postgresql-repl.weko3pg | 5432 | up     | 1.000000  | standby | 90         | true              | 0                 |                   |                        | 2022-09-14 01:51:47
(2 rows)
```

Execute at each pgpool and confirm that status is up.

```
$ kubectl exec -n weko3pg weko-postgresql-0 -c postgres -- patronictl list 
Defaulted container "postgres" out of: postgres, exporter
+ Cluster: weko-postgresql (7143046989264236624) --+---------+----+-----------+
| Member            | Host          | Role         | State   | TL | Lag in MB |
+-------------------+---------------+--------------+---------+----+-----------+
| weko-postgresql-0 | 10.64.223.207 | Leader       | running |  1 |           |
| weko-postgresql-1 | 10.64.100.101 | Sync Standby | running |  1 |         0 |
| weko-postgresql-2 | 10.64.216.145 | Replica      | running |  1 |         0 |
+-------------------+---------------+--------------+---------+----+-----------+
```

Execute on the master and confirm that the State is running.

```
$ kubectl exec -n weko3pg weko-postgresql-0 -c postgres -- psql -U postgres -c "select * from pg_stat_replication;"　

Defaulted container "postgres" out of: postgres, exporter
 pid | usesysid |  usename   | application_name  |  client_addr  | client_hostname | client_port |         backend_start         | backend_xmin |   state   | sent_lsn  | write_lsn | flush_lsn | replay_lsn | write_lag | flush_lag | replay_lag | sync_priority | sync_state |          reply_time
-----+----------+------------+-------------------+---------------+-----------------+-------------+-------------------------------+--------------+-----------+-----------+-----------+-----------+------------+-----------+-----------+------------+---------------+------------+-------------------------------
 227 |    16638 | invenio_cl | weko-postgresql-1 | 10.64.100.101 |                 |       50888 | 2022-09-14 01:51:10.660722+00 |              | streaming | 0/8000000 | 0/8000000 | 0/8000000 | 0/8000000  |           |           |            |             1 | sync       | 2022-09-14 02:31:12.993479+00
 330 |    16638 | invenio_cl | weko-postgresql-2 | 10.64.216.145 |                 |       41910 | 2022-09-14 01:51:42.958308+00 |              | streaming | 0/8000000 | 0/8000000 | 0/8000000 | 0/8000000  |           |           |            |             0 | async      | 2022-09-14 02:31:13.164685+00
(2 rows)
```

Execute at the master and check the following items.
- write_lag, flush_lag, and replay_lag are blank.


### Check the results of the backup job execution

```
$ kubectl get pod -n weko3pg 
NAME                                 READY   STATUS      RESTARTS     AGE
postgres-operator-665bc4c8bb-mdw5v   1/1     Running     0            7d
weko-pgdump-job1-27725340-rkppt      0/1     Completed   0            2d9h
weko-pgdump-job1-27726780-xpnhq      0/1     Completed   0            33h
weko-pgdump-job1-27728220-x2wbv      0/1     Completed   0            9h
weko-pgdump-job2-27725345-f4lkn      0/1     Completed   0            2d9h
weko-pgdump-job2-27726785-trrfg      0/1     Completed   0            33h
weko-pgdump-job2-27728225-sqn4m      0/1     Completed   0            9h
weko-pgdump-job3-27725345-z7ppg      0/1     Completed   0            2d9h
weko-pgdump-job3-27726785-wxmp6      0/1     Completed   0            33h
weko-pgdump-job3-27728225-7qtw8      0/1     Completed   0            9h
weko-pgdump-job4-27725345-j649j      0/1     Completed   0            2d9h
weko-pgdump-job4-27726785-q8lxt      0/1     Completed   0            33h
weko-pgdump-job4-27728225-9pnzf      0/1     Completed   0            9h
weko-pgpool-bf75cb4fb-r57n4          2/2     Running     1 (7d ago)   7d
weko-pgpool-bf75cb4fb-v52sx          2/2     Running     0            7d
weko-postgresql-0                    2/2     Running     0            7d
weko-postgresql-1                    2/2     Running     0            7d
weko-postgresql-2                    2/2     Running     0            7d
```

Check that the STATUS of each job is set to Completed.


## Environment Reconstruction Procedure


Describe the procedure for rebuilding the environment if an error occurs during construction for any reason.

### Delete existing resources


Stop the WEB POD before working on it.

```
$ cd <Manifest file of institutions>/manifests/
$ kubectl delete -f deploy-web.yaml
```


Delete the namespace "weko3pg".


```
$ kubectl delete namespace weko3pg
```

### Building a PostgreSQL Environment


Follow the above steps to build a PostgreSQL environment.

### Redeployment of WEB POD


Deploy WEB POD and create DB.

```
$ cd <Manifest file of institutions>/manifests/
$ kubectl apply -f deploy-web.yaml
$ kubectl exec -n weko3 <WEB POD> -c web -it -- bash
invenio@test1-repo-nii-ac-jp-web-d559db756-gjpc4:/code$ invenio db init
Creating database postgresql+psycopg2://invenio:<pass>@pgpool.weko3pg:5432/test1_repo_nii_ac_jp
invenio@test1-repo-nii-ac-jp-web-d559db756-gjpc4:/code$ invenio db create
```

Check that it terminates without error.

### Restore DB

Put the backup file in a location accessible from the PostgreSQL master pod.

```
$ kubectl exec -n weko3pg <POD name of PostgreSQL master> -c postgres -it -- bash
root@weko3pg-cluster-0:/home/postgres# zcat /var/lib/postgresql/backup/test1.sql.gz | psql -U postgres <db-name>
```


## Debugging PostgreSQL

Enabling the replica query log
This is used when you want to check what kind of SELECT statement was executed on a replica.

Enabling the query log will worsen performance, so disable it after confirmation.

Execute the following command.

```
$ REPLICA_POD=<POD Name of PostgreSQL replica>
$ kubectl exec -n weko3pg $REPLICA_POD -c postgres -- psql -U postgres -c "ALTER SYSTEM SET log_statement = 'all'"
$ kubectl exec -n weko3pg $REPLICA_POD -- apt-get update
$ kubectl exec -n weko3pg $REPLICA_POD -- apt-get install gosu -y
$ kubectl exec -n weko3pg $REPLICA_POD -- gosu postgres pg_ctl reload
```

To disable the query log, execute the following command

```
$ kubectl exec -n weko3pg $REPLICA_POD -c postgres -- psql -U postgres -c "ALTER SYSTEM SET log_statement = 'none'"
$ kubectl exec -n weko3pg $REPLICA_POD -c postgres -- gosu postgres pg_ctl reload
```
