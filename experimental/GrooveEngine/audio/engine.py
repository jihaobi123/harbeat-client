"""Real-time audio engine with lock-free callback design."""

from __future__ import annotations

from dataclasses import dataclass, field
from queue import Empty, SimpleQueue
import threading
import time

import numpy as np
import sounddevice as sd

from audio.deck import AudioDeck
from audio.mixer_fx import MixerFX
from core.datatypes import MixCommand, TrackMetadata, TransitionPlan


@dataclass(slots=True)
class RingBuffer:
    """Lightweight Numpy ring buffer for audio blocks."""

    capacity_frames: int
    channels: int
    buffer: np.ndarray = field(init=False)
    write_index: int = field(default=0, init=False)
    read_index: int = field(default=0, init=False)
    available_frames: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.buffer = np.zeros((self.capacity_frames, self.channels), dtype=np.float32)

    def write(self, frames: np.ndarray) -> None:
        """Write frames into the ring buffer, overwriting oldest data if full."""

        for frame in frames:
            self.buffer[self.write_index] = frame
            self.write_index = (self.write_index + 1) % self.capacity_frames
            if self.available_frames < self.capacity_frames:
                self.available_frames += 1
            else:
                self.read_index = (self.read_index + 1) % self.capacity_frames

    def read(self, frame_count: int) -> np.ndarray:
        """Read up to frame_count frames from the buffer."""

        output = np.zeros((frame_count, self.channels), dtype=np.float32)
        frames_to_read = min(frame_count, self.available_frames)
        for index in range(frames_to_read):
            output[index] = self.buffer[self.read_index]
            self.read_index = (self.read_index + 1) % self.capacity_frames
        self.available_frames -= frames_to_read
        return output


class GrooveAudioEngine:
    """Coordinates decks, FX, and the output stream."""

    def __init__(self, sample_rate: int = 44100, block_size: int = 1024) -> None:
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.command_queue: SimpleQueue[MixCommand] = SimpleQueue()
        self.deck_a = AudioDeck(deck_id="A")
        self.deck_b = AudioDeck(deck_id="B")
        self.fx = MixerFX(sample_rate=sample_rate)
        self.output_ring = RingBuffer(capacity_frames=sample_rate * 8, channels=2)
        self.stream: sd.OutputStream | None = None
        self.running = False
        self.render_thread: threading.Thread | None = None
        self.active_plan: TransitionPlan | None = None
        self.transition_start_time: float | None = None

    def start(self) -> None:
        """Start the render loop and output stream."""

        if self.running:
            return
        self.running = True
        self.render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self.render_thread.start()
        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=2,
            dtype="float32",
            callback=self._audio_callback,
        )
        self.stream.start()

    def stop(self) -> None:
        """Stop audio processing."""

        self.running = False
        if self.render_thread and self.render_thread.is_alive():
            self.render_thread.join(timeout=1.0)
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def enqueue(self, command: MixCommand) -> None:
        """Send a command from the main thread to the engine."""

        self.command_queue.put(command)

    def load_track(self, deck_id: str, metadata: TrackMetadata, target_bpm: float | None = None) -> None:
        """Load a track on a deck."""

        deck = self.deck_a if deck_id == "A" else self.deck_b
        deck.load(metadata, target_bpm=target_bpm)

    def apply_transition_plan(self, plan: TransitionPlan) -> None:
        """Activate a transition plan for automation playback."""

        self.active_plan = plan
        self.transition_start_time = time.perf_counter()

    def _audio_callback(self, outdata: np.ndarray, frames: int, _time_info: object, _status: object) -> None:
        """Lock-free callback: only reads from the prepared ring buffer."""

        outdata[:] = self.output_ring.read(frames)

    def _render_loop(self) -> None:
        """Background renderer that processes commands and fills the output ring."""

        while self.running:
            self._drain_commands()
            block_a = self.deck_a.read_frames(self.block_size)
            block_b = self.deck_b.read_frames(self.block_size)

            transition_beat = self._transition_beat_position()
            if self.active_plan is not None:
                self.fx.apply_automation(self.active_plan.automation, transition_beat)

            processed_a = self.fx.process_deck("A", block_a)
            processed_b = self.fx.process_deck("B", block_b)
            mixed = self.fx.mix(processed_a, processed_b, self.fx.master_noise_level())
            self.output_ring.write(mixed)

            if self.output_ring.available_frames > self.block_size * 6:
                time.sleep(self.block_size / self.sample_rate / 2)

    def _drain_commands(self) -> None:
        """Handle all pending commands from the control thread."""

        while True:
            try:
                command = self.command_queue.get_nowait()
            except Empty:
                break
            self._handle_command(command)

    def _handle_command(self, command: MixCommand) -> None:
        """Dispatch a mixer command."""

        if command.command == "play":
            deck_id = command.payload["deck_id"]
            deck = self.deck_a if deck_id == "A" else self.deck_b
            deck.play()
        elif command.command == "pause":
            deck_id = command.payload["deck_id"]
            deck = self.deck_a if deck_id == "A" else self.deck_b
            deck.pause()
        elif command.command == "stop":
            self.deck_a.stop()
            self.deck_b.stop()
        elif command.command == "apply_plan":
            self.apply_transition_plan(command.payload["plan"])

    def _transition_beat_position(self) -> float:
        """Compute current transition beat offset from wall clock time."""

        if self.transition_start_time is None or self.active_plan is None:
            return 0.0
        elapsed = time.perf_counter() - self.transition_start_time
        beats_per_second = self.active_plan.target_bpm / 60.0
        return elapsed * beats_per_second
