# WEKO3 end to end tests

An end to end test suite for a WEKO3 instance, and the tool that looks
one over and puts right what it can.  Taken from
<https://github.com/RCOSDP/weko-workshop>, built {when} from {revision}.

## Set it up

**Linux and macOS**

```
./setup.sh
```

**Windows, in PowerShell**

```
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

`setup.sh` is a shell script and PowerShell has no shell to run it with,
which is why there are two. The `-ExecutionPolicy` is because Windows
refuses unsigned scripts by default; it applies to that one call and
changes nothing about the machine.

Either makes `.venv-e2e/` beside this file and installs chromium into it,
and each finds a Python for itself -- `python3`, `python` and the
versioned names on Linux, the `py -3` launcher first on Windows. An
*alias* for `python3` would not have helped on Linux: a shell does not
expand aliases inside a script. If yours is somewhere unusual, name it:

```
WEKO_E2E_PYTHON=/usr/local/bin/python3.12 ./setup.sh
```

```
$env:WEKO_E2E_PYTHON = 'C:\Python312\python.exe'
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Python 3.10 or newer, which is what the playwright and pytest in
`requirements.txt` ask for -- the suite's own code is not what needs it.
And enough disk for the browser.

## Run it

```
cd e2e
../.venv-e2e/bin/python ./e2ectl env      # what a run would use
../.venv-e2e/bin/python ./e2ectl ping     # can it reach the instance
../.venv-e2e/bin/python -m pytest         # the base flow, about two minutes
```

On Windows a virtual environment keeps its programs in `Scripts` rather
than in `bin`, and `e2ectl` is handed to the interpreter rather than run
as a program, so the same three are:

```
cd e2e
..\.venv-e2e\Scripts\python .\e2ectl env
..\.venv-e2e\Scripts\python .\e2ectl ping
..\.venv-e2e\Scripts\python -m pytest
```

That is the whole of the difference. Everything the suite itself does --
the browser, the HTTP, the tool -- is the same on either.

Nothing about the instance is built in.  It runs against whatever you
point it at -- `WEKO_BASE_URL`, `WEKO_TEST_EMAIL`, `WEKO_TEST_PASSWORD`,
or an environment file copied from `e2e/environments/`.

**A WEKO checkout is not needed.** The tests reach the instance over HTTP
and through a browser. A checkout of WEKO that owns the compose file is
wanted only for the parts that run inside the containers -- the physical
clean-up, the stand-in servers, and eleven of the doctor's checks -- and
each of those says so and steps aside when there is none.

## Is my instance fit to be tested?

```
cd e2e
../.venv-e2e/bin/python ./e2ectl doctor         # what is wrong, if anything
../.venv-e2e/bin/python ./e2ectl doctor --fix   # put right what can be
```

Looking changes nothing.  Every repair *adds* what is missing and
replaces nothing, and nothing here deletes: what could only be put right
by removing something is reported and left alone.

## My instance is somewhere else

`--fix` works through `docker compose`, so it is no use for an instance
you cannot reach the containers of.  `--sql` writes the same repairs out
instead, to be handed to whoever can run SQL on it:

```
WEKO_E2E_WEKO_REF=release_v2.1.0 ../.venv-e2e/bin/python ./e2ectl doctor --sql > repair.sql
```

The reading of the instance goes to stderr and the script to stdout, so
that is a file which can be run rather than one that has to be edited
first.  One transaction, rows added and nothing else, and a row whose id
is already in use undoes the whole of it.

**The version matters.**  The rows are WEKO's own data, and an instance
built from an older WEKO wants that WEKO's -- between `v2.0.3` and
`release_v2.1.0` the shipped item types go from 173 rows to 210.
`WEKO_E2E_WEKO_REF` is the branch, tag or commit to take them from; they
are fetched from GitHub over HTTP, nothing is cloned, and what is fetched
is kept so the second time needs no network.

If this package was built after `e2ectl seed`, it already carries the
versions that were taken, and `--sql` works with no network at all.
`./e2ectl seed --list` says which.

## The rest

[`e2e/README.md`](e2e/README.md) is the whole of it -- every setting,
each optional suite, cleaning up, deriving a suite of your own, and what
to do when it does not work.  [`e2e/README.ja.md`](e2e/README.ja.md) is
the same in Japanese.

This package does not carry the screenshots of a run; they are
[in the repository]({evidence}).
