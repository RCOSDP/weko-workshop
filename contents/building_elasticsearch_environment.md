# Building elasticsearch environment

## Building Elasticsearch

Execute the following commands.

```
$ cat /usr/local/share/keys/elasticsearch-env.sh
export ELASTICSEARCH_S3_ACCESS_KEY=***
export ELASTICSEARCH_S3_SECRET_KEY=***
export ELASTICSEARCH_S3_ENDPOINT=***
export ELASTICSEARCH_S3_BUCKET=***
$ source /usr/local/share/keys/elasticsearch-env.sh
$ cd <cloned directory>/weko3
$ docker-compose build elasticsearch
$ docker tag weko3_elasticsearch:latest nrt.ocir.io/<tenancy-namespace>/<dir>/elasticsearch:<tag>
$ docker push nrt.ocir.io/<tenancy-namespace>/<dir>/elasticsearch:<tag>
```

## Building essnapshooter

Execute the following commands.

```
$ cd <cloned directory>/weko-k8s/src/essnapshooter/
$ docker build -t essnapshooter .
$ docker tag essnapshooter:latest <image repository>/essnapshooter:<tag>
$ docker push nrt.ocir.io/<tenancy-namespace>/<dir>/essnapshooter:<tag>
```

## Deploying Elasticsearch

```
$ cd weko-k8s/deploy/elasticsearch/overlay/<dir>/
$ XDG_CONFIG_HOME=../../../../kustomize-plugin SECRET_PATH=/usr/local/share/keys/secret.properties kustomize build --enable-alpha-plugins . | kubectl create -f -
```

Check the running status.

```
$ kubectl get pod -n weko3es -o wide
NAME                                                              READY   STATUS    RESTARTS   AGE     IP             NODE            NOMINATED NODE   READINESS GATES
elasticsearch-exporter-prometheus-elasticsearch-exporter-52qp8m   1/1     Running   0          6m27s   10.64.83.41    10.65.39.47     <none>           <none>
weko-elasticsearch-0                                              1/1     Running   0          6m27s   10.64.240.50   10.65.12.57     <none>           <none>
weko-elasticsearch-1                                              1/1     Running   0          5m15s   10.64.163.12   10.65.78.126    <none>           <none>
weko-elasticsearch-2                                              1/1     Running   0          4m19s   10.64.16.246   10.65.197.237   <none>           <none>
```

* Check the following items
  * READY of each POD should be 1/1.
  * STATUS of each POD should be Running.

```
$ kubectl exec -n weko3es weko-elasticsearch-0 -it -- curl localhost:9200/_cluster/health?pretty
{
  "cluster_name" : "k8s-cluster",
  "status" : "green",
  "timed_out" : false,
  "number_of_nodes" : 3,
  "number_of_data_nodes" : 3,
  "active_primary_shards" : 0,
  "active_shards" : 0,
  "relocating_shards" : 0,
  "initializing_shards" : 0,
  "unassigned_shards" : 0,
  "delayed_unassigned_shards" : 0,
  "number_of_pending_tasks" : 0,
  "number_of_in_flight_fetch" : 0,
  "task_max_waiting_in_queue_millis" : 0,
  "active_shards_percent_as_number" : 100.0
}
```

* Check the following items
  * status must be GREEN.

```
$ kubectl logs -n weko3es weko-elasticsearch-0 | less 
```

Make sure there are no error logs

```
$ kubectl logs -n weko3es weko-elasticsearch-1 | less 
```

Make sure there are no error logs

```
$ kubectl logs -n weko3es weko-elasticsearch-2 | less 
```

Make sure there are no error logs


### Creating S3 repository

```
$ kubectl exec -n weko3es weko-elasticsearch-0 -it -- bash
[root@weko-elasticsearch-0 elasticsearch]# curl -XPUT "$(hostname -i):9200/_snapshot/s3_repository" -H 'Content-Type: application/json' -d"
 {
   \"type\": \"s3\",
   \"settings\": {
     \"client\": \"default\",
     \"region\": \"ap-tokyo-1\",
     \"endpoint\": \"${ELASTICSEARCH_S3_ENDPOINT}\",
     \"bucket\": \"${ELASTICSEARCH_S3_BUCKET}\"
   }
 }"
{"acknowledged":true}
```

### Checking of backup job (performed after job execution)

```
$ kubectl get pod -n weko3es 
```

Check that the STATUS of the snapshotter is COMPLETED.

```
NAME                                                              READY   STATUS      RESTARTS   AGE
elasticsearch-exporter-prometheus-elasticsearch-exporter-52qp8m   1/1     Running     0          7d19h
elasticsearch-snapshotter-27725280-6kkqx                          0/1     Completed   0          2d10h
elasticsearch-snapshotter-27726720-qrkz8                          0/1     Completed   0          34h
elasticsearch-snapshotter-27728160-x2j56                          0/1     Completed   0          10h
weko-elasticsearch-0                                              1/1     Running     0          7d19h
weko-elasticsearch-1                                              1/1     Running     0          7d19h
weko-elasticsearch-2                                              1/1     Running     0          7d19h
```