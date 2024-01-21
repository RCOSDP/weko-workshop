# Develop hello world application

## Install cookiecutter

Install cookiecutter module.

```
$ pip3 list --format=columns |grep cookiecutter
cookiecutter                  1.7.3 
$ sudo pip3 install -U cookiecutter
```

## Make a module using module template 

Execute the following command to create the module.

```
cookiecutter cookiecutter-weko-module
```

When you run cookiecutter, you will be asked a few questions and eventually a template for the module will be created.

```
$ cd modules
$ cookiecutter cookiecutter-weko-module
/usr/local/lib/python3.6/site-packages/requests/__init__.py:104: RequestsDependencyWarning: urllib3 (1.26.18) or chardet (5.0.0)/charset_normalizer (2.0.12) doesn't match a supported version!
  RequestsDependencyWarning)
project_name [WEKO-FunGenerator]: WEKO-HELLO
project_shortname [weko-hello]: 
package_name [weko_hello]: 
github_repo [RCOSDP/weko-hello]: 
description [Module of weko-hello.]: 
author_name [National Institute of Informatics]: 
author_email [wekosoftware@nii.ac.jp]: 
year [2023]: 
copyright_holder [National Institute of Informatics]: 
copyright_by_intergovernmental [False]: 
superproject [WEKO3]: 
transifex_project [weko-hello]: 
extension_class [WekoHello]: 
config_prefix [WEKO_HELLO]:
```

The generated files and directory structure are as follows.

```
$ tree weko-hello/
weko-hello/
├── AUTHORS.rst
├── CHANGES.rst
├── CONTRIBUTING.rst
├── INSTALL.rst
├── LICENSE
├── MANIFEST.in
├── README.rst
├── babel.ini
├── docs
│   ├── Makefile
│   ├── api.rst
│   ├── authors.rst
│   ├── changes.rst
│   ├── conf.py
│   ├── configuration.rst
│   ├── contributing.rst
│   ├── examplesapp.rst
│   ├── index.rst
│   ├── installation.rst
│   ├── license.rst
│   ├── make.bat
│   ├── requirements.txt
│   └── usage.rst
├── examples
│   ├── app-fixtures.sh
│   ├── app-setup.sh
│   ├── app-teardown.sh
│   └── app.py
├── pytest.ini
├── requirements-devel.txt
├── run-tests.sh
├── setup.cfg
├── setup.py
├── tests
│   ├── conftest.py
│   ├── test_examples_app.py
│   └── test_weko_hello.py
└── weko_hello
    ├── __init__.py
    ├── config.py
    ├── ext.py
    ├── templates
    │   └── weko_hello
    │       ├── base.html
    │       └── index.html
    ├── version.py
    └── views.py

7 directories, 41 files
```

## Add url_prefix into views.py

Open 'weko-hello/weko_hello/views.py'.

The following definitions

```
blueprint = Blueprint(
    'weko_hello',
    __name__,
    template_folder='templates',
    static_folder='static',
)
```

Fix as follows. Add **url_prefix** parameter.

```
blueprint = Blueprint(
    'weko_hello',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/weko_hello',
)
```

## Modify docker-compose2.yml and requirements-weko-modules.txt

Open 'docker-compose2.yml' and add **weko-hello module** directory.

```
services:
  web:
    restart: "always"
    build:
      context: .
~snip~
    volumes:
      - weko3_data:/var/tmp
      - static_data:/home/invenio/.virtualenvs/invenio/var/instance/static
      - data_data:/home/invenio/.virtualenvs/invenio/var/instance/data
      - conf_data:/home/invenio/.virtualenvs/invenio/var/instance/conf
      - type: bind
        source: .
        target: /code
      - /code/modules/invenio-admin/invenio_admin.egg-info
~snip~
      - /code/modules/weko-swordserver/weko_swordserver.egg-info
      - /code/modules/weko-hello/weko_hello.egg-info
    user: invenio
```

Open 'requirements-weko-modules.txt' and add the follow line.

```
-e /code/modules/weko-hello
```

## Rebuild weko container

Build the container to install the created module.

```
docker-compose -f docker-compose2.yml build web
```

When finish to build, Rebuild the container.

```
docker-compose -f docker-compose2.yml down
docker-compose -f docker-compose2.yml up -d
```

## Copy static library and files

Execute the following commands to copy static library and files.

```
docker-compose -f docker-compose2.yml exec web invenio assets build
docker-compose -f docker-compose2.yml exec web invenio collect -v
```

When finish to execute command, Restart the containers.

```
docker-compose -f docker-compose2.yml restart
```

## Access the module

Open web browser and access bellow url via the browser.

```
https://<your_weko_server>/weko_hello/
```

Then you can see your created module view.

## Little modification 

Fix the module to be able to display today's date

Change **modules/weko-hello/weko_hello/views.py** as follow.

```
from __future__ import absolute_import, print_function

import datetime

from flask import Blueprint, render_template
from flask_babelex import gettext as _

blueprint = Blueprint(
    'weko_hello',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/weko_hello',
)


@blueprint.route("/")
def index():
    """Render a basic view."""
    now = datetime.datetime.now()
    
    return render_template(
        "weko_hello/index.html",
        module_name=_('WEKO-HELLO'),now=now)
```


Change **modules/weko-hello/weko_hello/templates/weko_hello/index.html** as follow. 

```
~snip~
{{_('Welcome to %(module_name)s', module_name=module_name)}}
<br/>
{{_('Now: %(now)s', now=now)}}
{%- endblock %}
```

End.