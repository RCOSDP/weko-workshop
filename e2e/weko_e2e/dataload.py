"""Take the rows out of a dump, and leave the rest of it alone.

``install.sh`` loads the data an instance starts with from files under
``scripts/demo``.  Some of them are dumps rather than seeds:
``item_type.sql`` drops the item type tables and builds them again before
filling them, which is right for an empty database and wrong for
somebody's instance -- it would take the item types they had made with
it.

So a repair does not run those files.  It reads the statements that only
*add* rows out of them and runs those, which leaves every table, every
constraint and every row that was already there exactly as it was.

Two kinds of statement are kept:

``INSERT INTO ...``
    as written.  They carry the ids they insert, so where one of those
    ids is already in use the insert fails -- and because the whole lot
    is run in one transaction, a failure leaves the instance untouched
    rather than half loaded.

``SELECT pg_catalog.setval(...)``
    rewritten to move the sequence *forward only*.  A dump sets a
    sequence to where the dump ended; replaying that on an instance which
    has gone further would hand out ids it has already used.

The rows do not come in parent-before-child order -- the file they came
from has no constraints in place while it loads them, and puts them back
at the end -- so the load turns foreign key checking off for its own
transaction rather than reordering them.  See :data:`WITHOUT_FK_CHECKS`.
"""

import re

INSERT = 'INSERT INTO '
"""What a statement that only adds rows begins with."""

WITHOUT_FK_CHECKS = 'SET session_replication_role = replica;'
"""Put the foreign keys aside for this transaction, not for the schema.

The rows are listed in the order ``pg_dump`` wrote them, which is not
the order the foreign keys want them in: the file they came from drops
every constraint before loading and adds them back afterwards.  Only the
rows are being taken here, so instead the checks are switched off for
the one transaction -- what ``pg_restore --disable-triggers`` does -- and
the constraints themselves are never touched.

Primary keys and unique constraints are not triggers and still apply,
which is what stops a load from landing on top of rows already there.
"""

SETVAL = re.compile(
    r"^SELECT\s+pg_catalog\.setval\(\s*'([^']+)'\s*,\s*(\d+)\s*,"
    r"\s*(?:true|false)\s*\)\s*;$")
"""A dump's way of putting a sequence back where it found it."""


def forward_setval(sequence, floor):
    """Return a setval that can only move a sequence forward.

    :param sequence: the sequence's name, as the dump spells it
    :param floor: where the dump would have put it
    """
    return (
        "SELECT setval('{0}', GREATEST("
        "(SELECT last_value FROM {0}), {1}), true);".format(sequence, floor))


def data_only(text):
    """Return the statements of a dump that add rows, and nothing else.

    Everything else -- ``DROP``, ``CREATE``, ``ALTER``, the ``SET``s a
    dump opens with -- is left out, so what the statements meet is the
    schema the instance already has.

    :param text: the dump, as read from the file
    :return: list of statements, in the order the dump had them
    """
    kept = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(INSERT):
            kept.append(line)
            continue
        match = SETVAL.match(line)
        if match:
            kept.append(forward_setval(match.group(1), int(match.group(2))))
    return kept


def load_script(statements):
    """Return the SQL that adds a dump's rows and nothing else.

    Meant to be run in one transaction -- ``psql --single-transaction``
    -- so that a row the instance refuses undoes the whole load and the
    foreign keys are back on however it ends.
    """
    return '\n'.join([WITHOUT_FK_CHECKS] + list(statements))


def describe(statements):
    """Return what a set of statements would add, as ``{table: rows}``.

    Used to say what a repair is about to do before it does it.
    """
    counted = {}
    for statement in statements:
        if not statement.startswith(INSERT):
            continue
        # A dump writes either "INSERT INTO t VALUES" or
        # "INSERT INTO t(col, ...) VALUES".
        table = statement[len(INSERT):].split()[0].split('(')[0]
        counted[table] = counted.get(table, 0) + 1
    return counted
