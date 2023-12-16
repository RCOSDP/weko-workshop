# Install openssh in Windows

ssh is a software application that provides a secure connection to a terminal on a remote server. It is used to access the terminal on the virtual machine. Although the UI of the virtual machine can be used, ssh will be used in this workshop to match the feel of the production environment.

Use winget to install for openssh.

```
winget install Microsoft.OpenSSH.Beta
```

Set the execution path to openssh installed via winget.

```
set PATH=C:\Program Files\OpenSSH;%PATH%
```

Check the version of ssh. If the execution path has been successfully set, the installed openssh version is displayed.

```
ssh -V
```

```
> ssh -V
OpenSSH_for_Windows_9.4p1, LibreSSL 3.7.3
```

When complete, proceed to the [next step](./install_vscode_in_windows.md).