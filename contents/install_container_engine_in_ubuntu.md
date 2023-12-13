# Ubuntu


## Set up OS

* configure virtual memory

```bash
echo "vm.max_map_count = 262144"|sudo tee -a /etc/sysctl.conf
sudo sysctl vm.max_map_count=262144
````
ref. [https://www.elastic.co/guide/en/elasticsearch/reference/current/vm-max-map-count.html](https://www.elastic.co/guide/en/elasticsearch/reference/current/vm-max-map-count.html)

## Install Docker Engine 

1. Install docker engine.

See [https://docs.docker.com/install/linux/docker-ce/ubuntu/](https://docs.docker.com/install/linux/docker-ce/ubuntu/)


```bash
sudo apt-get update
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg-agent \
    software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
   $(lsb_release -cs) \
   stable"
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io
sudo usermod -aG docker $USER

sudo systemctl start docker
sudo systemctl enable docker

exec $SHELL -l
```

2. Test the installed docker engine.

```bash
docker --version
```

result: 

```bash
$ docker --version
Docker version 20.10.6, build 370c289
```

## Install Docker-Compose

1. Install docker-compose command.

See [https://docs.docker.com/compose/install/](https://docs.docker.com/compose/install/).


```bash
sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

2. Test the installed command.

```bash
docker-compose --version
```

```bash
$ docker-compose --version
docker-compose version 1.29.2, build 5becea4c
```
