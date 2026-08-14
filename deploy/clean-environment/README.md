# HarBeat clean environment deployment

This directory defines the clean deployment platform. It never imports old
virtual environments, service units, caches, or source directories.

Quick local validation:

```powershell
py deploy/clean-environment/harbeatctl.py validate
py -m unittest discover deploy/clean-environment/tests -v
```

Linux target layout is described in
`docs/clean_environment_modular_deployment_execution_plan_20260814.md`.

Current execution evidence:

- Stage D shadow parity: `docs/stage_d_old_vs_clean_shadow_acceptance_20260814.md`
- Stage E contract and switch gate: `docs/stage_e_mobile_rk_contract_and_switch_plan_20260814.md`

Stage E is in progress. Production cutover and old-environment cleanup are not
authorized.
