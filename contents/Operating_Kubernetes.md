Change k8s Image

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
