# Metric mix cloud release

Published 2026-10-20 at `https://8.136.120.255/listen/smart/`.
Rules: `/listen/smart/standards.html`. See `docs/metric-mix-standards-20261020.md` for thresholds, formulas and limitations.

## Layout

- Cloud root: `/srv/harbeat-listen/metric-mix`.
- `code` and `web` symlinks point into `releases/v1-b42d5d5a488d-r2`.
- Isolated venv; pinned dependencies in `requirements.txt`.
- systemd service listens only at `127.0.0.1:8791`, one worker, three bounded outstanding jobs.
- Nginx includes `harbeat-metric-mix.conf` from the existing listening snippet. The HTTP-level rate zones are in `00-harbeat-metric-mix-limit.conf`.
- `state`, `media`, `private`, and `staging` are disposable service data. Only whitelisted WAV paths are served as media. Diagnostics are private.
- Jetson worker: `/home/mark/harbeat-metric-mix/metric_mix`; interpreter `/home/mark/harbeat-analysis-venv/bin/python`. Cloud uses its existing SSH identity to reach the worker. NAS inputs remain read-only.
- NAS roots: `/mnt/nas/harbeat/preprocess` and `/mnt/nas/harbeat/data/analysis-platform/reports`.

## Build and release

From `web`, run TypeScript checking and the separate Vite entry:

```sh
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/vite build --config vite.metric-mix.config.ts
```

Package `metric_mix`, `deploy/metric-mix`, `web/dist-metric-mix` and the standards Markdown. Exclude `__pycache__`, dot metadata files and `._*`. Upload into a new release directory, preserving earlier releases. Install pinned requirements in the isolated venv when they change. Deploy identical Python modules on Jetson and cloud; the worker code fingerprint must match. Atomically switch both symlinks, then restart only `harbeat-metric-mix.service`.

Install the supplied systemd unit, Nginx rate-zone file and route snippet into their corresponding `/etc` paths. Append exactly one `include /etc/nginx/snippets/harbeat-metric-mix.conf;` to the existing listening snippet. Run `nginx -t` before reloading Nginx. Do not replace the existing player or its service.

Use `deploy/analysis-platform/ssh.config` from the workspace root for the existing `harbeat-cloud` and `harbeat-jetson` aliases. Keep the relative config path because its absolute path contains spaces and breaks the current ProxyJump expansion.

## Acceptance

```sh
python3 -m unittest tests.test_metric_mix tests.test_metric_gateway
```

From `web`:

```sh
./node_modules/.bin/vitest run src/metric-mix/plan.test.ts src/metric-mix/transport.test.ts src/continuous/segments.test.ts src/continuous/activation.test.ts src/realtime/cache.test.ts
```

Check service health, loopback binding, old player and standards HTTP responses, exact-Origin enforcement, 8KB body limit, rate limiting and hidden private-result paths. Prepare a real source-bound pair through the public UI. Audition original, a single method and the combination when eligible; export the session before stopping. Confirm audio observation markers and correct native B source continuation. Check phone-width controls and export. Browser render-quantum timing is not physical output latency.

Current release passed 17 Python and 24 TypeScript tests. Real public playback completed original, filter and bass/filter handoffs. A 390×844 viewport had no document overflow; primary buttons were at least48px tall. Physical phone, Safari, background/lock-screen and Bluetooth acceptance remain pending.

## Rollback

For a previous compatible metric release, atomically restore `code` and `web` to its retained directories; restore matching worker modules, then restart the metric service. Never pair a new gateway with an old worker fingerprint.

To remove this feature, first back up the current Nginx listening snippet. Remove only its metric include line, run `nginx -t`, reload Nginx, then stop/disable `harbeat-metric-mix.service`. The original `/listen/` uses its existing route and service. Keep release files and state for inspection; do not delete NAS or public library sources. The initial listening snippet is also saved under `deploy-backup/harbeat-listen.conf.before`, but restoring that whole file could overwrite later unrelated changes.
