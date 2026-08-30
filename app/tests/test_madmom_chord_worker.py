from scripts.madmom_chord_worker import _compatibility_shims


def test_madmom_compatibility_shims_are_idempotent() -> None:
    _compatibility_shims()
    _compatibility_shims()
