# Deploy the new WEKO3 container image

```
cd /usr/local/share/deploy_logs/weko-manifests/
```

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

```
$ egrep -A1 "name: nginx|name: web|name: worker" data.ir.rcos.nii.ac.jp/manifests/deplo
y-web.yaml
      - name: nginx
        image: <registry path>/nginx:v1.0.4
--
      - name: web
        image: <registry path>/web:v1.0.4
--
      - name: worker
        image: <registry path>/web:v1.0.4
```



```
$ kubectl exec -n weko3es -it weko-elasticsearch-0 -- curl http://localhost:9200/_cat/indices/data_ir_rcos_nii_ac_jp*
green open data_ir_rcos_nii_ac_jp-events-stats-item-create-000001   I5nXhvCbTFaDSME_UGimYA 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-stats-search-000001               JJyMbZfNSC-l47Sda5Myfg 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-stats-item-create-000001          EJDlDIozRfGyN6sUTUyy8A 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-events-stats-top-view-000001      uoJnjFThSsGafPoETsRwXA 1 1 8 0 106.5kb 53.2kb
green open data_ir_rcos_nii_ac_jp-stats-file-download-000001        AI8Q55hXRRaamlY6i9196w 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-stats-record-view-000001          kkWw6KoRR1GLKGBputYP8g 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-events-stats-celery-task-000001   mqoGm631Q-W--bc96BNntg 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-events-stats-record-view-000001   5GpZzv6SQZSj3ddfiM-eaw 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-stats-celery-task-000001          adeQDgfSRjWuikqv_C4x0w 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-authors-author-v1.0.0             HbURWvRUQce8ERx_NXND1w 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-weko-item-v1.0.0                  pfc1yi3oSTObcrVgjxZB6A 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-events-stats-file-download-000001 iyHZibrMR9alfqv-RHxQJw 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-stats-file-preview-000001         YdIf4fGyTfWvWwXOh-lhkA 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-stats-bookmarks                   HpGqTQj2RfGhmhnUbclLbQ 1 1 1 0   6.6kb  3.3kb
green open data_ir_rcos_nii_ac_jp-events-stats-search-000001        jN_7bxC0S_a4RYLLKBbQyA 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-deposits-deposit-v1.0.0           1d7Y8OZZQ5q4VbzzXRoxaw 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-events-stats-file-preview-000001  mRGQ2D1VQPS7u5M0jzEArQ 1 1 0 0    522b   261b
green open data_ir_rcos_nii_ac_jp-stats-top-view-000001             sBxMjp2TQPu5b2dq9byT9w 1 1 8 0  47.4kb 23.7kb

```


```
$ kubectl exec -n weko3es -it weko-elasticsearch-0 -- curl -XDELETE http://localhost:92
00/data_ir_rcos_nii_ac_jp*
```

kubectl exec -n weko3 -it data-ir-rcos-nii-ac-jp-web-75c64bb6b5-qtfhb -c web -- ./scripts/populate-instance.sh


