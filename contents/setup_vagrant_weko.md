# Setup vagrant-weko

Download the Vagrant file to build the WEKO3 development environment.
Go to [https://github.com/RCOSDP/vagrant-weko](https://github.com/RCOSDP/vagrant-weko) in your browser.

Next, click Code button and Download Zip link. Then start to download zipped github repository.

![pic](setup_vagrant_weko_000.png)

When complete to download, extract the downloaded package at any directory.

Next Open command prompt to build development enviroment using Vagrant. 

When opend command prompt, move the directory of extracted vagrant-weko.

Move "single" directory in the directory.

Run vagrant up command then start to build single virutual machine environment.

```
>vagrant up
Bringing machine 'default' up with 'virtualbox' provider...
==> default: Importing base box 'bento/ubuntu-20.04'...
==> default: Matching MAC address for NAT networking...
~ snip ~
```

When completed, '''vagrant status''' command, then it show running status of the virtual machine. 

```
>vagrant status
Current machine states:

default                   running (virtualbox)

The VM is running. To stop this VM, you can run `vagrant halt` to
shut it down forcefully, or you can run `vagrant suspend` to simply
suspend the virtual machine. In either case, to restart it again,
simply run `vagrant up`.
```

This completes the environment setup, and all necessary commands such as docker, docker-compose, git, etc. required to build WEKO3 are already installed.

Specific installation commands can be found at [Github permalink](https://github.com/RCOSDP/vagrant-weko/blob/5228caa98033bd511d876a3ac6d7447d49943561/single/Vagrantfile#L22-L38).

When complete, proceed to the [next step](./setup_sshconfig_in_windows.md).