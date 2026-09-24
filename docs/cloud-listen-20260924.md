# HarBeat public player deployment

Target entry: `https://8.136.120.255/listen/`.

The public player is a static React/Web Audio application. Its index, per-song
metadata, native audio segments, transition-entry audio and clock worklet are
served directly from ECS by Nginx. Playback requests do not use the local preview
server, the analysis API or the NAS. Analysis and source music remain on the
existing processing system; only generation of new releases needs that system.

## Source and processing contract

- Published source index: 157 songs (EDM 8, KPOP 84, 音乐风格参考曲库 65).
- The updated source audit permits 152 songs for mixing. Five retain complete
  native playback but have genuine tempo/beat-grid conflicts: In the Name of
  Love, CHEER UP (Korean Ver.), Sample, Victory Lap Five and Come Up.
- Source master SHA-256 is rechecked after each transfer to ECS. Original reports
  and manifests are never modified.
- Runtime section tails may be clipped by at most 1 ms to account for the report's
  millisecond precision. A separated stem ending less than one 44.1 kHz sample
  early limits the alignment calculation to its measured coverage. Larger
  discrepancies continue to fail the original validation.
- Stereo 44.1 and 48 kHz sources are supported. Tests compare concatenated native
  output, including segment boundaries, with a direct FFmpeg resample.
- Native playback uses 30-second segments from the beginning. The existing
  150-second entry-search scope, accepted atempo entry recipe, vocal-overlap
  scoring and full progressive handoff remain unchanged.
- Audio activation begins synchronously in the play gesture, before network or
  worklet waits. See [MDN's Web Audio guidance](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Best_practices).

## Release layout

On ECS, `/srv/harbeat-listen/` contains:

| Path | Purpose |
| --- | --- |
| `processor/` | Small isolated processing code package |
| `venv/` | Dependencies from `requirements-listen.txt` |
| `library/` | Generated source-bound metadata, recipes and FLAC assets |
| `registry/` | Private generated-media registry; never exposed by Nginx |
| `media/` | Verified content-addressed hardlinks; immutable public audio |
| `releases/<release>/` | Built application and complete public metadata |
| `current` | Symlink to the active complete release |
| `deploy-20260924/` | Private task inputs, logs, manifests and verification records |

The HTTPS snippet is `deploy/analysis-platform/aliyun-listen.conf`. Only
`/listen` and `/listen/` are added to the existing server. Existing routes remain
configured independently. The host already has a trusted Let's Encrypt IP
certificate and a renewal timer; no new cloud resource purchase is required.

## Rebuild and publish

1. Export bound jobs with `build_continuous_library.py --export-jobs` from the
   processing host's published index/reports. Any skipped source-hash pass is
   followed by mandatory full source hashing after transfer to ECS.
2. Run `render_continuous_cloud.py` on ECS with two workers. It fetches one source
   per worker, verifies the hash, renders locally, then releases the temporary
   source copy. Completed detail files carry a preparation identity for resume.
3. Require 157 playable songs, every source-eligible song to remain mix-ready,
   and zero rendering failures. Keep at least 5 GiB disk reserve before starting
   another track.
4. Run `package_continuous_site.py package` with the library, registry and an
   output directory inside the new release. Its private manifest must be placed
   outside the public release. The exporter changes delivery URLs only and
   deduplicates assets by SHA-256.
5. Run the verifier against cloud-local files, then create hardlinks in `media/`.
   No second audio copy is needed. All public audio uses `/listen/media/<sha>.flac`.
6. Build `web` with `npm run build:continuous`; copy `continuous.html` as
   `index.html` and include `v3-clock.js`. Verify the complete release before
   switching the `current` symlink.
7. Back up the existing HTTPS configuration, include the listen snippet, run
   `nginx -t`, then reload. Validate HTTPS, GET/HEAD, range requests and browser
   playback before declaring the release available.

## Rollback and acceptance

Switch `current` back to a previously verified release to roll back the player.
For the first publication, restore the saved HTTPS configuration and reload
Nginx after a successful syntax check. Keep public content-addressed audio until
no retained release references it.

Acceptance covers desktop and mobile viewport layout, complete inventory,
start/pause/resume, volume, seeking over multiple native boundaries, a real
vocal-overlap handoff, and a third song selected during the handoff. Browser
tests must validate TLS normally and must not disable autoplay requirements.
Functional acceptance is separate from a 500-concurrent-user capacity test.

## Published release and verification

- Active release: `/srv/harbeat-listen/releases/20260924-2`. Release `20260924-1`
  remains available for rollback. The second release fixes a user selecting the
  next song while an asynchronous seek is still fetching its new native segment;
  that selection must not cancel the seek and leave no current song.
- 157 playable tracks, 152 mix-ready, zero render failures. All 45,481 unique
  media files were hashed after rendering: 41,156,053,542 bytes in total.
- HTTPS was checked without a certificate bypass. HTML, compressed metadata,
  worklet and FLAC returned successfully; a 64-byte range returned HTTP 206.
  The existing vocal-overlap experiment still returned HTTP 200.
- Chromium checks covered all three collections, pause/resume, volume, seeking
  over 30-second and later segment boundaries, a real vocal-overlap/dynamic-EQ
  handoff, and selecting/preparing a third track during the handoff. No page exceptions or
  failed application/media responses occurred. Desktop and 390-pixel mobile
  viewports showed no horizontal overflow. These are browser automation checks,
  not a physical iPhone or WeChat acceptance test.
- Automated checks: full web suite 252 passed / 12 skipped (optional external
  fixtures); the final frontend fix passed 59 relevant tests and a production
  build. Library/exporter tests passed 22, and phrase-alignment/vocal-corpus tests
  passed 48. The 48 kHz test compares complete native output sample-for-sample.
- ECS has about 6.5 GiB free after publication (94% disk utilization). Expand
  storage before another large corpus build. Only unused Docker build cache was
  reclaimed; existing service data, images and volumes were preserved.

`scripts/smoke_public_continuous.cjs` repeats the public browser checks. It needs
Node and Playwright with Chromium. `HARBEAT_PUBLIC_URL` and `HARBEAT_QA_OUT`
override the target and local evidence directory; `PLAYWRIGHT_MODULE` and
`CHROMIUM_EXECUTABLE_PATH` can point at an existing runtime. Run it with
`node scripts/smoke_public_continuous.cjs`. It deliberately uses normal TLS and
browser autoplay restrictions.

The UI refinement proposal is awaiting the user's design response. Existing
continuous-player presentation remains the visual baseline until then.
