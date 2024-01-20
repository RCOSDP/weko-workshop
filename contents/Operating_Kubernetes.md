# Operating WEKO3 on Kubernetes

This section describes WEKO3 deployment and operational methods in a Kubernetes environment.

## [Building Infrastructure Environment](building_infrastructure_environment.md)
## Deploying a Repository


# Change k8s Image

/home/vagrant/weko/Dockerfile
<pre>
# RUN mv /home/invenio/.virtualenvs/invenio/var/instance/static /home/invenio/.virtualenvs/invenio/var/instance/static.org
↓
RUN mv /home/invenio/.virtualenvs/invenio/var/instance/static /home/invenio/.virtualenvs/invenio/var/instance/static.org
</pre>

build k8s Image
<pre>
docker-compose build web
docker-compose build nginx
</pre>

Put tag k8s Image
<pre>
docker tag weko-web:latest  nrt.ocir.io/nrbslpthdcco/at/ng/web:latest
docker tag weko-nginx:latest nrt.ocir.io/nrbslpthdcco/at/ng/nginx:latest
</pre>

make config.json to registrate Oracle Cloud
/home/vagrant/.docker/config.json
<pre>
{
	"auths": {
		"nrt.ocir.io": {
			"auth": "**********"
		}
	}
}
</pre>

Registration k8s Image to Oracle Cloud
<pre>
docker push nrt.ocir.io/nrbslpthdcco/at/ng/web:latest
docker push nrt.ocir.io/nrbslpthdcco/at/ng/nginx:latest
</pre>

Login k8s

$ kubectl get deployment -n weko3
cd /usr/local/share/deploy_logs/

$ grep -R "jdcat-dev-ir-rcos-nii-ac-jp-web"


cp -r jdcat-dev.ir.rcos.nii.ac.jp-2022-10-21 jdcat-dev.ir.rcos.nii.ac.jp-2022-12-29

$ grep "image:" jdcat-dev.ir.rcos.nii.ac.jp-2022-12-29/manifests/deploy-web.yaml

$kubectl apply -f jdcat-dev.ir.rcos.nii.ac.jp-2022-12-29/manifests/deploy-web.yaml


$ curl httpbin.org/ip
{
  "origin": "136.187.110.101"
}

https://github.com/RCOSDP/weko-k8s/tree/release

make a branch for WACREN
and share it.



$ pip3 list --format=columns | grep cookiecutter
cookiecutter                  1.7.3   


$ pip3 install -U cookiecutter==1.7.3

cookiecutter cookiecutter-weko-module

docker-compose -f docker-compose2.yml exec web bash
cd modules/weko-fun
pip install -e .
cd var/instance/

docker-compose -f docker-compose2.yml up -d

docker-compose -f docker-compose2.yml exec web bash
cdvirtualenv
pip install -e /code/modules/weko-fungenerator/

cdvirtualenv
vi var/instance/conf/uwsgi.ini


python setup.py init_catalog -l fr
python setup.py compile_catalog
I18N_LANGUAGES 
docker-compose -f docker-compose2.yml exec web invenio language create --active --registered "fr" "French" 000

Nigerian demo enviroment provide two reposiotries.

TODO:
- NII provides how to deploy new repository into Nigerian demo enviroment.
- One Portal 