# Report Artifacts

This directory is reserved for committed historical evidence that is too raw
or too large to belong in an active runbook but still needs to remain in the
repository for audit context.

Use it sparingly:

- Keep fresh local logs, screenshots, traces, databases, and machine paths under
  ignored `.agent-run/` by default.
- Commit artifacts here only after confirming they contain no private paths,
  credentials, tokens, or machine-local secrets.
- Prefer dated, descriptive filenames or dated subdirectories when a report has
  multiple supporting files.
- Link each artifact from a Markdown report or README so future agents know why
  it is retained.
