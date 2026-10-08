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

## My instance is not run by docker

Everything that runs inside a container goes through one command line,
and `WEKO_E2E_EXEC` is what that command line is.  For Kubernetes:

```
WEKO_E2E_EXEC='kubectl exec -i -n weko {service} --'
WEKO_E2E_WEB_SERVICE=deploy/weko-web
WEKO_E2E_DB_SERVICE=statefulset/postgresql
WEKO_E2E_WORKER_SERVICE=deploy/weko-worker
```

`{service}` is where the service name goes; the `WEKO_E2E_*_SERVICE`
settings hold whatever your command calls each container.  `-i` matters:
some of what the tool does is piped in on standard input.  `./e2ectl env`
says what it will use.

Where nginx, web and the worker are three containers of **one** pod --
the usual Kubernetes shape -- each setting carries its container too,
and may be more than one word:

```
WEKO_E2E_WEB_SERVICE='deploy/weko-web -c web'
WEKO_E2E_WORKER_SERVICE='deploy/weko-web -c worker'
WEKO_E2E_NGINX_SERVICE='deploy/weko-web -c nginx'
```

With it, no WEKO checkout is needed for the doctor's full 19 checks, for
`doctor --fix`, for `clean --hard`, or for the optional suites:

| Suite | Measured that way |
| --- | --- |
| (base) | 13 passed |
| `--suite ark` | 6 passed, with the stand-in (see below) |
| `--suite crossref` | 8 passed, 2 skipped -- the deposit, off without a Crossref account |
| `--suite coarnotify` | 10 passed, 4 skipped -- the web push steps need a stand-in only docker can set up |
| `--suite shibboleth` | 9 passed |

**For the `ark` suite**, `ark-stub enable` cannot help -- it writes into
a checkout's `scripts/instance.cfg`.  Where your instance settings come
from instead is your deployment's business, so the tool prints them:

```
./e2ectl ark-stub config     # prints; changes nothing
```

Apply those wherever your deployment keeps instance settings, restart the
web and worker pods, then `./e2ectl ark-stub start` runs the stand-in in
the web pod and `--suite ark` can run.

**For the Crossref deposit**, `crossref-account enable` cannot help
either, for the same reason.  `./e2ectl crossref-account config` prints
the settings; what it prints holds a password, so it belongs in a Secret
rather than a ConfigMap.  Granting a DOI needs none of this -- without a
Crossref account the suite is 8 passed and 2 skipped, as documented.

**ARK is not in every WEKO.**  `feature/nii_WACREN_crossref_doi` has it;
`release_v2.1.0` has none of the code.  Where it is absent no
configuration will make an ARK appear -- check that first.

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
[in the repository]({evidence}). A run of your own writes its record to
`e2e/evidence/` -- `run.md` (every step, what it found, the screenshots
it took), `doctor.md` and `images/` -- and that folder is what to send
back.
