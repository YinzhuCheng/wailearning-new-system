# Documentation Assets

This directory stores committed assets that are referenced by repository
documentation.

Use this directory for:

- small brand or diagram assets that documentation links to directly;
- stable visual references that are safe to commit and not generated during a
  local run.

Do not put screenshots, Playwright traces, local uploads, generated reports, or
machine-local evidence here. Those belong under ignored `.agent-run/` unless a
human explicitly promotes a scrubbed artifact into a committed report.

Subdirectories:

- [brand/](brand/)
