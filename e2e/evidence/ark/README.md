# E2E test run report: the `ark` suite

日本語版: [`README.ja.md`](README.ja.md) ·
the run this belongs to: [`../README.md`](../README.md)

An ARK is minted for the item and becomes its permalink. WEKO mints it when
the Item Registration action completes, by calling an ARK server, and only
when the instance is configured for it.

The suite is [`../../tests/test_ark_mint.py`](../../tests/test_ark_mint.py);
the screenshots below are in [`images/`](images), taken by the steps
themselves as they went.

| | |
| --- | --- |
| Run id | `20260930-005832` |
| Result | **6 passed** |
| Asked for with | `--suite ark`, with `WEKO_E2E_ARK_NAAN=99999` |

---

Run against the stand-in ARK server -- `e2ectl ark-stub enable` -- because
this instance has no ARK server of its own. The same suite run against a
real one, configured with `e2ectl ark-account enable`, is in the
["Other environments" table of the run](../README.md#other-environments).

### Register an item, granting no DOI (test_03)

The ARK is minted on the way through, when Item Registration completes,
so nothing on screen asks for one.

![The approval screen of the ARK run](images/02-approval.png)

![After approval](images/03-approved.png)

### The item carries an ARK (test_04, test_05)

The permalink of an item with no DOI and no CNRI is its ARK, so the
record page is where a minted ARK shows up -- here `ark:/99999/fk400002`,
under the NAAN this environment was configured for.

![The record page, showing the ARK as its permalink](images/04-record-page.png)
