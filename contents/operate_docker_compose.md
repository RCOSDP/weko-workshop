# Operate docker-compose

## Create and start containers

```
docker-compose up -d
```

Use the "-f" option to execute commands specifying a configuration file.

```
docker-compose -f docker-compose2.yml up -d
```

## Stop and remove containers, networks

```
docker-compose down
```

Use the "-f" option to execute commands specifying a configuration file.

```
docker-compose -f docker-compose2.yml down
```

If you want to delete the volume together, add the "-v" option.

```
docker-compose -f docker-compose2.yml down -v
```

## Start containers

```
docker-compose start
```

Use the "-f" option to execute commands specifying a configuration file.

```
docker-compose -f docker-compose2.yml start
```

## Stop containers

```
docker-compose stop
```

Use the "-f" option to execute commands specifying a configuration file.

```
docker-compose -f docker-compose2.yml stop
```

## Restart containers

```
docker-compose restart
```

Use the "-f" option to execute commands specifying a configuration file.

```
docker-compose -f docker-compose2.yml restart
```

## List containers

```
docker-compose ps
```

Use the "-f" option to execute commands specifying a configuration file.

```
docker-compose -f docker-compose2.yml ps
```

## Show container log

```
docker-compose logs -f
```

Use the "-f" option to execute commands specifying a configuration file.

```
docker-compose -f docker-compose2.yml logs -f
```

To check the logs for a specific container, specify the container name.

```
docker-compose -f docker-compose2.yml logs -f web
```

## execute command in container

```
docker-compose exec <container_name> bash
```

Use the "-f" option to execute commands specifying a configuration file.

```
docker-compose -f docker-compose2.yml exec <container_name> bash
```


