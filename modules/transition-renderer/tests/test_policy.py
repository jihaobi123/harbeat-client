import pytest

from harbeat_transition_renderer.policy import (
    AUTOMATIC_RENDERER_VERSION,
    FAST_CUT_RENDERER_VERSION,
    RendererKind,
    resolve_renderer_policy,
)


def test_resolves_both_registered_renderer_policies():
    assert resolve_renderer_policy({'renderer_version':FAST_CUT_RENDERER_VERSION},{}).kind is RendererKind.FAST_CUT_V7
    assert resolve_renderer_policy({'renderer_version':AUTOMATIC_RENDERER_VERSION},{}).kind is RendererKind.AUTOMATIC_V9


def test_missing_version_is_observable_compatibility_not_unknown_fallback():
    policy=resolve_renderer_policy({}, {})
    assert policy.compatibility_used is True
    assert policy.reason == 'v0.1_missing_version_default'


def test_unknown_declared_version_is_rejected():
    with pytest.raises(ValueError,match='unsupported renderer version'):
        resolve_renderer_policy({'renderer_version':'unknown'}, {})
