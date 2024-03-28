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

### Edit enviromental parameters

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

```
yq '.spec.nfs.server' deploy/weko/manifest_template/volume-pv.yaml
```



- Information to access middleware

```
$ cd <clone directory>/weko-k8s/deploy/weko/manifest_template
$ vi configmap.yaml
#Change the values of the following fields
/data/INVENIO_POSTGRESQL_DBUSER -> specify PostgreSQL user name
```

```
yq '.data.INVENIO_POSTGRESQL_DBUSER' deploy/weko/manifest_template/configmap.yaml
```

```
/data/INVENIO_POSTGRESQL_DBPASS -> specify PostgreSQL password
```

```
yq '.data.INVENIO_POSTGRESQL_DBPASS' deploy/weko/manifest_template/configmap.yaml
```

```
$ vi secret.yaml
#Modify the values of the following fields. (It is not necessary to encode in base64.) $ vi secret.yaml
/stringData/INVENIO_RABBITMQ_USER -> specify RabbitMQ user name
```

```
yq '.stringData.INVENIO_RABBITMQ_USER' deploy/weko/manifest_template/secret.yaml
```

```
/stringData/INVENIO_RABBITMQ_PASS -> specify password for RabbitMQ
```

```
yq '.stringData.INVENIO_RABBITMQ_PASS' deploy/weko/manifest_template/secret.yaml
```

```
/stringData/INVENIO_POSTGRESQL_DBUSER -> Specify PostgreSQL user name
/stringData/INVENIO_POSTGRESQL_DBPASS -> specify PostgreSQL password
```

```
yq '.stringData.INVENIO_POSTGRESQL_DBUSER' deploy/weko/manifest_template/secret.yaml
yq '.stringData.INVENIO_POSTGRESQL_DBPASS' deploy/weko/manifest_template/secret.yaml
```

```
/stringData/INVENIO_USER_EMAIL -> specify WEKO3 user name
/stringData/INVENIO_USER_PASS -> specify WEKO3 password
```

```
yq '.stringData.INVENIO_USER_EMAIL' deploy/weko/manifest_template/secret.yaml
yq '.stringData.INVENIO_USER_PASS' deploy/weko/manifest_template/secret.yaml
```

- Information for accessing S3

```
$ vi secret.yaml
#Fix the following items. (It is not necessary to encode in base64)
/stringData/S3_ACCESS_KEY_ID -> specify S3 access key
/stringData/S3_SECRECT_ACCESS_KEY -> specify S3 secret key
/stringData/S3_ENDPOINT_URL -> specify endpoint URL of S3
```

```
yq '.stringData.S3_ACCESS_KEY_ID' deploy/weko/manifest_template/secret.yaml
yq '.stringData.S3_SECRECT_ACCESS_KEY' deploy/weko/manifest_template/secret.yaml
yq '.stringData.S3_ENDPOINT_URL' deploy/weko/manifest_template/secret.yaml
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
```

```
$ sudo ./make_volumes.sh /usr/local/share/deploy_logs/repositories-#41512.txt
```

```
$ ./make_rabbitmq_vhost.sh <directory of repositories.txt>/repositories.txt
```

```
$ ./make_rabbitmq_vhost.sh /usr/local/share/deploy_logs/repositories-#41512.txt
Defaulted container "rabbitmq" out of: rabbitmq, setup-container (init)
Adding vhost "repository-a-example-org/" ...
Defaulted container "rabbitmq" out of: rabbitmq, setup-container (init)
Setting permissions for user "invenio" in vhost "repository-a-example-org/" ...
Defaulted container "rabbitmq" out of: rabbitmq, setup-container (init)
Adding vhost "repository-b-example-org/" ...
Defaulted container "rabbitmq" out of: rabbitmq, setup-container (init)
Setting permissions for user "invenio" in vhost "repository-b-example-org/" ...
```

```
$ mkdir <directory for manifest file output>.
$ . /make_weko_manifests.sh <directory of repositories.txt>/repositories.txt \
> <docker image repository>/<tenancy-namespace>/<dir>/init:<tag> \
> <docker image repository>/<tenancy-namespace>/<dir>/weko3_nginx:<tag> \
> <docker image repository>/<tenancy-namespace>/<dir>/weko3_web:<tag> \
> <manifest file output destination>.
```

```
$ ./make_weko_manifests.sh /usr/local/share/deploy_logs/repositories-#41512.txt <docker image repository>/nrbslpthdcco/af/init:v0.9.23a-5ef5a1a <docker image repository>/nrbslpthdcco/af/weko3_nginx:v0.9.27 <docker image repository>/nrbslpthdcco/af/weko3_web:v0.9.27 /usr/local/share/deploy_logs/.
create  repository-b.example.org
create  repository-a.example.org
```

```
$ ./deploy_weko.sh <directory of repositories.txt>/repositories.txt \
> <manifest file output destination> $ .
```

```
$ ./deploy_weko.sh /usr/local/share/deploy_logs/repositories-#41512.txt /usr/local/share/deploy_logs/
Error from server (AlreadyExists): namespaces "weko3" already exists
Sat Feb 10 15:53:43 GMT 2024
deploy ( 1 / 2 ) : repository-b.example.org
configmap/repository-a-example-org-configmap created
deployment.apps/repository-a-example-org-web created
ingress.networking.k8s.io/repository-a-example-org-ingress created
secret/repository-a-example-org-secret created
service/repository-a-example-org-nginx created
persistentvolume/repository-a-example-org-nginx-pv created
persistentvolume/repository-a-example-org-shib-pv created
persistentvolume/repository-a-example-org-config-pv created
persistentvolume/repository-a-example-org-data-pv created
persistentvolumeclaim/repository-a-example-org-nginx-pvc created
persistentvolumeclaim/repository-a-example-org-shib-pvc created
persistentvolumeclaim/repository-a-example-org-config-pvc created
persistentvolumeclaim/repository-a-example-org-data-pvc created
secret/repository-a-example-org-cert created
Sat Feb 10 15:54:04 GMT 2024
deploy ( 2 / 2 ) : repository-a.example.org
configmap/repository-b-example-org-configmap created
deployment.apps/repository-b-example-org-web created
ingress.networking.k8s.io/repository-b-example-org-ingress created
secret/repository-b-example-org-secret created
service/repository-b-example-org-nginx created
persistentvolume/repository-b-example-org-nginx-pv created
persistentvolume/repository-b-example-org-shib-pv created
persistentvolume/repository-b-example-org-config-pv created
persistentvolume/repository-b-example-org-data-pv created
persistentvolumeclaim/repository-b-example-org-nginx-pvc created
persistentvolumeclaim/repository-b-example-org-shib-pvc created
persistentvolumeclaim/repository-b-example-org-config-pvc created
persistentvolumeclaim/repository-b-example-org-data-pvc created
secret/repository-b-example-org-cert created
sleep 60
```

```
$ kubectl get pod -n weko3 -o wide
NAME READY STATUS RESTARTS AGE IP NODE NOMINATED NODE READINESS GATES
test-af1-repo-nii-ac-jp-web-6976698fb5-69v85 2/3 Running 0 118s 10.244.1.10 10.0.10.112 <none> <none>
#Check the following items.
　READY of POD is 2/3 (because initial DB registration of PostgreSQL is not done)
　POD's STATUS should be Running.
```


```
$ kubectl describe pods -n weko3 repository-b-example-org-web-58d4fb64fc-m72rc
Name:             repository-b-example-org-web-58d4fb64fc-m72rc
Namespace:        weko3
Priority:         0
Service Account:  default
Node:             10.85.130.241/10.85.130.241
Start Time:       Sat, 10 Feb 2024 15:54:08 +0000
Labels:           app=repository-b-example-org-nginx
                  pod-template-hash=58d4fb64fc
Annotations:      <none>
Status:           Running
IP:               10.84.122.177
IPs:
  IP:           10.84.122.177
Controlled By:  ReplicaSet/repository-b-example-org-web-58d4fb64fc
Init Containers:
  init:
    Container ID:  cri-o://70213bb27264e79e1b27f59308d76c22136c8c4922e9882780ed2801f827f4a6
    Image:         <docker image repository>/nrbslpthdcco/af/init:v0.9.23a-5ef5a1a
    Image ID:      633f81a0302c4c8a8a7c3fd198246c3db8edd75d5a84b4e85cd71ce194b27a0b
    Port:          <none>
    Host Port:     <none>
    Command:
      /bin/bash
    Args:
      -c
      jinja2 /conf/instance.cfg > /conf/invenio.cfg
    State:          Terminated
      Reason:       Completed
      Exit Code:    0
      Started:      Sat, 10 Feb 2024 15:54:16 +0000
      Finished:     Sat, 10 Feb 2024 15:54:17 +0000
    Ready:          True
    Restart Count:  0
    Environment Variables from:
      repository-b-example-org-configmap  ConfigMap  Optional: false
      repository-b-example-org-secret     Secret     Optional: false
    Environment:                                <none>
    Mounts:
      /conf from repository-b-example-org-config-volume (rw)
      /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-42ggj (ro)
Containers:
  nginx:
    Container ID:   cri-o://9950062dd1751739235d59f9aa8be831184b3f630132f662216102ac14912068
    Image:          <docker image repository>/nrbslpthdcco/af/weko3_nginx:v0.9.27
    Image ID:       3721abd052c21f4fe22cdb436bf1ce64d5496626f684b12aa8bf4c172486f393
    Ports:          80/TCP, 443/TCP
    Host Ports:     0/TCP, 0/TCP
    State:          Running
      Started:      Sat, 10 Feb 2024 15:54:18 +0000
    Ready:          False
    Restart Count:  0
    Limits:
      memory:  300Mi
    Requests:
      memory:     250Mi
    Readiness:    http-get https://:443/ping delay=0s timeout=3s period=10s #success=1 #failure=3
    Environment:  <none>
    Mounts:
      /etc/nginx from repository-b-example-org-nginx-volume (rw)
      /etc/shibboleth from repository-b-example-org-shib-volume (rw)
      /home/invenio/.virtualenvs/invenio/var/instance/data from repository-b-example-org-data-volume (rw)
      /home/invenio/.virtualenvs/invenio/var/instance/static from repository-b-example-org-static-volume (rw)
      /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-42ggj (ro)
  web:
    Container ID:  cri-o://213987b0edec287d6c0861ab7baba1658fa4037e464bf5888029f0f7f7380796
    Image:         <docker image repository>/nrbslpthdcco/af/weko3_web:v0.9.27
    Image ID:      195d1bbfba3ab4fe8848cf559f7134261fef2d44091b66d3f30a5eedcd272cb1
    Port:          5000/TCP
    Host Port:     0/TCP
    Command:
      /bin/bash
    Args:
      -c
      mv /home/invenio/.virtualenvs/invenio/var/instance/static.org/* /home/invenio/.virtualenvs/invenio/var/instance/static/. && uwsgi --ini /home/invenio/.virtualenvs/invenio/var/instance/conf/uwsgi.ini
    State:          Running
      Started:      Sat, 10 Feb 2024 15:54:19 +0000
    Ready:          True
    Restart Count:  0
    Limits:
      memory:  2000Mi
    Requests:
      memory:  700Mi
    Environment Variables from:
      repository-b-example-org-configmap  ConfigMap  Optional: false
      repository-b-example-org-secret     Secret     Optional: false
    Environment:                                <none>
    Mounts:
      /home/invenio/.virtualenvs/invenio/var/instance/conf from repository-b-example-org-config-volume (rw)
      /home/invenio/.virtualenvs/invenio/var/instance/data from repository-b-example-org-data-volume (rw)
      /home/invenio/.virtualenvs/invenio/var/instance/static from repository-b-example-org-static-volume (rw)
      /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-42ggj (ro)
  worker:
    Container ID:  cri-o://503284a5f48b30de6e18ce1e9b2b3839a30e06e042bfc684c2e7d8388420de72
    Image:         <docker image repository>/nrbslpthdcco/af/weko3_web:v0.9.27
    Image ID:      195d1bbfba3ab4fe8848cf559f7134261fef2d44091b66d3f30a5eedcd272cb1
    Port:          5000/TCP
    Host Port:     0/TCP
    Command:
      /bin/bash
    Args:
      -c
      rm -f /home/invenio/celeryd.pid && celery worker --pidfile /home/invenio/celeryd.pid --schedule=/home/invenio/celerybeat-schedule -c 2 -A invenio_app.celery --loglevel=INFO -B
    State:          Running
      Started:      Sat, 10 Feb 2024 15:54:21 +0000
    Ready:          True
    Restart Count:  0
    Limits:
      memory:  2000Mi
    Requests:
      memory:  400Mi
    Environment Variables from:
      repository-b-example-org-configmap  ConfigMap  Optional: false
      repository-b-example-org-secret     Secret     Optional: false
    Environment:                                <none>
    Mounts:
      /home/invenio/.virtualenvs/invenio/var/instance/conf from repository-b-example-org-config-volume (rw)
      /home/invenio/.virtualenvs/invenio/var/instance/data from repository-b-example-org-data-volume (rw)
      /home/invenio/.virtualenvs/invenio/var/instance/static from repository-b-example-org-static-volume (rw)
      /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-42ggj (ro)
Conditions:
  Type              Status
  Initialized       True
  Ready             False
  ContainersReady   False
  PodScheduled      True
Volumes:
  repository-b-example-org-nginx-volume:
    Type:       PersistentVolumeClaim (a reference to a PersistentVolumeClaim in the same namespace)
    ClaimName:  repository-b-example-org-nginx-pvc
    ReadOnly:   false
  repository-b-example-org-shib-volume:
    Type:       PersistentVolumeClaim (a reference to a PersistentVolumeClaim in the same namespace)
    ClaimName:  repository-b-example-org-shib-pvc
    ReadOnly:   false
  repository-b-example-org-static-volume:
    Type:       EmptyDir (a temporary directory that shares a pod's lifetime)
    Medium:
    SizeLimit:  <unset>
  repository-b-example-org-data-volume:
    Type:       PersistentVolumeClaim (a reference to a PersistentVolumeClaim in the same namespace)
    ClaimName:  repository-b-example-org-data-pvc
    ReadOnly:   false
  repository-b-example-org-config-volume:
    Type:       PersistentVolumeClaim (a reference to a PersistentVolumeClaim in the same namespace)
    ClaimName:  repository-b-example-org-config-pvc
    ReadOnly:   false
  kube-api-access-42ggj:
    Type:                    Projected (a volume that contains injected data from multiple sources)
    TokenExpirationSeconds:  3607
    ConfigMapName:           kube-root-ca.crt
    ConfigMapOptional:       <nil>
    DownwardAPI:             true
QoS Class:                   Burstable
Node-Selectors:              nodeType=WEKO
Tolerations:                 node.kubernetes.io/not-ready:NoExecute op=Exists for 300s
                             node.kubernetes.io/unreachable:NoExecute op=Exists for 300s
Events:
  Type     Reason            Age                    From               Message
  ----     ------            ----                   ----               -------
  Warning  FailedScheduling  31m                    default-scheduler  0/18 nodes are available: persistentvolumeclaim "repository-b-example-org-nginx-pvc" not found. preemption: 0/18 nodes are available: 18 No preemption victims found for incoming pod..
  Normal   Scheduled         31m                    default-scheduler  Successfully assigned weko3/repository-b-example-org-web-58d4fb64fc-m72rc to 10.85.130.241
  Normal   Pulled            31m                    kubelet            Container image "<docker image repository>/nrbslpthdcco/af/init:v0.9.23a-5ef5a1a" already present on machine
  Normal   Created           31m                    kubelet            Created container init
  Normal   Started           31m                    kubelet            Started container init
  Normal   Pulling           31m                    kubelet            Pulling image "<docker image repository>/nrbslpthdcco/af/weko3_nginx:v0.9.27"
  Normal   Pulled            31m                    kubelet            Successfully pulled image "<docker image repository>/nrbslpthdcco/af/weko3_nginx:v0.9.27" in 230.665851ms (230.673866ms including waiting)
  Normal   Created           31m                    kubelet            Created container nginx
  Normal   Started           31m                    kubelet            Started container nginx
  Normal   Pulling           31m                    kubelet            Pulling image "<docker image repository>/nrbslpthdcco/af/weko3_web:v0.9.27"
  Normal   Pulled            31m                    kubelet            Successfully pulled image "<docker image repository>/nrbslpthdcco/af/weko3_web:v0.9.27" in 159.896971ms (159.903915ms including waiting)
  Normal   Created           31m                    kubelet            Created container web
  Normal   Started           31m                    kubelet            Started container web
  Normal   Pulling           31m                    kubelet            Pulling image "<docker image repository>/nrbslpthdcco/af/weko3_web:v0.9.27"
  Normal   Pulled            31m                    kubelet            Successfully pulled image "<docker image repository>/nrbslpthdcco/af/weko3_web:v0.9.27" in 178.992938ms (178.99958ms including waiting)
  Normal   Created           31m                    kubelet            Created container worker
  Normal   Started           31m                    kubelet            Started container worker
  Warning  Unhealthy         31m (x5 over 31m)      kubelet            Readiness probe failed: HTTP probe failed with statuscode: 502
  Warning  Unhealthy         30m (x4 over 31m)      kubelet            Readiness probe failed: Get "https://10.84.122.177:443/ping": net/http: request canceled (Client.Timeout exceeded while awaiting headers)
  Warning  NodeNotReady      29m                    node-controller    Node is not ready
  Warning  FailedMount       26m                    kubelet            Unable to attach or mount volumes: unmounted volumes=[repository-b-example-org-config-volume], unattached volumes=[kube-api-access-42ggj repository-b-example-org-nginx-volume repository-b-example-org-shib-volume repository-b-example-org-static-volume repository-b-example-org-data-volume repository-b-example-org-config-volume]: timed out waiting for the condition
  Warning  Unhealthy         6m14s (x138 over 26m)  kubelet            Readiness probe failed: HTTP probe failed with statuscode: 500
  Warning  FailedMount       38s                    kubelet            Unable to attach or mount volumes: unmounted volumes=[repository-b-example-org-data-volume repository-b-example-org-config-volume], unattached volumes=[kube-api-access-42ggj repository-b-example-org-nginx-volume repository-b-example-org-shib-volume repository-b-example-org-static-volume repository-b-example-org-data-volume repository-b-example-org-config-volume]: timed out waiting for the condition
  Warning  Unhealthy         7s (x5 over 37s)       kubelet            Readiness probe failed: HTTP probe failed with statuscode: 500
````



### Initialize Database



```
$ PSQL_MASTER=$(kubectl get po -n weko3pg -l spilo-role=master -o jsonpath="{.items[].metadata.name}")
$ echo $PSQL_MASTER
$ DB=<DB name of the deployed institution>.
#DB: Hyphen (-) and dot (.) in FQDN to underscore (_) (e.g. if FQDN is kitami-it.repo.nii.ac.jp, DB name is kitami_it_repo_nii_ac_jp)
$ echo $DB
```

```
$ DB=research_wacren_net
$ echo $DB
research_wacren_net
```

```
$ WEB_POD=<deployed WEB POD name> 
$ echo $WEB_POD
```

```
WEB_POD=repository-a-example-org-web-8c45847bc-q98md
$ echo $WEB_POD
repository-a-example-org-web-8c45847bc-q98md
```

```
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio postgres -c "create database $DB"
```

```
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio postgres -c "create database $DB"
CREATE DATABASE
```

```
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio postgres -c "SELECT datname FROM pg_database WHERE datname='$DB';"
         datname
-------------------------
 <db-name>
(1 row)
```

Confirm that #DB has been created.

```
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio postgres -c "SELECT datname FROM pg_database WHERE datname='$DB';"
       datname
---------------------
 research_wacren_net
(1 row)
```

Initialize Database

```
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio db init
```

```
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio db init
Creating database postgresql+psycopg2://invenio:dbpass123@pgpool.weko3pg:5432/research_wacren_net
```

Run the following commands for creating tables.

```
kubectl exec -n weko3 $WEB_POD -c web -- invenio db create
```

```
$ kubectl exec -n weko3 $WEB_POD -c web -- invenio db create
Creating all tables!

INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
Created all tables!
```

### Initialize application

```
date; kubectl exec -n weko3 $WEB_POD -c web -- bash -x ./scripts/populate-instance.sh; date
```

#### Item type

Copy sql files from web container to local.

```
kubectl cp -n weko3 -c web $WEB_POD:scripts/demo/item_type3.sql /tmp/item_type3.sql
```

```
kubectl cp -n weko3pg /tmp/item_type3.sql $PSQL_MASTER:/tmp/ -c postgres
```

```
kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio $DB -f /tmp/item_type3.sql
```

```
kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- rm /tmp/item_type3.sql
```


```
kubectl cp -n weko3 -c web $WEB_POD:scripts/demo/indextree.sql /tmp/indextree.sql
kubectl cp -n weko3pg /tmp/indextree.sql $PSQL_MASTER:/tmp/ -c postgres
kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio $DB -f /tmp/indextree.sql
kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- rm /tmp/indextree.sql
```





```
kubectl exec -n weko3 $WEB_POD -c web -- invenio workflow init action_status,Action,Flow
```

```
kubectl cp -n weko3 -c web $WEB_POD:scripts/demo/resticted_access.sql /tmp/resticted_access.sql
kubectl cp -n weko3pg /tmp/resticted_access.sql $PSQL_MASTER:/tmp/ -c postgres
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio $DB -f /tmp/resticted_access.sql
$ kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- rm /tmp/resticted_access.sql
```


```
kubectl exec -n weko3 $WEB_POD -c web -- invenio workflow init gakuninrdm_data
kubectl exec -n weko3 $WEB_POD -c web -- invenio shell scripts/demo/register_oai_schema.py overwrite_all
kubectl exec -n weko3 $WEB_POD -c web -- invenio shell tools/update/addjpcoar_v1_mapping.py
```

```
rm -v /tmp/item_type3.sql /tmp/indextree.sql /tmp/resticted_access.sql
```

```
kubectl exec -n weko3pg $PSQL_MASTER -c postgres -- psql -U invenio $DB -c "select setval('pidstore_recid_recid_seq', 2000000);"
```

```
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

## Certbot

```
$ kubectl delete -f /usr/local/share/deploy_logs/repository-b.example.org/manifests/deploy-web.yaml
deployment.apps "repository-a-example-org-web" deleted
```

```
$ kubectl delete -f /usr/local/share/deploy_logs/repository-b.example.org/manifests/ingress.yaml
ingress.networking.k8s.io "repository-a-example-org-ingress" deleted
```

```
apiVersion: v1
kind: Service
metadata:
  creationTimestamp: null
  name: certbot
  namespace: weko3
spec:
  ports:
  - name: http
    port: 80
    protocol: TCP
    targetPort: 80
  - name: https
    port: 443
    protocol: TCP
    targetPort: 443
  selector:
    run: certbot
status:
  loadBalancer: {}
---
kind: ConfigMap
metadata:
  name: certbot
  namespace: weko3
apiVersion: v1
data:
  default.conf: |
    server{
      listen 443 ssl;
      ssl_certificate /etc/nginx/certs/tls.crt;
      ssl_certificate_key /etc/nginx/certs/tls.key;
      server_name repository-b.example.org;
      location /.well-known/acme-challenge/ {
        alias /tmp/.well-known/;
      }
    }
---
apiVersion: v1
kind: Pod
metadata:
  creationTimestamp: null
  labels:
    run: certbot
  name: certbot
  namespace: weko3
spec:
  containers:
  - image: nginx
    name: nginx
    ports:
    - name: http
      containerPort: 80
    - name: https
      containerPort: 443
    resources: {}
    volumeMounts:
    - name: certbot
      mountPath: /etc/nginx/conf.d
    - name: cert
      mountPath: /etc/nginx/certs
  - image: certbot/certbot:latest
    name: certbot
    tty: true
    command: ["/bin/sh"]
  dnsPolicy: ClusterFirst
  restartPolicy: Always
  volumes:
  - name: certbot
    configMap:
      name: certbot
  - name: cert
    secret:
      secretName: repository-a-example-org-cert
status: {}
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  namespace: weko3
  name: certbot-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
    nginx.org/ssl-services: "certbot"
    appprotect.f5.com/app-protect-enable: "True"
    appprotect.f5.com/app-protect-policy: "weko3/weko3-policy"
    appprotect.f5.com/app-protect-security-log: "logconf"
    appprotect.f5.com/app-protect-security-log-enable: "True"
    appprotect.f5.com/app-protect-security-log-destination: "stderr"
    nginx.org/server-tokens: "off"
    nginx.org/server-snippets: |
      if ($http_user_agent ~* AdsBot-Google|SemrushBot|AhrefsBot) {
        return 403;
      }
      #allow 39.110.207.95;
      #deny all;

spec:
  tls:
  - hosts:
    - repository-b.example.org
    secretName: repository-a-example-org-cert
  ingressClassName: nginx
  rules:
  - host: repository-b.example.org
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: certbot
            port:
              number: 443
```

```
$ kubectl apply -f /home/mhaya/certbot.yaml
service/certbot created
configmap/certbot created
pod/certbot created
ingress.networking.k8s.io/certbot-ingress created

$ kubectl get pods -n weko3
NAME                                                 READY   STATUS        RESTARTS   AGE
certbot                                              2/2     Running       0          17m
repository-b-example-org-web-b7c75f69d-zgzzs   3/3     Running       0          116m
research-ren-ng-web-6456df44f8-gb2wl                 3/3     Running       0          52d
repository-a-example-org-web-8c45847bc-q98md              0/3     Terminating   0          123m
```

```
$ kubectl exec -n weko3 certbot -c certbot -it -- certbot certonly --manual -d repository-b.example.org
Saving debug log to /var/log/letsencrypt/letsencrypt.log
Enter email address (used for urgent renewal and security notices)
 (Enter 'c' to cancel): wekosoftware@nii.ac.jp

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Please read the Terms of Service at
https://letsencrypt.org/documents/LE-SA-v1.3-September-21-2022.pdf. You must
agree in order to register with the ACME server. Do you agree?
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
(Y)es/(N)o: Y

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Would you be willing, once your first certificate is successfully issued, to
share your email address with the Electronic Frontier Foundation, a founding
partner of the Let's Encrypt project and the non-profit organization that
develops Certbot? We'd like to send you email about our work encrypting the web,
EFF news, campaigns, and ways to support digital freedom.
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
(Y)es/(N)o: N
Account registered.
Requesting a certificate for repository-b.example.org

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Create a file containing just this data:

8jL5597WRGJEcI1BylVMV5Xoo52GbtAtNMbwqk6Z13o.aE1Bx0pGOHkpzIrPJrkdX-TwyVQMitrmyeB7EP-o9xs

And make it available on your web server at this URL:

http://repository-b.example.org/.well-known/acme-challenge/8jL5597WRGJEcI1BylVMV5Xoo52GbtAtNMbwqk6Z13o

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Press Enter to Continue
```

Execute following commands on other terminal.

```
kubectl exec -n weko3 certbot -c nginx -- mkdir -p /tmp/.well-known/
kubectl exec -n weko3 certbot -c nginx -- bash -c "echo -n '8jL5597WRGJEcI1BylVMV5Xoo52GbtAtNMbwqk6Z13o.aE1Bx0pGOHkpzIrPJrkdX-TwyVQMitrmyeB7EP-o9xs' > /tmp/.well-known/8jL5597WRGJEcI1BylVMV5Xoo52GbtAtNMbwqk6Z13o"
curl -kL http://repository-b.example.org/.well-known/acme-challenge/8jL5597WRGJEcI1BylVMV5Xoo52GbtAtNMbwqk6Z13o


kubectl exec -n weko3 certbot -c nginx -- bash -c "echo -n 'RddGsh-L7e7s7NjqLLmMpgO84K0KZ4uKGwE02WZCDeQ.xGvuXEtTCzGpV7hliWWSF5-zSgh524rr1pdniwMtHXM' > /tmp/.well-known/RddGsh-L7e7s7NjqLLmMpgO84K0KZ4uKGwE02WZCDeQ"

```
Press Enter to Continue

Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/repository-b.example.org/fullchain.pem
Key is saved at:         /etc/letsencrypt/live/repository-b.example.org/privkey.pem
This certificate expires on 2024-05-10.
These files will be updated when the certificate renews.

NEXT STEPS:
- This certificate will not be renewed automatically. Autorenewal of --manual certificates requires the use of an authentication hook script (--manual-auth-hook) but one was not provided. To renew this certificate, repeat this same certbot command before the certificate's expiry date.

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
If you like Certbot, please consider supporting our work by:
 * Donating to ISRG / Let's Encrypt:   https://letsencrypt.org/donate
 * Donating to EFF:                    https://eff.org/donate-le
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
```

```
kubectl cp -n weko3 -c certbot certbot:/etc/letsencrypt/archive/repository-b.example.org/fullchain1.pem fullchain.pem
```

```
kubectl cp -n weko3 -c certbot certbot:/etc/letsencrypt/archive/repository-b.example.org/privkey1.pem privkey.pem
```

```
$ openssl x509 -noout -in fullchain.pem -dates
notBefore=Feb 10 23:34:47 2024 GMT
notAfter=May 10 23:34:46 2024 GMT
```

'''
sudo mkdir /usr/local/share/keys/repository-b.example.org-certs/
'''

```
sudo mv privkey.pem /usr/local/share/keys/repository-b.example.org-certs/privkey.pem
sudo mv fullchain.pem /usr/local/share/keys/repository-b.example.org-certs/fullchain.pem
```

```
kubectl create secret -n weko3 tls repository-a-example-org-cert --key /usr/local/share/keys/repository-b.example.org-certs/privkey.pem --cert /usr/local/share/keys/repository-b.example.org-certs/fullchain.pem --dry-run=client -o yaml
```

```
kubectl create secret -n weko3 tls repository-a-example-org-cert --key /usr/local/share/keys/repository-b.example.org-certs/privkey.pem --cert /usr/local/share/keys/repository-b.example.org-certs/fullchain.pem -o yaml
```

```
$ kubectl apply -f /usr/local/share/deploy_logs/repository-b.example.org/manifests/deploy-web.yaml
deployment.apps/repository-a-example-org-web created
```

```
$ kubectl apply -f /usr/local/share/deploy_logs/repository-b.example.org/manifests/ingress.yaml
ingress.networking.k8s.io/repository-a-example-org-ingress created
```

$ kubectl delete -f /usr/local/share/deploy_logs/repository-a.example.org/ssl/certbot.yaml
service "certbot" deleted
configmap "certbot" deleted
pod "certbot" deleted
ingress.networking.k8s.io "certbot-ingress" deleted


##

$ sudo cp /usr/local/share/deploy_logs/repository-a.example.org/ssl/repository-a.example.org.key /fs-shibboleth/repository-a.example.org/server.key

$ sudo cp /usr/local/share/deploy_logs/repository-a.example.org/ssl/repository-a.example.org.crt /fs-shibboleth/repository-a.example.org/server.crt


shibboleth2.xml

```
<SPConfig xmlns="urn:mace:shibboleth:3.0:native:sp:config"
    xmlns:conf="urn:mace:shibboleth:3.0:native:sp:config"
    clockSkew="180">

    <OutOfProcess tranLogFormat="%u|%s|%IDP|%i|%ac|%t|%attr|%n|%b|%E|%S|%SS|%L|%UA|%a" />
 <UnixListener address="/tmp/shibd.sock"/>
    <RequestMapper type="XML">
    <RequestMap>
        <Host name="repository-a.example.org"
                authType="shibboleth"
                requireSession="true"
                redirectToSSL="443">
            <Path name="/secure" />
        </Host>
    </RequestMap>
    </RequestMapper>

    <ApplicationDefaults entityID="https://repository-a.example.org/shibboleth-sp"
        REMOTE_USER="eppn persistent-id targeted-id"
        cipherSuites="DEFAULT:!EXP:!LOW:!aNULL:!eNULL:!DES:!IDEA:!SEED:!RC4:!3DES:!kRSA:!SSLv2:!SSLv3:!TLSv1:!TLSv1.1">
        <Sessions lifetime="28800" timeout="3600" relayState="ss:mem"
                  checkAddress="false" handlerSSL="false" cookieProps="http">
        <SSO entityID="https://idp.example.org/saml2/idp/metadata.php">
              SAML2
            </SSO>
            <Logout>SAML2 Local</Logout>
            <LogoutInitiator type="Admin" Location="/Logout/Admin" acl="127.0.0.1 ::1" />
            <Handler type="MetadataGenerator" Location="/Metadata" signing="false"/>
            <Handler type="Status" Location="/Status" acl="127.0.0.1 ::1"/>
            <Handler type="Session" Location="/Session" showAttributeValues="false"/>
            <Handler type="DiscoveryFeed" Location="/DiscoFeed"/>
        </Sessions>
        <Errors supportContact="root@localhost"
            helpLocation="/about.html"
            styleSheet="/shibboleth-sp/main.css"/>
        <MetadataProvider type="XML" validate="false" file="idp-metadata.xml"/>
        <MetadataProvider type="XML" validate="true"
                url="https://idp.example.org/saml2/idp/metadata.php">
        </MetadataProvider>
        <CredentialResolver type="File" key="server.key" certificate="server.crt"/>
    </ApplicationDefaults>
    <SecurityPolicyProvider type="XML" validate="true" path="security-policy.xml"/>
    <ProtocolProvider type="XML" validate="true" reloadChanges="false" path="protocols.xml"/>
</SPConfig>
```

```
$ kubectl exec -n weko3 repository-a-example-org-web-76ff8d9fff-2wrfj -c nginx -- supervisorctl restart shibd
shibd: stopped
shibd: started
```

### Checking Access from a Browser

Checking that access is possible from a browser.

If you want to confirm access before deploying Ingress, you can access by port forwarding from kubectl command.

```
$ kubectl port-forward -n weko3 <WEB POD name> 8080:443 &
```

# References

- orginal text. https://meatwiki.nii.ac.jp/confluence/pages/viewpage.action?pageId=91390025


#

# Shibboleth login pattern. (True: Shibboleth IdP(JairoCloud), False: Embedded DS-Pattern 1)
WEKO_ACCOUNTS_SHIB_IDP_LOGIN_ENABLED = True

# Enable Shibboleth login system using DP selection only.
WEKO_ACCOUNTS_SHIB_DP_LOGIN_DIRECTLY_ENABLED = True

# Enable Shibboleth login system using IdP selection only
WEKO_ACCOUNTS_SHIB_INST_LOGIN_DIRECTLY_ENABLED = True


```
$ kubectl exec -n weko3 -it research-ren-ng-web-6456df44f8-gb2wl -c nginx -- cat /usr/share/nginx/html/secure/login.php
<?php

$base =  $_SERVER['REQUEST_SCHEME']."://".$_SERVER['SERVER_NAME'];

// ERROR
  $url = $base."/weko/shib/login?next=%2F";
  $curl = curl_init();
  $post_args=[];
  $post_args['SHIB_ATTR_USER_NAME']=$_SERVER['HTTP_WEKOID'];
  $post_args["SHIB_ATTR_EPPN"]=$_SERVER['Remote-User'];
  $post_args["SHIB_ATTR_MAIL"]=$_SERVER['mail'];
  $post_args["SHIB_ATTR_SESSION_ID"]=$_SERVER['Shib-Session-ID'];
  $post_args["SHIB_ATTR_ROLE_AUTHORITY_NAME"]="管理者";
  $options = array(
    //Method
    CURLOPT_POST => true,//POST
    //body
    CURLOPT_POSTFIELDS => http_build_query($post_args),
  );
  $cookie=tempnam(sys_get_temp_dir(),'cookie_');
  //set options
  curl_setopt($curl,CURLOPT_URL,$url);
  curl_setopt($curl, CURLOPT_RETURNTRANSFER, true);
  curl_setopt($curl,CURLOPT_SSL_VERIFYPEER, false);
  curl_setopt($curl, CURLOPT_SSL_VERIFYHOST, 0);
  curl_setopt($curl, CURLOPT_COOKIESESSION, true);
  curl_setopt_array($curl, $options);
  curl_setopt($curl,CURLOPT_COOKIEJAR,$cookie);
  curl_setopt($curl,CURLOPT_COOKIEFILE,$cookie);
  // request
  $result = curl_exec($curl);
  $info = curl_getinfo($curl);
  $errno = curl_errno($curl);
  $error = curl_error($curl);
  curl_close($curl);
  if (CURLE_OK !== $errno) {
        throw new RuntimeException($error, $errno);
  }
  header("HTTP/1.1 302 Found");
  header("Location: ".$base.$result);
  //var_dump($app_cookies[0]['value']);
?>
```


```
$ kubectl rollout restart deploy -n weko3 repository-b-example-org-web
deployment.apps/repository-b-example-org-web restarted
```

https://research.ren.africa/Shibboleth.sso/Metadata
https://repository-aggregator.ren.africa/Shibboleth.sso/Metadata
