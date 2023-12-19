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


# connec to OCI

bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)"



$ oci setup config
    This command provides a walkthrough of creating a valid CLI config file.

    The following links explain where to find the information required by this
    script:

    User API Signing Key, OCID and Tenancy OCID:

        https://docs.cloud.oracle.com/Content/API/Concepts/apisigningkey.htm#Other

    Region:

        https://docs.cloud.oracle.com/Content/General/Concepts/regions.htm

    General config documentation:

        https://docs.cloud.oracle.com/Content/API/Concepts/sdkconfig.htm


Enter a location for your config [/home/wacren/.oci/config]:

Enter a user OCID: ocid1.user.oc1..aaaaaaaanoqccuphwaozgqqddvgpdmgmfr45pgj3zak2b2f5jh24ilbqzckq
Enter a tenancy OCID:  ocid1.tenancy.oc1..aaaaaaaax227cmubyqyxwqtcymi4axwodotvgopepfxnx5wxcfnjme4vf6pa
Error: Invalid OCID format. Instructions to find OCIDs: https://docs.cloud.oracle.com/Content/API/Concepts/apisigningkey.htm#Other
Enter a tenancy OCID: ocid1.tenancy.oc1..aaaaaaaax227cmubyqyxwqtcymi4axwodotvgopepfxnx5wxcfnjme4vf6pa
Enter a region by index or name(e.g.
1: af-johannesburg-1, 2: ap-chiyoda-1, 3: ap-chuncheon-1, 4: ap-dcc-canberra-1, 5: ap-hyderabad-1,
6: ap-ibaraki-1, 7: ap-melbourne-1, 8: ap-mumbai-1, 9: ap-osaka-1, 10: ap-seoul-1,
11: ap-singapore-1, 12: ap-sydney-1, 13: ap-tokyo-1, 14: ca-montreal-1, 15: ca-toronto-1,
16: eu-amsterdam-1, 17: eu-dcc-dublin-1, 18: eu-dcc-dublin-2, 19: eu-dcc-milan-1, 20: eu-dcc-milan-2,
21: eu-dcc-rating-1, 22: eu-dcc-rating-2, 23: eu-frankfurt-1, 24: eu-madrid-1, 25: eu-marseille-1,
26: eu-milan-1, 27: eu-paris-1, 28: eu-stockholm-1, 29: eu-zurich-1, 30: il-jerusalem-1,
31: me-abudhabi-1, 32: me-dcc-muscat-1, 33: me-dubai-1, 34: me-jeddah-1, 35: mx-queretaro-1,
36: sa-santiago-1, 37: sa-saopaulo-1, 38: sa-vinhedo-1, 39: uk-cardiff-1, 40: uk-gov-cardiff-1,
41: uk-gov-london-1, 42: uk-london-1, 43: us-ashburn-1, 44: us-chicago-1, 45: us-gov-ashburn-1,
46: us-gov-chicago-1, 47: us-gov-phoenix-1, 48: us-langley-1, 49: us-luke-1, 50: us-phoenix-1,
51: us-sanjose-1): 13
Do you want to generate a new API Signing RSA key pair? (If you decline you will be asked to supply the path to an existing key.) [Y/n]: n
Enter the location of your API Signing private key file:

Enter the location of your API Signing private key file: /home/wacren/.oci/oci_api_key.pem
Fingerprint: 5d:43:c5:5c:df:3f:12:29:46:c3:3c:9c:95:31:bc:9e
Config written to /home/wacren/.oci/config


    If you haven't already uploaded your API Signing public key through the
    console, follow the instructions on the page linked below in the section
    'How to upload the public key':

        https://docs.cloud.oracle.com/Content/API/Concepts/apisigningkey.htm#How2



oci bastion session create-managed-ssh --profile DEFAULT --bastion-id ocid1.bastion.oc1.ap-tokyo-1.amaaaaaa43y3wuialkyd4p27uaoivoeqivfiuqph3ymf6dbapaq4nutiaifa --display-name wacren --key-type PUB --ssh-public-key-file /home/mhaya/.ssh/key.pub  --target-os-username wacren --session-ttl 10800 --target-resource-id ocid1.instance.oc1.ap-tokyo-1.anxhiljr43y3wuiccihdrwym4mx4cdxagz3sq7xqgliwjudvvftbqqp6oaga

ssh -i ~/.ssh/oci/id_rsa -o ProxyCommand="ssh -i ~/.ssh/oci/id_rsa -W %h:%p -p 22 ${bastion_id}@host.bastion.ap-tokyo-1.oci.oraclecloud.com" -p 22 mhaya@${ip}



