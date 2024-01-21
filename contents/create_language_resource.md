# Create language resource

## Preparing to add a language

Open the configuration file.

```
scripts/instance.cfg
```

Add language information to I18N_LANGUAGES. 

```
I18N_LANGUAGES = [('ja', 'Japanese'), ('zh', 'Chinese'), ('id', 'Indonesian'), ('vi', 'Vietnamese'),('ms', 'Malay'), ('fil', 'Filipino (Pilipinas)'), ('th', 'Thai'), ('hi', 'Hindi'), ('ar', 'Arabic')]
```

For example, add French.

```
I18N_LANGUAGES = [('ja', 'Japanese'), ('fr', 'French') ,('zh', 'Chinese'), ('id', 'Indonesian'), ('vi', 'Vietnamese'),('ms', 'Malay'), ('fil', 'Filipino (Pilipinas)'), ('th', 'Thai'), ('hi', 'Hindi'), ('ar', 'Arabic')]
```

Build an image to get the configuration file into the container.

```
$ docker-compose -f docker-compose2.yml build web
```

```
$ docker-compose -f docker-compose2.yml restart
```

Add French as an option in the administration.

```
docker-compose -f docker-compose2.yml exec web invenio language create --active "fr" "Frence" 000
```

Enable French from the WEKO3 administration page(/admin/language/).

## Adding language resources to a module

Create language resources for the module.

The work will be performed on the container.

```
docker-compose -f docker-compose2.yml exec web bash
```

For example, for adding language resources to the weko-theme module, execute following commands.

```
$ cd modules/weko-theme
$ python setup.py init_catalog -l fr
~snip~
running init_catalog
creating catalog weko_theme/translations/fr/LC_MESSAGES/messages.po based on weko_theme/translations/messages.pot
```

Edit the created messages.po. Here, as an example, we set the French "Se connecter" for "Log in".

```
modules/weko-theme/weko_theme/translations/fr/LC_MESSAGES/messages.po 
```

```
#: weko_theme/templates/weko_theme/header_login.html:24
msgid "Log in"
msgstr "Se connecter"
```

After editing, compile messages.po.

```
$ python setup.py compile_catalog
~snip~
running compile_catalog
compiling catalog weko_theme/translations/ja/LC_MESSAGES/messages.po to weko_theme/translations/ja/LC_MESSAGES/messages.mo
compiling catalog weko_theme/translations/fr/LC_MESSAGES/messages.po to weko_theme/translations/fr/LC_MESSAGES/messages.mo
compiling catalog weko_theme/translations/en/LC_MESSAGES/messages.po to weko_theme/translations/en/LC_MESSAGES/messages.mo
```

Restarting the container will check the switching of language resources.