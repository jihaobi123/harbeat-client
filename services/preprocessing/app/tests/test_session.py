"""Tests for C6 Session Orchestration module."""
import unittest

from app.modules.session.schemas import (
    ButtonIntent,
    Candidate,
    CandidateList,
    ControlCommand,
    SceneConfig,
    SceneType,
    SessionConfig,
    SessionState,
)
from app.modules.session.state_machine import SessionStateMachine
from app.modules.session.undo_stack import UndoStack, UNDOABLE_ACTIONS, NON_UNDOABLE_ACTIONS
from app.modules.session.queue_manager import QueueManager, REPETITION_WINDOW_SEC
from app.modules.session.safety_pool import SafetyPool, DEFAULT_SAFETY_TRACK_CRITERIA
from app.modules.session.coordinator import SessionCoordinator


# ═══════════════════════════════════════════════════════════════════════════════
# State Machine
# ═══════════════════════════════════════════════════════════════════════════════

class StateMachineTests(unittest.TestCase):
    def test_start_goes_to_warmup(self):
        sm = SessionStateMachine()
        self.assertEqual(sm.state, SessionState.setup)
        sm.start()
        self.assertEqual(sm.state, SessionState.warmup)

    def test_energy_up_triggers_build(self):
        sm = SessionStateMachine()
        sm.start()
        new_state = sm.handle_intent("energy_up")
        self.assertEqual(new_state, SessionState.build)

    def test_energy_down_triggers_recover(self):
        sm = SessionStateMachine()
        sm.start()
        sm.handle_intent("energy_up")  # warmup → build
        new_state = sm.handle_intent("energy_down")
        self.assertEqual(new_state, SessionState.recover)

    def test_hold_triggers_hold_state(self):
        sm = SessionStateMachine()
        sm.start()
        sm.handle_intent("energy_up")  # → build
        new_state = sm.handle_intent("hold")
        self.assertEqual(new_state, SessionState.hold)

    def test_emergency_forces_emergency(self):
        sm = SessionStateMachine()
        sm.start()
        sm.force_emergency()
        self.assertEqual(sm.state, SessionState.emergency)

    def test_close_from_recover(self):
        sm = SessionStateMachine()
        sm.start()
        sm.handle_intent("energy_up")    # → build
        sm.handle_intent("energy_down")  # → recover
        sm.handle_intent("close")
        self.assertEqual(sm.state, SessionState.close)

    def test_auto_transition_after_many_tracks(self):
        sm = SessionStateMachine()
        sm.start()
        # Simulate 5 tracks in warmup → should auto-build
        for _ in range(5):
            sm.on_track_change(new_energy=0.4)
        self.assertEqual(sm.state, SessionState.build)

    def test_target_energy_changes_with_state(self):
        sm = SessionStateMachine()
        sm.start()
        self.assertGreater(sm.target_energy, 0.0)
        sm.handle_intent("energy_up")  # → build
        self.assertGreater(sm.target_energy, 0.4)

    def test_snapshot_contains_state_info(self):
        sm = SessionStateMachine()
        sm.start()
        snap = sm.snapshot()
        self.assertEqual(snap["state"], "warmup")
        self.assertIn("target_energy", snap)
        self.assertIn("track_count_in_state", snap)

    def test_state_change_listener_fires(self):
        sm = SessionStateMachine()
        transitions: list[tuple] = []
        sm.on_state_change(lambda old, new: transitions.append((old, new)))
        sm.start()
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0], (SessionState.setup, SessionState.warmup))


# ═══════════════════════════════════════════════════════════════════════════════
# Undo Stack
# ═══════════════════════════════════════════════════════════════════════════════

class UndoStackTests(unittest.TestCase):
    def test_push_and_pop(self):
        stack = UndoStack(max_depth=10)
        stack.push("next", prev_track_id="track_1")
        self.assertTrue(stack.can_undo())
        entry = stack.pop()
        self.assertIsNotNone(entry)
        if entry:
            self.assertEqual(entry.action, "next")
            self.assertEqual(entry.prev_track_id, "track_1")

    def test_emergency_not_undoable(self):
        stack = UndoStack()
        result = stack.push("emergency_next", prev_track_id="track_1")
        self.assertIsNone(result)
        self.assertFalse(stack.can_undo())

    def test_undoable_actions_match_spec(self):
        for action in UNDOABLE_ACTIONS:
            stack = UndoStack()
            result = stack.push(action, prev_track_id="t1")
            self.assertIsNotNone(result, f"'{action}' should be undoable")

    def test_non_undoable_actions_are_not_stored(self):
        for action in NON_UNDOABLE_ACTIONS:
            stack = UndoStack()
            result = stack.push(action, prev_track_id="t1")
            self.assertIsNone(result, f"'{action}' should NOT be undoable")

    def test_stack_depth_limited(self):
        stack = UndoStack(max_depth=3)
        for i in range(5):
            stack.push("next", prev_track_id=f"track_{i}")
        self.assertEqual(stack.depth, 3)

    def test_clear_empties_stack(self):
        stack = UndoStack()
        stack.push("next", prev_track_id="track_1")
        stack.clear()
        self.assertFalse(stack.can_undo())
        self.assertEqual(stack.depth, 0)

    def test_peek_does_not_pop(self):
        stack = UndoStack()
        stack.push("next", prev_track_id="track_1")
        self.assertEqual(stack.depth, 1)
        peeked = stack.peek()
        self.assertIsNotNone(peeked)
        if peeked:
            self.assertEqual(peeked.action, "next")
        self.assertEqual(stack.depth, 1)  # still there

    def test_snapshot(self):
        stack = UndoStack()
        stack.push("next", prev_track_id="track_1")
        snap = stack.snapshot()
        self.assertTrue(snap["can_undo"])
        self.assertEqual(snap["depth"], 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Queue Manager
# ═══════════════════════════════════════════════════════════════════════════════

class QueueManagerTests(unittest.TestCase):
    def test_set_current_and_history(self):
        qm = QueueManager(buffer_size=3)
        qm.set_current("track_1", artist="Artist A", energy=0.5)
        self.assertEqual(qm.current_track_id, "track_1")
        qm.set_current("track_2", artist="Artist B", energy=0.6)
        self.assertEqual(qm.current_track_id, "track_2")
        self.assertEqual(qm.history_count, 1)

    def test_refill_queue(self):
        qm = QueueManager(buffer_size=3)
        candidates = CandidateList(
            candidates=[
                Candidate(track_id="t1", score=0.9),
                Candidate(track_id="t2", score=0.8),
                Candidate(track_id="t3", score=0.7),
            ]
        )
        count = qm.refill(candidates)
        self.assertEqual(count, 3)
        self.assertEqual(qm.size, 3)

    def test_pop_returns_best_first(self):
        qm = QueueManager(buffer_size=3)
        qm.refill(CandidateList(candidates=[
            Candidate(track_id="t1", score=0.9),
            Candidate(track_id="t2", score=0.8),
        ]))
        first = qm.pop()
        self.assertIsNotNone(first)
        if first:
            self.assertEqual(first.track_id, "t1")

    def test_repetition_penalty_recent_track_blocked(self):
        qm = QueueManager()
        qm.set_current("track_1", artist="Artist A", energy=0.5)
        qm.set_current("track_2", artist="Artist B", energy=0.6)
        penalty = qm.repetition_penalty("track_1")
        self.assertGreater(penalty, 0.5)  # heavily penalized

    def test_repetition_penalty_fresh_track_ok(self):
        qm = QueueManager()
        qm.set_current("track_1", artist="Artist A", energy=0.5)
        penalty = qm.repetition_penalty("track_99")
        self.assertEqual(penalty, 0.0)

    def test_energy_trend_detection(self):
        qm = QueueManager()
        qm.set_current("t1", energy=0.3)
        qm.set_current("t2", energy=0.5)
        qm.set_current("t3", energy=0.7)
        qm.set_current("t4", energy=0.85)
        self.assertEqual(qm.history_energy_trend(window=3), "rising")

    def test_snapshot(self):
        qm = QueueManager()
        qm.set_current("t1", energy=0.5)
        qm.refill(CandidateList(candidates=[Candidate(track_id="t2", score=0.9)]))
        snap = qm.snapshot()
        self.assertEqual(snap["current_track_id"], "t1")
        self.assertEqual(snap["queue_size"], 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Safety Pool
# ═══════════════════════════════════════════════════════════════════════════════

class SafetyPoolTests(unittest.TestCase):
    def _make_track(self, tid, bpm=100, energy=0.5, genre="house", tags=None):
        return {
            "track_id": tid, "bpm": bpm, "energy": energy,
            "primary_genre": genre, "tags": tags or [],
            "beat_points": [0.0, 0.5, 1.0],
            "beat_confidence": 0.95,
            "intro_is_clean": True,
            "outro_is_clean": True,
        }

    def test_build_pool_filters_by_bpm(self):
        sp = SafetyPool()
        tracks = [
            self._make_track("t1", bpm=60),   # too slow
            self._make_track("t2", bpm=100),  # OK
            self._make_track("t3", bpm=140),  # too fast
        ]
        pool = sp.build(tracks, min_tracks=1, max_tracks=10)
        self.assertIn("t2", pool)
        self.assertNotIn("t1", pool)

    def test_build_pool_respects_genre_preferences(self):
        sp = SafetyPool()
        tracks = [
            self._make_track("t1", genre="hip-hop"),
            self._make_track("t2", genre="ambient"),  # not preferred
        ]
        pool = sp.build(tracks, min_tracks=1, max_tracks=10)
        # hip-hop should rank higher than ambient
        if pool:
            self.assertEqual(pool[0], "t1")

    def test_get_random_returns_track(self):
        sp = SafetyPool()
        sp.build([
            self._make_track("t1"), self._make_track("t2"), self._make_track("t3"),
        ], min_tracks=3)
        result = sp.get_random()
        self.assertIsNotNone(result)
        self.assertIn(result, ["t1", "t2", "t3"])

    def test_get_random_excludes_ids(self):
        sp = SafetyPool()
        sp.build([
            self._make_track("t1"), self._make_track("t2"),
        ], min_tracks=2)
        result = sp.get_random(exclude=["t1"])
        self.assertEqual(result, "t2")

    def test_empty_pool_returns_none(self):
        sp = SafetyPool()
        self.assertIsNone(sp.get_random())

    def test_snapshot(self):
        sp = SafetyPool()
        sp.build([self._make_track("t1")], min_tracks=1)
        snap = sp.snapshot()
        self.assertEqual(snap["size"], 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Coordinator
# ═══════════════════════════════════════════════════════════════════════════════

class FakeCandidateSelector:
    """Stub C3 for testing."""
    def select_candidates(self, **kwargs):
        return CandidateList(
            candidates=[
                Candidate(track_id="cand_1", score=0.9, template="safe_blend",
                         reason="Good match", warnings=[]),
                Candidate(track_id="cand_2", score=0.8, template="drop_in",
                         reason="OK match", warnings=["bpm_jump"]),
            ],
            best=Candidate(track_id="cand_1", score=0.9, template="safe_blend"),
            safe=Candidate(track_id="cand_1", score=0.9, template="safe_blend"),
            diverse=Candidate(track_id="cand_2", score=0.8, template="drop_in"),
            fallback_track_id="cand_safe",
        )


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.selector = FakeCandidateSelector()
        self.coord = SessionCoordinator(
            config=SessionConfig(),
            candidate_selector=self.selector,
        )

    def test_start_session(self):
        snap = self.coord.start()
        self.assertEqual(snap.state, SessionState.warmup)

    def test_handle_energy_up_returns_command(self):
        self.coord.start()
        cmd = self.coord.handle_intent(ButtonIntent(action="energy_up"))
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.action, "xfade")
        self.assertEqual(cmd.params.get("style"), "energy_lift")
        self.assertIsNotNone(cmd.params.get("to_track_id"))

    def test_handle_next_returns_command(self):
        self.coord.start()
        cmd = self.coord.handle_intent(ButtonIntent(action="next"))
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.action, "xfade")

    def test_handle_emergency_next_returns_immediate_command(self):
        self.coord.start()
        self.coord.build_safety_pool([
            {"track_id": "safe_1", "bpm": 100, "energy": 0.5,
             "primary_genre": "hip-hop", "tags": [], "beat_points": [0.0, 0.5]},
        ])
        cmd = self.coord.handle_intent(ButtonIntent(action="emergency_next"))
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.action, "emergency_cut")
        self.assertEqual(cmd.execute_at, "now")
        self.assertFalse(cmd.quantize)

    def test_undo_with_empty_stack_returns_none(self):
        self.coord.start()
        cmd = self.coord.handle_intent(ButtonIntent(action="undo"))
        self.assertIsNone(cmd)

    def test_undo_after_action_returns_revert_command(self):
        self.coord.start()
        self.coord._queue.set_current("track_before", energy=0.5)
        # Do an action
        self.coord.handle_intent(ButtonIntent(action="energy_up"))
        # Now undo
        cmd = self.coord.handle_intent(ButtonIntent(action="undo"))
        self.assertIsNotNone(cmd)
        self.assertIn("track_before", cmd.params.get("to_track_id", ""))

    def test_handle_hold_returns_command(self):
        self.coord.start()
        self.coord.handle_intent(ButtonIntent(action="energy_up"))  # → build
        cmd = self.coord.handle_intent(ButtonIntent(action="hold"))
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.params.get("style"), "safe_blend")

    def test_handle_talkover_returns_duck_command(self):
        self.coord.start()
        cmd = self.coord.handle_intent(ButtonIntent(action="talkover"))
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.action, "duck")
        self.assertEqual(cmd.params.get("db"), -12)

    def test_track_change_updates_state(self):
        self.coord.start()
        self.coord.on_track_changed("track_1", energy=0.5)
        snap = self.coord.snapshot()
        self.assertEqual(snap.current_track_id, "track_1")

    def test_snapshot_contains_all_fields(self):
        self.coord.start()
        self.coord.on_track_changed("track_1", energy=0.6)
        snap = self.coord.snapshot()
        self.assertIsNotNone(snap.session_id)
        self.assertEqual(snap.state, SessionState.warmup)
        self.assertEqual(snap.current_track_id, "track_1")


if __name__ == "__main__":
    unittest.main()
