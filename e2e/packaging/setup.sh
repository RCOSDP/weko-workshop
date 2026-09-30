#!/bin/sh
# Set the test suite up: a Python environment of its own, and the
# browser it drives.  Run this once, from the directory it is in.
set -e
cd "$(dirname "$0")"

# Which python?  Not every system has one called python3 -- and an alias
# for it would not help, because a shell does not expand aliases in a
# script.  So look for one here.  WEKO_E2E_PYTHON names one outright,
# and is then the one used or the reason for stopping: falling back to
# something else after being told which to use would be worse than
# saying so.
need="3.10"
new_enough='import sys; raise SystemExit(sys.version_info < (3, 10))'

if [ -n "$WEKO_E2E_PYTHON" ]; then
    if ! command -v "$WEKO_E2E_PYTHON" >/dev/null 2>&1; then
        echo "WEKO_E2E_PYTHON names $WEKO_E2E_PYTHON, which is not there." >&2
        exit 1
    fi
    if ! "$WEKO_E2E_PYTHON" -c "$new_enough" 2>/dev/null; then
        echo "WEKO_E2E_PYTHON names $WEKO_E2E_PYTHON, which is" >&2
        echo "$("$WEKO_E2E_PYTHON" --version 2>&1); $need or newer" >&2
        echo "is needed." >&2
        exit 1
    fi
    python=$WEKO_E2E_PYTHON
else
    for candidate in python3 python \
                     python3.13 python3.12 python3.11 python3.10; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if "$candidate" -c "$new_enough" 2>/dev/null; then
            python=$candidate
            break
        fi
    done
fi

if [ -z "$python" ]; then
    echo "No Python $need or newer was found." >&2
    echo >&2
    echo "Tried: python3, python, and python3.13 down to python3.10." >&2
    echo "If yours is called something else, or is somewhere not on" >&2
    echo "PATH, name it:" >&2
    echo >&2
    echo "    WEKO_E2E_PYTHON=/usr/local/bin/python3.12 ./setup.sh" >&2
    echo >&2
    echo "$need is what the playwright and pytest in requirements.txt" >&2
    echo "ask for; the suite's own code is not what needs it." >&2
    exit 1
fi

echo "Using $python ($("$python" --version 2>&1))"
"$python" -m venv .venv-e2e
.venv-e2e/bin/pip install --upgrade pip
.venv-e2e/bin/pip install -r e2e/requirements.txt
.venv-e2e/bin/playwright install chromium
echo
echo "Ready.  Now:"
echo "    cd e2e"
echo "    ../.venv-e2e/bin/python ./e2ectl env     # what a run would use"
echo "    ../.venv-e2e/bin/python ./e2ectl ping    # can it reach the instance"
echo "    ../.venv-e2e/bin/python ./e2ectl doctor  # is it fit to test"
echo "    ../.venv-e2e/bin/python -m pytest        # run the base flow"
