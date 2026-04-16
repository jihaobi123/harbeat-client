"""Simple terminal UI for testing GrooveEngine workflows."""

from __future__ import annotations

from pathlib import Path

from analyzer.extractor import TrackAnalyzer
from analyzer.storage import MetadataStorage
from audio.engine import GrooveAudioEngine
from core.datatypes import MixCommand, TrackMetadata
from logic.brain import TransitionPlanner


class GrooveCLI:
    """Interactive CLI to analyze tracks and preview transition plans."""

    def __init__(self) -> None:
        self.analyzer = TrackAnalyzer()
        self.planner = TransitionPlanner()
        self.engine = GrooveAudioEngine()

    def run(self) -> None:
        """Run the command loop."""

        print("GrooveEngine CLI")
        print("1) Analyze track")
        print("2) Plan transition")
        print("3) Start audio engine")
        print("4) Stop audio engine")
        print("5) Quit")

        while True:
            choice = input("Select option: ").strip()
            if choice == "1":
                self._analyze_track()
            elif choice == "2":
                self._plan_transition()
            elif choice == "3":
                self.engine.start()
                print("Audio engine started.")
            elif choice == "4":
                self.engine.stop()
                print("Audio engine stopped.")
            elif choice == "5":
                self.engine.stop()
                print("Goodbye.")
                return
            else:
                print("Unknown option.")

    def _analyze_track(self) -> None:
        """Analyze a track and persist its metadata JSON."""

        audio_path = Path(input("Audio path: ").strip())
        metadata = self.analyzer.analyze(audio_path)
        output_path = audio_path.with_suffix(".groove.json")
        MetadataStorage.save(metadata, output_path)
        print(f"Saved analysis to {output_path}")

    def _plan_transition(self) -> None:
        """Load two metadata files and create a transition plan."""

        track_a_path = Path(input("Track A metadata path: ").strip())
        track_b_path = Path(input("Track B metadata path: ").strip())
        track_a = MetadataStorage.load(track_a_path)
        track_b = MetadataStorage.load(track_b_path)
        plan = self.planner.plan(track_a, track_b)
        self._print_plan(track_a, track_b, plan)

        load_audio = input("Load tracks into engine? [y/N]: ").strip().lower() == "y"
        if load_audio:
            self.engine.load_track("A", track_a, target_bpm=plan.target_bpm)
            self.engine.load_track("B", track_b, target_bpm=plan.target_bpm)
            self.engine.enqueue(MixCommand(command="apply_plan", payload={"plan": plan}))
            self.engine.enqueue(MixCommand(command="play", payload={"deck_id": "A"}))
            self.engine.enqueue(MixCommand(command="play", payload={"deck_id": "B"}))
            print("Tracks queued in engine.")

    def _print_plan(self, track_a: TrackMetadata, track_b: TrackMetadata, plan: object) -> None:
        """Render a concise summary for a transition plan."""

        print(f"Track A: {track_a.title}")
        print(f"Track B: {track_b.title}")
        print(f"Mix start: {plan.mix_start_time:.2f}s")
        print(f"Overlap beats: {plan.overlap_duration_beats}")
        print(f"Target BPM: {plan.target_bpm:.2f}")
        print(f"Strategy: {plan.strategy.value}")
        print(f"Score: {plan.score_breakdown.total_score:.3f}")
        for note in plan.score_breakdown.notes:
            print(f"- {note}")
