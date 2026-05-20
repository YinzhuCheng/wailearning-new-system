# CourseEval Brand Assets

This folder contains local, editable logo assets for CourseEval.

## Files

| File | Use |
|------|-----|
| `courseeval-logo.svg` | Horizontal logo / wordmark for documents, splash screens, and broad headers. |
| `courseeval-mark.svg` | Square icon mark for favicons, app icons, avatars, or compact navigation. |

## Design Notes

- Concept: an AI-assisted course book, evaluation bars, a neural guidance path,
  and a check path.
- Tone: formal, education-focused, and operational rather than decorative.
- Primary colors:
  - teal `#0F766E`
  - blue `#2563EB`
  - ink `#111827`
  - accent yellow `#FACC15`
- The small node-and-orbit motif is the AI-assist cue. It should read as
  decision support rather than autonomous replacement of teacher judgment.
- The SVGs are intentionally text/vector assets so they can be reviewed,
  versioned, recolored, or converted to PNG later without binary churn.

## Runtime Integration

- Canonical editable assets live in this folder.
- Runtime copies are checked into:
  - `apps/web/school/src/assets/brand/`
  - `apps/web/parent/src/assets/brand/`
  - `apps/web/school/public/courseeval-mark.svg`
  - `apps/web/parent/public/courseeval-mark.svg`
- The admin login page uses `courseeval-logo.svg` as the default logo unless
  `/api/settings/public` provides `system_logo`.
- The admin sidebar and parent login page use `courseeval-mark.svg` for compact
  brand placement.
- Both web app `index.html` files use the public `courseeval-mark.svg` as the
  browser tab favicon.
- When changing these assets, update the runtime copies in both SPAs and run the
  frontend build targets selected by `ops/scripts/dev/select_validation_targets.py`.
