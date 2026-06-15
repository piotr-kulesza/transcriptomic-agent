# Regression harness

A deterministic, no-LLM regression suite for the Layer-1 engine. Tests that
the per-comparison `meta_gsea` and `cross_dataset_de` results still recover
known biology on the 14-DEG endometriosis fixture.

The endometriosis data is a **test fixture**, not engine logic. Engine code
remains disease-agnostic.

## Running

```bash
source .venv/bin/activate
pytest eval/
```

Runs in <10 s on a laptop. No API key needed.

## Fixtures

`eval/fixtures/deg/` contains the 14 limma/DESeq2 DEG tables, slimmed to
`gene, logFC, p, adj_p, ci_l, ci_r, se` and gzipped (~5 MB total).

Rebuild from source with:

```bash
python eval/fixtures/build_fixtures.py
```

Defaults to `/Users/piotr/Documents/R_projects/meta/data_subtypes_new`;
override with `EVAL_DEG_SOURCE_DIR=/path/to/source`.

`validation/ground_truth_parsed.txt` holds the manual fgsea/enrichR
ground truth used to derive the direction assertions in
`test_layer1_recovery.py`.

## Assertion set

Hallmark-collection `meta_gsea` direction calls for the three lesion-vs-EH
contrasts, plus `cross_dataset_de` direction consistency and `meta_rank`
orientation symmetry. The hallmark assertions encode:

- OE vs EH: complement UP, IFN-γ UP, E2F/G2M DOWN, estrogen-late DOWN
- PE vs EH: allograft rejection / inflammatory response UP; MYC / OXPHOS /
  E2F / G2M DOWN
- DIE vs EH: E2F_TARGETS DOWN

Any change that flips a direction or drops a known signal fails the suite.

## Canary tests

`eval/test_canary.py` deepcopies the fixture, sign-flips every logFC for OE
vs EH, and asserts the previously-confirmed signals now point the wrong way.
This is the "test the test" check from the tier-1 design — proof the suite
would catch the direction-flip bug it was built for.
