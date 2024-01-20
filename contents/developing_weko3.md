# Developing WEKO3

pip3 list --format=columns |grep cookiecutter
sudo pip3 install -U cookiecutter

$ pip3 list --format=columns |grep cookiecutter
cookiecutter                  1.7.3 

cd modules
cookiecutter cookiecutter-weko-module

$ cookiecutter cookiecutter-weko-module
/usr/local/lib/python3.6/site-packages/requests/__init__.py:104: RequestsDependencyWarning: urllib3 (1.26.18) or chardet (5.0.0)/charset_normalizer (2.0.12) doesn't match a supported version!
  RequestsDependencyWarning)
project_name [WEKO-FunGenerator]: 
project_shortname [weko-fungenerator]: 
package_name [weko_fungenerator]: 
github_repo [RCOSDP/weko-fungenerator]: 
description [Module of weko-fungenerator.]: 
author_name [National Institute of Informatics]: 
author_email [wekosoftware@nii.ac.jp]: 
year [2023]: 
copyright_holder [National Institute of Informatics]: 
copyright_by_intergovernmental [False]: 
superproject [WEKO3]: 
transifex_project [weko-fungenerator]: 
extension_class [WekoFunGenerator]: 
config_prefix [WEKO_FUNGENERATOR]:


python setup.py init_catalog -l fr
python setup.py compile_catalog