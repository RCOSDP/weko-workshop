# Building RabbitMQ environment

## Deploying RabbitMQ cluster

```
$ cd weko-k8s/deploy/rabbitmq/overlay/<dir>/
```

```
$ XDG_CONFIG_HOME=../../../../kustomize-plugin SECRET_PATH=/usr/local/share/keys/secret.properties kustomize build --enable-alpha-plugins . | kubectl create -f -
```

The first time you deploy, use create; the second and later times you can deploy by using apply.


## Check cluster startup


```
$ kubectl -n rabbitmq-system get all 
NAME                                             READY   STATUS    RESTARTS   AGE
pod/rabbitmq-cluster-operator-574fdfb4f7-9d8f7   1/1     Running   0          59s
 
NAME                                        READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/rabbitmq-cluster-operator   1/1     1            1           59s
 
NAME                                                   DESIRED   CURRENT   READY   AGE
replicaset.apps/rabbitmq-cluster-operator-574fdfb4f7   1         1         1       59s
```

Check that Operator is running from READY and STATUS

```
$ kubectl get pods -n weko3ra -o wide 
NAME                     READY   STATUS    RESTARTS   AGE   IP             NODE           NOMINATED NODE   READINESS GATES
weko-rabbitmq-server-0   1/1     Running   0          85s   10.64.231.57   10.65.70.180   <none>           <none>
weko-rabbitmq-server-1   1/1     Running   0          85s   10.64.40.55    10.65.70.180   <none>           <none>
weko-rabbitmq-server-2   1/1     Running   0          84s   10.64.181.82   10.65.70.180   <none>           <none>
```

Check that RabbitMQ READY is 1/1 and STATUS is Running

```
$ kubectl logs -n weko3ra weko-rabbitmq-server-0 
```

Check that there are no error logs.

```
$ kubectl logs -n weko3ra weko-rabbitmq-server-1
```

Check that there are no error logs.

```
$ kubectl logs -n weko3ra weko-rabbitmq-server-2
```

Check that there are no error logs.


## Creating a RabbitMQ User


To set up from the console
Refer to the following procedure when you can execute commands in RabbitMQ's POD.


1. creating a user


```
$ kubectl exec -n weko3ra weko-rabbitmq-server-0 -- rabbitmqctl add_user admin <addmin password>
$ kubectl exec -n weko3ra weko-rabbitmq-server-0 -- rabbitmqctl add_user invenio <invenio password>
```

Password is managed separately.


2. Tagging users

Tag users to set permissions.

```
$ kubectl exec -n weko3ra weko-rabbitmq-server-0 -- rabbitmqctl set_user_tags admin administrator
$ kubectl exec -n weko3ra weko-rabbitmq-server-0 -- rabbitmqctl set_user_tags invenio management
```



3. delete the initial user

Delete the initial user when deploying RabbitMQ.


```
$ DEFAULT_USER=$(kubectl -n weko3ra get secret weko-rabbitmq-default-user -o jsonpath="{.data.username}" | base64 --decode)
$ kubectl exec -n weko3ra weko-rabbitmq-server-0 -- rabbitmqctl delete_user ${DEFAULT_USER}
```

4. check if the user has been created


```
$ kubectl exec -n weko3ra weko-rabbitmq-server-0 -c rabbitmq -- rabbitmqctl list_users
Listing users ...
user    tags
admin   [administrator]
invenio [management]
```

- Check the following items
  - That there are two types of users: admin and invenio.
　admin's tag is administrator, and invenio's tag is management.



The login information for the initial account is confirmed from the kubectl server by the following method.


```
$ kubectl -n weko3ra get secret weko-rabbitmq-default-user -o jsonpath="{.data.username}" | base64 --decode
```

Then, Username is displayed.

```
$ kubectl -n weko3ra get secret weko-rabbitmq-default-user -o jsonpath="{.data.password}" | base64 --decode
```

Then, password is displayed.


## Create VHOST

Create a VHOST according to WEKO3 to be deployed.

Use repositories.txt created according to repositories.txt.


```
$ ../weko-k8s/scripts/make_rabbitmq_vhost.sh repositories.txt
```

WEKO2_FQDN is used among the items listed in #repositories.txt.


The created VHOST can be checked with the following command.

```
$ kubectl exec -n weko3ra weko-rabbitmq-server-0 -c rabbitmq -- rabbitmqctl list_vhosts
```
