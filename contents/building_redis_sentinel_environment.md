# Building Redis Sentinel environment

## Building Redis image

Execute the following commands

```
$ cd weko-k8s/src/redis/
$ docker build -t <repository path>/redis:<tag> .
$ docker push <repository path>/redis:<tag>
```

## Building Sentinel

Execute the following commands

```
$ cd weko-k8s/src/sentinel/
$ docker build -t <repository path>/sentinel:<tag> .
$ docker push <repository path>/sentinel:<tag>
```

## Deploying Redis

```
$ cd weko-k8s/deploy/redis/overlay/<dir>/
```

```
$ XDG_CONFIG_HOME=../../../../kustomize-plugin SECRET_PATH=/usr/local/share/keys/secret.properties kustomize build --enable-alpha-plugins . | kubectl apply -f -
```

Check that the system is up and running after deployment.


```
$ kubectl get pod -n weko3re -o wide
NAME                             READY   STATUS    RESTARTS   AGE   IP              NODE          NOMINATED NODE   READINESS GATES
weko-redis-0                     2/2     Running   0          46m   10.244.7.134    10.0.10.160   <none>           <none>
weko-redis-1                     2/2     Running   0          59m   10.244.8.83     10.0.10.11    <none>           <none>
weko-sentinel-6967c4647d-58csq   1/1     Running   0          35m   10.244.10.162   10.0.10.172   <none>           <none>
weko-sentinel-6967c4647d-h5vx4   1/1     Running   0          60m   10.244.9.218    10.0.10.115   <none>           <none>
weko-sentinel-6967c4647d-qvm5q   1/1     Running   0          35m   10.244.10.126   10.0.10.221   <none>           <none>
```

- Check the following items
  - READY of Redis should be 2/2
  - READY of Sentinel should be 1/1
  - STATUS of all PODs should be Running

```
$ for redis in $(kubectl get pod -n weko3re | grep redis | awk '{print $1}');do kubectl exec -n weko3re $redis -c redis -- redis-cli info | grep role ;done
role:slave
role:master
```

Check that master and slave exist


```
$ for sentinel in $(kubectl get pod -n weko3re | grep sentinel | awk '{print $1}');do kubectl exec -n weko3re $sentinel -c sentinel -- redis-cli -p 26379 info | grep mymaster ;done
master0:name=mymaster,status=ok,address=10.244.8.83:6379,slaves=1,sentinels=3
master0:name=mymaster,status=ok,address=10.244.8.83:6379,slaves=1,sentinels=3
master0:name=mymaster,status=ok,address=10.244.8.83:6379,slaves=1,sentinels=3
```

- Check the following items.
  - address is included in the IP address of the running Redis
  - slaves is 1
  - sentinels must be 3

```
$ for sentinel in $(kubectl get pod -n weko3re | grep sentinel | awk '{print $1}');do kubectl exec -n weko3re $sentinel -c sentinel -- redis-cli -p 26379 sentinel sentinels mymaster | grep _down ;done
```

Nothing should be output. If any output is produced, the downed Sentinel is included in the monitoring target.

```
$ for sentinel in $(kubectl get pod -n weko3re | grep sentinel | awk '{print $1}');do kubectl exec -n weko3re $sentinel -c sentinel -- redis-cli -p 26379 sentinel slaves mymaster | grep _down ;done
```

Nothing should be output. If any output is produced, the downed slave is included in the monitored target.