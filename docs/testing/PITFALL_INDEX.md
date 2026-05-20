<!-- Generated from ops/scripts/dev/sync_testing_governance_docs.py. Edit that script instead of editing this file directly. -->

# Pitfall Index

This document is the stable explainer for
[`pitfall-index.csv`](pitfall-index.csv).

## What The CSV Stores

`pitfall-index.csv` is the structured companion to the canonical Markdown
pitfall bodies, especially [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)
plus the narrower topic-route docs it now links to.

Each row records:

- `pitfall_sequence`
- `source_commit_sha`
- `document_path`
- `line`
- `heading`
- `category`
- `status`
- `notes`

## Update Rule

Update the CSV in the same change set whenever a genuinely new pitfall is added
or when canonical pitfall bodies move and the structured index must stay in
sync.

## Related Files

- [pitfall-index.csv](pitfall-index.csv)
- [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)
- [pitfalls-ledger-and-selector-tooling.md](pitfalls-ledger-and-selector-tooling.md)
