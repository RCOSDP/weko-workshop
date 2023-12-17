# Initialize repository

## Users and Roles

After installation, the following users will be pre-set.

| Username | Role | Password |
|-|-|-|
|wekosoftware@nii.ac.jp|System Administrator|uspass123|
|repoadmin@example.org|Repository Administrator|uspass123|
|comadmin@example.org|Community Administrator|uspass123|
|contributor@example.org|Contributor|uspass123|
|user@example.org||uspass123|

Note: Please delete them before production operation.

## Change the server name

To change the server name of the repository, change the value of the "INVENIO_WEB_HOST_NAME" setting in docker-compose2.yml.

The OAI identifier prefix is "oai:INVENIO_WEB_HOST_NAME".
To change it, change the value of ""OAISERVER_ID_PREFIX"" in "scripts/instance.cfg" and restart container. Configuration file "invenio.cfg" in the container is updated according to the changes.

The invenio.cfg in the container is as follows:

```
/home/invenio/.virtualenvs/invenio/var/instance/invenio.cfg
```
Note: Currently, changing the server name requires data modification after the item is registered.
