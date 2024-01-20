# Describing secret.properties

For middleware deployment, kustomize is used. In addition, SecretsFromProperties is used as a custom plugin for kustomize to create Secrets.

Secret is not directly described in the yaml file, but is described in secret.properties and output in yaml format by kustomize build.

This page shows how to describe secret.properties.

#### location of secret.properties

Location : /usr/local/share/keys/

#### Specification of secret.properties

Describe the following for each data to be deployed as Secret.

```
<namespace>. <Secret name>. <Data name>=<Value (to be written without base64 encoding)>.
```

As an example, we show the case of ocir-secret, which is used to pull Redis images from the container registry.

```
weko3re.ocir-secret..dockerconfigjson = {"auths":{"nrt.ocir.io":{"username":"<username>","password":"<password>","email":"example@example.com","auth":"<auth>"}}}
```

auth： Base64-encoded authentication information. The following command is used to create it.

```
　$ echo -n "<tenancy-namespace>/<username>:<password>" | base64
```

Templates with Secret entries for each middleware are available in the weko-k8s repository.

https://github.com/RCOSDP/weko-k8s/blob/release/deploy/secret.properties


Specification of SecretsFromProperties yaml file

| Field | Value | Description |
| --------- | ------ | ----- |
| apiVersion | rcos.nii.ac.jp/v1 ||	
| kind | SecretsFromProperties ||	
|metadata.name|	Name of SecretsFromProperties	 ||
|metadata.namespace|	Namespace of SecretsFromProperties ||
|behavior|	create, replace, or merge 	|create：Create a new Secret.|
|disableNameSuffixHash|true or false	|true： Do not combine the hash value with the name of the Secret.
|^ |^ |false： Combine the hash value with the name of the Secret. Default. |
|name|	Name of Secret	||
|namespace|	Namespace of Secret||	
|type|	Type of Secret|	|
|keys|	Key of Secret|	|




As an example, we show the case of ocir-secret.

```
apiVersion: rcos.nii.ac.jp/v1
kind: SecretsFromProperties
metadata:
  name: ocir-secret
  namespace: <namespace>
behavior: create
disableNameSuffixHash: true
name: ocir-secret
namespace: <namespace>
type: kubernetes.io/dockerconfigjson
keys:
  - .dockerconfigjson
```


How to build kustomize using SecretsFromProperties


The following is a command to build kustomize using SecretsFromProperties.

```
$ cd <>
$ XDG_CONFIG_HOME=<Directory where SecretsFromProperties was built>/kustomize-plugin SECRET_PATH=<Directory of secret.properties>/secret.properties kustomize build --enable-alpha-plugins .
```

To deploy the built and output yaml, execute the following command.

```
$ XDG_CONFIG_HOME=<Directory where SecretsFromProperties was built>/kustomize-plugin SECRET_PATH=<Directory of secret.properties>/secret.properties kustomize build --enable
```