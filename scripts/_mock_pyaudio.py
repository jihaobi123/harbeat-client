"""Mock pyaudio for BeatNet offline mode (no microphone needed)."""
paFloat32 = 8  # pyaudio constant

class PyAudio:
    def open(self, **kwargs):
        raise RuntimeError("pyaudio mock: real-time audio not available")
    def terminate(self):
        pass
