# Changelog

## 2026-07-06

### Smoothness and Reliability Pass

- Added validation for encoding settings, API form values, Reed-Solomon parity
  settings, and parsed video headers so bad inputs fail with clear messages
  instead of low-level exceptions.
- Made generated MP4 files more browser-friendly by forcing `yuv420p` output
  and `+faststart` metadata layout for both normal encodes and stress-test
  re-encodes.
- Improved decode output handling so paths like `-o restored/` create the
  target directory and recovered filenames are sanitized before writing.
- Hardened the Flask GUI job table with locking, finished-job cleanup, safer
  file serving checks, unique decode output folders, and JSON error responses.
- Improved frontend polling/error handling so API failures display readable
  messages and progress values stay clamped to sane ranges.
- Added responsive mobile layout tweaks and a reduced-motion mode for smoother
  UI behavior on constrained devices.
- Updated `.gitignore` to keep generated output and local caches out of source
  control.

### Validation

- Python AST syntax parse across all `isg/**/*.py` files.
- `node --check isg/gui/static/app.js`.
- CLI encode/decode smoke test with `requirements.txt` as the payload.
- Flask test-client smoke check for `/` and JSON validation errors.