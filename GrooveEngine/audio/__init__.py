"""Package marker for audio.

Keep package imports lightweight so offline tooling does not require
real-time audio dependencies unless those symbols are actually used.
"""

__all__ = [
    "AudioDeck",
    "GrooveAudioEngine",
    "MixerFX",
    "OfflineDualDeckRenderer",
    "OfflineRenderResult",
    "SyncPreparation",
    "prepare_track_for_mix",
]


def __getattr__(name: str):
    if name == "AudioDeck":
        from audio.deck import AudioDeck

        return AudioDeck
    if name == "GrooveAudioEngine":
        from audio.engine import GrooveAudioEngine

        return GrooveAudioEngine
    if name == "MixerFX":
        from audio.mixer_fx import MixerFX

        return MixerFX
    if name == "OfflineDualDeckRenderer":
        from audio.offline_renderer import OfflineDualDeckRenderer

        return OfflineDualDeckRenderer
    if name == "OfflineRenderResult":
        from audio.offline_renderer import OfflineRenderResult

        return OfflineRenderResult
    if name == "SyncPreparation":
        from audio.sync import SyncPreparation

        return SyncPreparation
    if name == "prepare_track_for_mix":
        from audio.sync import prepare_track_for_mix

        return prepare_track_for_mix
    raise AttributeError(f"module 'audio' has no attribute {name!r}")
