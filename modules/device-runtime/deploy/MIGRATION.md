# Production migration gate

The module is accepted as an independent contract, but current production
behavior is intentionally unchanged.

Integration must use a dual-read migration:

1. Read the new profile store first.
2. If absent, read `harbeat_rk_base_url` and migrate it as an unverified
   endpoint candidate.
3. Verify the candidate against the stable identity obtained during pairing.
4. Persist the profile by `device_id`; retain the legacy key for one release.
5. Persist operation references only. The RK remains the owner of task state.
6. Remove full render plans from SharedPreferences only after a shadow release
   proves restart and reconnect behavior.

Do not deploy this module by copying Python files into the Flutter or RK source
tree. Implement thin Dart/RK adapters against the accepted JSON contract and
validate them independently.
