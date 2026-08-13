# Baseline Recovery

The actual baseline archives are deliberately excluded from Git. Restore them
from the controlled local/offline backup location and verify every SHA256 in
`deployment-baseline-20260813.json` before use.

## Scope

- Mobile: installed APK plus a private SharedPreferences export.
- Jetson: deployed source and non-secret configuration only.
- RK3588: deployed source, tests, service templates, and non-secret examples.

Music, stems, renders, databases, model weights, caches, logs, credentials, and
virtual environments require their own external-asset manifests. This baseline
does not claim those assets are backed up or suitable for Git.

## Recovery Rule

Never extract over a running production directory. Extract into a new release
directory, validate hashes and imports, run the module health checks, then
switch the service symlink. The current production directories remain untouched
until fresh-clone and rollback acceptance have passed.
