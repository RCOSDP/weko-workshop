# Install visual studio code in Windowss

Install Visual Studio Code as a source code editor and SSH console. Again, use winget.

```
winget install Microsoft.VisualStudioCode
```

Install the Visual Studio Code extension for WEKO3 development.

```
code --install-extension ms-vscode-remote.remote-ssh-edit
code --install-extension ms-vscode-remote.vscode-remote-extensionpack
code --install-extension ms-vscode.remote-explorer
code --install-extension ms-vscode.remote-server
code --install-extension ms-vscode-remote.remote-ssh
code --install-extension donjayamanne.python-environment-manager
code --install-extension donjayamanne.python-extension-pack

```

When complete, proceed to the [next step](./setup_vagrant_weko.md).