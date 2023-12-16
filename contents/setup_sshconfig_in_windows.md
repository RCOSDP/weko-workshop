# Setup ssh config

Next, configure the settings for ssh connections to the virtual machine environment you have created.


First, run ''' vagrant ssh-config ''' to output the ssh configuration.

```
>vagrant ssh-config
Host default
  HostName 127.0.0.1
  User vagrant
  Port 2222
  UserKnownHostsFile /dev/null
  StrictHostKeyChecking no
  PasswordAuthentication no
  IdentityFile <path to private key file>
  IdentitiesOnly yes
  LogLevel FATAL
```

Next, copy the ssh configuration and move home directory.

```
cd %HOMEDRIVE%%HOMEPATH%
```

Open or create new config file of ssh client.

```
>code .ssh\config
```

And paste the ssh configuration which is copied from vagrant command.

![pic](setup_vagrant_weko_001.png)

Change HOST name from default to single or you like name.

You are now ready to connect to the virtual machine via ssh. The next step is to [build WEKO3](./build_weko3.md).

