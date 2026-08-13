"""Standalone local-window transition renderer."""

from .reference_renderer import (
    FAST_CUT_RENDERER_VERSION,
    RENDERER_VERSION,
    DefaultRenderError,
    ensure_reference_render,
    pair_cache_root,
    pair_dir,
)
from .policy import RendererKind, RendererPolicy, resolve_renderer_policy

__all__ = [
    "FAST_CUT_RENDERER_VERSION",
    "RENDERER_VERSION",
    "RendererKind",
    "RendererPolicy",
    "DefaultRenderError",
    "ensure_reference_render",
    "pair_cache_root",
    "pair_dir",
    "resolve_renderer_policy",
]
