# Clone code repositories

１．Clone the repository.

```
$ git clone <repository-url> #If a user name and password are requested, use the one issued.
```

The <repository-url> can be found on the clone source repository page.

The main repositories used are as follows.

| Name  | Repository URL  | Repository Type  | Description  |
| --------- | --------- | --------- |--------- |
| weko-k8s | https://github.com/RCOSDP/weko-k8s |  Private	| Used to build various middleware for using WEKO3.|
| weko3 | https://bitbucket.org/niijp/weko3 | Private	 | WEKO3 |
| kubernetes-ingress | https://github.com/nginxinc/kubernetes-ingress | Public	|Used to build Ingress controllers.|

２．Checkout for intended use.

```
$ cd <repository dir>
$ git checkout <commit ID>
$ git branch
```
Check that the commit ID is correct.


※When pulling from github

When a source file is changed and pushed, the force option may be used to force the change.

Pull as follows to reflect the forced push changes.


```
$ git fetch origin <branch name>
$ git reset --hard origin/<branch name>
```


※When retrieving files in a submodule

The kubernetes-ingress repository is added as a submodule in weko-k8s. submodules are not linked to the weko-k8s repository and require a separate command to be executed to update them.

Execute the following command in the weko-k8s repository to get the submodule file.

```
$ git submodule update --init
```
