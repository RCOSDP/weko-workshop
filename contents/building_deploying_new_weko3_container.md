# Building/Deoloying new WEKO3 container

## Building init container image

Execute the following commands.

```
$ cd <cloned directory>/weko-k8s/src/init-container/
$ docker build -t <repository path>/init:<tag> .
$ docker push <repository path>/init:<tag>
```

## Building web and nginx container images

Execute the following commands.

```
$ cd <cloned directory>/weko3
$ docker-compose build web
$ docker tag weko3_web:latest <registry path>/weko3_web:<tag>
$ docker push <registry path>/weko3_web:<tag>
$ docker-compose build nginx
$ docker tag weko3_nginx:latest <registry path>/weko3_nginx:<tag>
$ docker push <registry path>/weko3_nginx:<tag>
```

## Deploying WEKO3

### Edit parameters per environment

Change the following items as necessary

- IP address of the NFS server

```
$ cd <clone directory>/weko-k8s/deploy/weko/manifest_template
$ vi volume-pv.yaml
#Change the values of the following fields
(name: __DOMAIN_NAME__-nginx-pv)/spec/nfs/server/
(name: __DOMAIN_NAME__-shib-pv)/spec/nfs/server/
(name: __DOMAIN_NAME__-static-pv)/spec/nfs/server/
(name: __DOMAIN_NAME__-config-pv)/spec/nfs/server/
(name: __DOMAIN_NAME__-data-pv)/spec/nfs/server/
```

- Information to access middleware

```
$ cd <clone directory>/weko-k8s/deploy/weko/manifest_template
$ vi configmap.yaml
#Change the values of the following fields
/data/INVENIO_POSTGRESQL_DBUSER -> specify PostgreSQL user name
/data/INVENIO_POSTGRESQL_DBPASS -> specify PostgreSQL password
$ vi secret.yaml
#Modify the values of the following fields. (It is not necessary to encode in base64.) $ vi secret.yaml
/stringData/INVENIO_RABBITMQ_USER -> specify RabbitMQ user name
/stringData/INVENIO_RABBITMQ_PASS -> specify password for RabbitMQ
/stringData/INVENIO_POSTGRESQL_DBUSER -> Specify PostgreSQL user name
/stringData/INVENIO_POSTGRESQL_DBPASS -> specify PostgreSQL password
/stringData/INVENIO_USER_EMAIL -> specify WEKO3 user name
/stringData/INVENIO_USER_PASS -> specify WEKO3 password
```

- Information for accessing S3

```
$ vi secret.yaml
#Fix the following items. (It is not necessary to encode in base64)
/stringData/S3_ACCESS_KEY_ID -> specify S3 access key
/stringData/S3_SECRECT_ACCESS_KEY -> specify S3 secret key
/stringData/S3_ENDPOINT_URL -> specify endpoint URL of S3
```

### Deployment of various resources

Execute the following commands.

```
$ cat /usr/local/share/keys/oci-container-registry.account
user : <username>
token : <token>
$ kubectl create secret docker-registry ocir-secret -n weko3 \

--docker-username='<tenancy-namespace>/<username>' \
--docker-password='<token>' \
--docker-email='example@example.com'
$ cd <clone directory>/weko-k8s/scripts/
$ sudo . /make_volumes.sh <directory of repositories.txt>/repositories.txt
#Note that the configuration file in file storage will be overwritten by the template file.
$ . /make_rabbitmq_vhost.sh <directory of repositories.txt>/repositories.txt
$ mkdir <directory for manifest file output>.
$ . /make_weko_manifests.sh <directory of repositories.txt>/repositories.txt \
> nrt.ocir.io/<tenancy-namespace>/<dir>/init:<tag> \
> nrt.ocir.io/<tenancy-namespace>/<dir>/weko3_nginx:<tag> \
> nrt.ocir.io/<tenancy-namespace>/<dir>/weko3_web:<tag> \
> <manifest file output destination>.
$ . /deploy_weko.sh <directory of repositories.txt>/repositories.txt \
> <manifest file output destination> $ .
$ kubectl get pod -n weko3 -o wide
NAME READY STATUS RESTARTS AGE IP NODE NOMINATED NODE READINESS GATES
test-af1-repo-nii-ac-jp-web-6976698fb5-69v85 2/3 Running 0 118s 10.244.1.10 10.0.10.112 <none> <none>
#Check the following items.
　READY of POD is 2/3 (because initial DB registration of PostgreSQL is not done)
　POD's STATUS should be Running.
```

### Initial DB registration process

```
$ PSQL_MASTER=$(kubectl get po -n weko3pg -l spilo-role=master -o jsonpath="{.items[].metadata.name}")
$ echo $PSQL_MASTER
$ DB=<DB name of the deployed institution>.
#DB: Hyphen (-) and dot (.) in FQDN to underscore (_) (e.g. if FQDN is kitami-it.repo.nii.ac.jp, DB name is kitami_it_repo_nii_ac_jp)
$ echo $DB
$ WEB_POD=<deployed WEB POD name> $ echo $DB
$ echo $WEB_POD
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio postgres -c "create database $DB"
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio postgres -c "SELECT datname FROM pg_database WHERE datname='$DB';"
         datname
-------------------------
 <db-name>
(1 row)
Confirm that #DB has been created.
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio db init
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio db create
$ date; kubectl exec -n weko3 $WEB_POD -c web -- bash -x . /scripts/populate-instance.sh; date
# Make sure it runs to the end.
$ kubectl cp -n weko3 -c web $WEB_POD:scripts/demo/item_type3.sql /tmp/item_type3.sql
$ kubectl cp -n weko3 -c web $WEB_POD:scripts/demo/indextree.sql /tmp/indextree.sql
$ kubectl cp -n weko3 -c web $WEB_POD:scripts/demo/resticted_access.sql /tmp/resticted_access.sql
 
$ kubectl cp -n weko3pg /tmp/item_type3.sql $PSQL_MASTER:/tmp/ -c postgres
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio $DB -f /tmp/item_type3.sql
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- rm /tmp/item_type3.sql
 
$ kubectl cp -n weko3pg /tmp/indextree.sql $PSQL_MASTER:/tmp/ -c postgres
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio $DB -f /tmp/indextree.sql
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- rm /tmp/indextree.sql
   
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio workflow init action_status,Action,Flow
   
$ kubectl cp -n weko3pg /tmp/resticted_access.sql $PSQL_MASTER:/tmp/ -c postgres
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio $DB -f /tmp/resticted_access.sql
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- rm /tmp/resticted_access.sql
   
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio workflow init gakuninrdm_data
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio shell scripts/demo/register_oai_schema.py overwrite_all
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio shell tools/update/addjpcoar_v1_mapping.py
 
$ rm -v /tmp/item_type3.sql /tmp/indextree.sql /tmp/resticted_access.sql
 
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio $DB -c "select setval('pidstore_recid_recid_seq', 2000000);"
 
$ kubectl get pod -n weko3 -o wide
NAME READY STATUS RESTARTS AGE IP NODE NOMINATED NODE READINESS GATES
test1-repo-nii-ac-jp-web-d559db756-zks7z 3/3 Running 2 (26h ago) 29h 10.244.10.150 10.0.10.172 <none> <none>
#Check the following items.
　POD's READY should be 3/3
　POD's STATUS should be Running
$ kubectl logs -n weko3 $WEB_POD -c <container>
#container: Specify one of init, web, or nginx.
Confirm that there is no error in #logs.
```

### Checking Access from a Browser

Checking that access is possible from a browser.

If you want to confirm access before deploying Ingress, you can access by port forwarding from kubectl command.

```
$ kubectl port-forward -n weko3 <WEB POD name> 8080:443 &
```

# References

- orginal text. https://meatwiki.nii.ac.jp/confluence/pages/viewpage.action?pageId=91390025