# Building kubelet instance

## dockerのインストール

1. remove the exist docker

2. Install latest version of docker

```
$ sudo yum remove docker \
                   docker-common \
                   docker-selinux \
                   docker-engine
$ sudo yum install -y yum-utils
$ sudo yum-config-manager \
     --add-repo \
     https://download.docker.com/linux/centos/docker-ce.repo
$ sudo yum install docker-ce
```

3. start the docker

```
$ sudo systemctl start docker
```

4. check the running status of docker

```
$ systemctl status docker 

```

5. test docker using hello-world image

```
$ sudo docker run hello-world
```

6. Confirm login to container registry

ref. https://docs.docker.jp/engine/installation/linux/docker-ce/centos.html

## Installation of docker-compose

execute following commands.

```
$ sudo curl -L "https://github.com/docker/compose/releases/download/v2.18.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
$ sudo chmod +x /usr/local/bin/docker-compose
```

check the installted version.

```
$ docker-compose -v
```

ref. https://docs.docker.com/compose/install/


## Installation of kubectl

If the version of kubectl is different between the server side and the client side, the command may cause an error.

During installation, look at the server-side version and make sure that there are no problems with the version of kubectl to be installed.


To install the latest version
Execute the following command

```
$ curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
$ curl -LO "https://dl.k8s.io/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl.sha256"
$ echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check
$ sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
$ kubectl version --client
```

### To install a specific version

Execute the following commands

```
$ curl -LO https://dl.k8s.io/release/<version>/bin/linux/amd64/kubectl
$ curl -LO "https://dl.k8s.io/<version>/bin/linux/amd64/kubectl.sha256"
```

```
$ echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check
```

Check that OK is displayed.

```
$ sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
$ kubectl version
```

ref. 
- https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/
- https://github.com/kubernetes/kubectl/issues/675

## Installation of Git

Execute the following commands

```
$ sudo yum install git
```

## Connecting k8s cluster


## Installation of Helm

Execute the following commands

```
$ mkdir /tmp/install-helm
$ cd /tmp/install-helm/
$ curl "https://get.helm.sh/helm-<version>-linux-amd64.tar.gz" -o helm.tar.gz
$ tar -zxvf helm.tar.gz
$ sudo mv linux-amd64/helm /usr/local/bin/
```

## Mount of file system

Execute the following commands

```
$ sudo mkdir /fs-pgbackup
$ sudo mkdir /fs-esbackup
$ sudo mkdir /fs-shibboleth
$ sudo mkdir /fs-nginx
$ sudo mkdir /fs-data
$ sudo mkdir /fs-config
$ sudo mount <ip-addr>:/fs-pgbackup /fs-pgbackup
$ sudo mount <ip-addr>:/fs-esbackup /fs-esbackup
$ sudo mount <ip-addr>:/fs-shibboleth /fs-shibboleth
$ sudo mount <ip-addr>:/fs-nginx /fs-nginx
$ sudo mount <ip-addr>:/fs-data /fs-data
$ sudo mount <ip-addr>:/fs-config /fs-config
```
ip-addr: Enter the IP address of the filesystem mount target.

```
$ df -h
Filesystem                 Size  Used Avail Use% Mounted on
devtmpfs                   3.8G     0  3.8G   0% /dev
tmpfs                      3.9G     0  3.9G   0% /dev/shm
tmpfs                      3.9G   17M  3.9G   1% /run
tmpfs                      3.9G     0  3.9G   0% /sys/fs/cgroup
/dev/sda3                   39G  2.6G   36G   7% /
/dev/sda1                  512M   12M  501M   3% /boot/efi
tmpfs                      782M     0  782M   0% /run/user/994
tmpfs                      782M     0  782M   0% /run/user/10020
tmpfs                      782M     0  782M   0% /run/user/27006
10.0.10.12:/fs-pgbackup    8.0E     0  8.0E   0% /fs-pgbackup
10.0.10.12:/fs-esbackup    8.0E     0  8.0E   0% /fs-esbackup
10.0.10.12:/fs-shibboleth  8.0E     0  8.0E   0% /fs-shibboleth
10.0.10.12:/fs-nginx       8.0E     0  8.0E   0% /fs-nginx
10.0.10.12:/fs-data        8.0E     0  8.0E   0% /fs-data
10.0.10.12:/fs-config      8.0E     0  8.0E   0% /fs-config
```

Check that the created file system is mounted.

Add the following settings to fstab so that the instance is automatically mounted at startup.

```
$ sudo vi /etc/fstab
$ cat /etc/fstab
~snip~
<ip-addr>:/fs-data /fs-data nfs defaults,nofail,nosuid,resvport 0 0
<ip-addr>:/fs-nginx /fs-nginx nfs defaults,nofail,nosuid,resvport 0 0
<ip-addr>:/fs-shibboleth /fs-shibboleth nfs defaults,nofail,nosuid,resvport 0 0
<ip-addr>:/fs-config /fs-config nfs defaults,nofail,nosuid,resvport 0 0
<ip-addr>:/fs-pgbackup /fs-pgbackup nfs defaults,nofail,nosuid,resvport 0 0
<ip-addr>:/fs-esbackup /fs-esbackup nfs defaults,nofail,nosuid,resvport 0 0
<ip-addr>:/fs-jcbackup /fs-jcbackup nfs defaults,nofail,nosuid,resvport 0 0 
```

## Installation of Kustomize

### Installation of Go


Specify the version and install go.


```
$ curl -s -o go<version of go>.linux-amd64.tar.gz https://dl.google.com/go/go<version of go>.linux-amd64.tar.gz
```

Example：curl -s -o go1.18.5.linux-amd64.tar.gz https://dl.google.com/go/go1.18.5.linux-amd64.tar.gz

```
$ sudo tar -C /usr/local -xzf go<version of go>.linux-amd64.tar.gz
```

Example：sudo tar -C /usr/local -xzf go1.18.5.linux-amd64.tar.gz

Add "/usr/local/go/bin" to PATH

```
$ vi .bash_profile 
```

Example: PATH=$PATH:/usr/local/go/bin

```
$ source .bash_profile
```

Check installed version.

```
$ go version
go version go1.18.5 linux/amd64
```

## Installation of Kustomize

```
$ git clone https://github.com/kubernetes-sigs/kustomize.git
$ cd kustomize/
$ git checkout kustomize/<version of kustomize> -b <version of kustomize>
```

Example: git checkout kustomize/v4.4.1 -b v4.4.1


```
$ cd kustomize
$ KUSTOMIZE_MODULE=$(cat go.mod | grep module | awk '{print $2}')
$ rm go.mod go.sum
$ go mod init $KUSTOMIZE_MODULE
$ go mod tidy
$ go install .
$ sudo cp ~/go/bin/kustomize
```

Check installed version of kustomize.

```
$ kustomize version
{Version:unknown GitCommit:$Format:%H$ BuildDate:1970-01-01T00:00:00Z GoOs:linux GoArch:amd64}
```

## Installation of SecretsFromProperties(custom plugin)


Install SecretsFromProperties in the weko-k8s repository.

```
$ cd weko-k8s/src/kustomize-plugin/
$ go build --buildmode=plugin -o ../../kustomize-plugin/kustomize/plugin/rcos.nii.ac.jp/v1/secretsfromproperties/SecretsFromProperties.so kustomize/plugin/rcos.nii.ac.jp/v1/secretfromproperties/SecretsFromProperties.go
```

SecretsFromProperties allows the secret.properties file to be used to output the secret yaml.

The following example checks whether SecretsFromProperties can be used with PostgreSQL.

```
$ cd weko-k8s/deploy/postgresql/
$ XDG_CONFIG_HOME=../../kustomize-plugin SECRET_PATH=<secret.propertiesのpath>/secret.properties kustomize build --enable-alpha-plugins base
2022/08/09 04:32:50 Attempting plugin load from '../../kustomize-plugin/kustomize/plugin/rcos.nii.ac.jp/v1/secretsfromproperties/SecretsFromProperties.so'
~snip~
apiVersion: v1
data:
  invenio: ...
kind: Secret
metadata:
  name: postgresql-infrastructure-roles
  namespace: weko3pg
type: Opaque
~snip~
```

If Secrets are outputed in yaml, SecretsFromProperties has been successfully installed.

The version of the dependent package is updated, which may result in the following error

Error example

```
Error: accumulating resources: accumulation err='accumulating resources from '../../base': '/usr/local/weko-k8s.20230214/deploy/postgresql/base' must resolve to a file': recursed accumulation of path '/usr/local/weko-k8s.20230214/deploy/postgresql/base': loading generator plugins: plugin ../../../../kustomize-plugin/kustomize/plugin/rcos.nii.ac.jp/v1/secretsfromproperties/SecretsFromProperties.so fails to load: plugin.Open("../../../../kustomize-plugin/kustomize/plugin/rcos.nii.ac.jp/v1/secretsfromproperties/SecretsFromProperties"): plugin was built with a different version of package github.com/mailru/easyjson/jlexer
```

After executing "go mod tidy", you can change the package version on the Kustomize side. The version of the plugin can be checked at "weko-k8s/src/kustomize-plugin/go.mod".


Command Example

```
$ cd <cloned directory>/kustomize/kustomize
$ go get github.com/mailru/easyjson@v0.7.6
$ go mod tidy
$ go install .
$ sudo cp ~/go/bin/kustomize /usr/local/bin/
```

## Installation of rclone

Execute following command for install rclone.

```
$ sudo yum install -y rclone
```

If the above command cannot be used to install the software due to the distribution, execute the following command instead.

```
$ curl https://rclone.org/install.sh | sudo bash
```

### configuration of rclone

Create the following configuration files in the home directory of each account that needs access.

```
$ mkdir -p ~/.config/rclone
$ vi ~/.config/rclone/rclone.conf
$ chmod og-rwx -R ~/.config
```

Below is a sample configuration for OCI Object Storage and ActiveScale.

```
$ cat ~/.config/rclone/rclone.conf
[oci-pr]
type = s3
provider = Other
env_auth = false
access_key_id = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
secret_access_key = yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
region = ap-tokyo-1
endpoint = https://nrjjxl1nnwb4.compat.objectstorage.ap-tokyo-1.oraclecloud.com
acl = authenticated-read
 
[as]
type = s3
provider = Other
env_auth = false
access_key_id = xxxxxxxxxxxxxxxxxxxxxxxxxx
secret_access_key = yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
endpoint = http://storage2.s3.nii.ac.jp
acl = authenticated-read
```


### Connection Testing

Check if the bucket list of OCI object storage can be obtained.

```
$ rclone lsd oci-pr://
          -1 2022-10-02 13:32:27        -1 backup
          -1 2022-09-30 00:16:39        -1 contents
          -1 2022-09-30 00:17:09        -1 esbackup
          -1 2022-09-30 00:16:47        -1 log
```

Check to see if you can get a list of ActiveScale buckets.

```
$ rclone lsd as://
          -1 2022-10-02 13:32:27        -1 jc_contents_pr
```

