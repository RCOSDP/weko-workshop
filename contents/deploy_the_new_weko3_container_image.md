# Deploy the new WEKO3 container image

## Find yaml files used for previous deployments 

```
cd /usr/local/share/deploy_logs/weko-manifests/
```

## Modify deploy-web.yaml

Manifest files are organized in the following structure.

```
 $ tree data.ir.rcos.nii.ac.jp/
data.ir.rcos.nii.ac.jp/
|-- manifests
|   |-- configmap.yaml
|   |-- deploy-web.yaml
|   |-- ingress.yaml
|   |-- instance.cfg
|   |-- secret.yaml
|   |-- service.yaml
|   |-- uwsgi.ini
|   |-- volume-pvc.yaml
|   `-- volume-pv.yaml
`-- ssl
    |-- data.ir.rcos.nii.ac.jp.crt
    `-- data.ir.rcos.nii.ac.jp.key

2 directories, 11 files
```

Rewrite the version of the following images (web, worker or nginx) in the manifest file.

```
$ egrep -A1 "name: nginx|name: web|name: worker" data.ir.rcos.nii.ac.jp/manifests/deploy-web.yaml
      - name: nginx
        image: <registry path>/nginx:v1.0.4
--
      - name: web
        image: <registry path>/web:v1.0.4
--
      - name: worker
        image: <registry path>/web:v1.0.4
```

## Apply deploy-web.yaml

Apply the modified deployment file.

```
kubectl apply -f deploy-web.yaml
```

Wait until the container image is replaced.