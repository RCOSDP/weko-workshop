# Build the new WEKO3 container image

This section describes how to build a WEKO3 container image for running on Kubernates.

## Clone WEKO3 Repository

Skip this step if you have already cloned it.

Clone the code locally from Github. Additionally, check out the target version.

```
git clone https://github.com/RCOSDP/weko.git
cd weko
git checkout -b <branchName> refs/tags/<version tag>
```

for example,

```
git checkout -b v1.0.3 refs/tags/v1.0.3
```

## Update Repository

Reflects updates from the remote repository in the local repository.

```
git fetch -p
git merge origin/<target branchName>
```

## Modify Dockerfile

To create an image for Kubernates, uncomment the following in the Dockerfile

```
$ vi Dockerfile
~snip~
# RUN mv /home/invenio/.virtualenvs/invenio/var/instance/static /home/invenio/.virtualenvs/invenio/var/instance/static.org
~snip~
```

## Build Dockerfile

Build WEKO3 and nginx.

```
docker-compose build web
docker-compose build nginx
```

## Register to image repository

Tag the built container image with the version tag.

```
docker tag weko-web:latest  <registry path>/web:<version>
docker tag weko-nginx:latest <registry path>/nginx:<version>
```

Push container images to the image registry.

```
git push <registry path>/web:<version>
git push <registry path>/nginx:<version>
```