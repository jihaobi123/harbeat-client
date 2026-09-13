"""RK audio runtime contracts with lazy hardware-engine exports."""

from .default_render_contract import DefaultRenderCommand, ValidatedDefaultRenderCommand, validate_default_render_command

__all__ = [
    "AudioEngineMVP",
    "Deck",
    "DefaultRenderCommand",
    "SongCacheError",
    "ValidatedDefaultRenderCommand",
    "validate_default_render_command",
]


def __getattr__(name: str):
    if name in {"AudioEngineMVP", "Deck", "SongCacheError"}:
        from .engine import AudioEngineMVP, Deck, SongCacheError

        return {
            "AudioEngineMVP": AudioEngineMVP,
            "Deck": Deck,
            "SongCacheError": SongCacheError,
        }[name]
    raise AttributeError(name)
