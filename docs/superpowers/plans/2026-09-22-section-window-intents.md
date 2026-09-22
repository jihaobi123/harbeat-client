# Section/window intent implementation plan

User approved this design on 2026-09-22; execute inline using writing-plans, executing-plans and test-driven-development. No additional design approval needed.

Goal: preserve original reports and V3 DSP; add traceable local evidence and jointly constrain style, acoustic energy and executable transition windows.
Architecture: additive, hash-bound profiles generated from DJ 50ms measurements and interval-specific Discogs inference. Realtime planner evaluates each actual A start, B takeover and four subsequent 4s blocks. Original reports and existing rendered assets remain unchanged.
Tech: Python standard library / existing EffNet worker, TypeScript / React / Vitest.

- [x] Add tests in tests/test_mix_profiles.py: gaps and duplicated measurement frames must not appear as full coverage; 30s style blocks cannot confirm a short intro; hash mismatches fail; short intervals pending; null samples remain unknown.
- [x] Implement analysis_platform/mix_profiles.py with versioned units, source SHA/report ID, section and window support, relative-energy preservation, absolute power aggregation (linear domain), 16s takeover blocks. Add optional interval requests to model_worker via validated, bounded windows. Keep default 30s path unchanged.
- [x] Add scripts/build_mix_profiles.py: read catalog and reports, optionally infer exact intervals on Jetson, atomically write additive catalog/sidecars. No source report mutation. Reuse embedding cache and original audio identities.
- [x] Add web/src/realtime/evidence.test.ts and implement evidence.ts. Candidate-specific A 4s before actual mix start; B four 4s blocks after takeover; 1dB direction in every block, 6dB maximum jump. These are acoustic-energy pilot rules, not a trained perception model. Missing measurements fail closed for energy requests. Local style uses >=8s direct support, >=.10 top score and >=.015 margin (experimental rules, not confidence probability).
- [x] Extend planner Intent with simultaneous style and energy direction, preserve V3 timing/voice/EQ/score. Report exclusions and full evaluated evidence. Normal next works with legacy catalogs; style/energy cannot silently fall back to whole-song labels or relative curves.
- [x] Add UI joint controls, pre-listening section/window evidence and per-request reasons. Update exported decision records; keep DSP untouched.
- [x] Run Python, planner, transport and UI tests; typecheck/build. Generate real six-track profiles on Jetson; audit candidate acceptance/rejection and SHA preservation.
- [x] Deploy separate versioned preview preserving previous page/media; browser verify and document exact results and remaining uncertainty. Commit implementation and validation record.

Deployment HTTP and source checks completed. Browser navigation tool timed out; actual browser playback acceptance remains explicitly unverified (see validation record).
