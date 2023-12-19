Change k8s Imgge
/home/vagrant/weko/Dockerfile
# RUN mv /home/invenio/.virtualenvs/invenio/var/instance/static /home/invenio/.virtualenvs/invenio/var/instance/static.org
↓
RUN mv /home/invenio/.virtualenvs/invenio/var/instance/static /home/invenio/.virtualenvs/invenio/var/instance/static.org

build k8s Image
docker-compose build web
docker-compose build nginx

Put tag k8s Image
docker tag weko-web:latest  nrt.ocir.io/nrbslpthdcco/at/ng/web:latest
docker tag weko-nginx:latest nrt.ocir.io/nrbslpthdcco/at/ng/nginx:latest

make config.json to registrate Oracle Cloud
/home/vagrant/.docker/config.json
{
	"auths": {
		"nrt.ocir.io": {
			"auth": "**********"
		}
	}
}

