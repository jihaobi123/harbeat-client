import importlib.util
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT / "tools" / "flow_hub_mock.py"


def load_module():
    spec = importlib.util.spec_from_file_location("flow_hub_mock", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HubStateMachineTest(unittest.TestCase):
    def setUp(self):
        module = load_module()
        self.machine = module.HubStateMachine(
            session_id="8f3a19d04b7c221e",
            transition_seconds=12,
        )

    def test_energy_command_acknowledges_and_completes(self):
        snapshots = self.machine.handle_command(
            {"v": 1, "kind": "command", "id": 42, "op": "set_energy", "value": 5}
        )
        self.assertEqual(
            ["accepted", "preparing", "transitioning", "completed"],
            [item["phase"] for item in snapshots],
        )
        self.assertEqual([12000, 8000, 3000, 0], [item["eta_ms"] for item in snapshots])
        self.assertTrue(all(item["ack_id"] == 42 for item in snapshots))
        self.assertEqual(5, snapshots[-1]["current"]["energy"])
        self.assertFalse(snapshots[-1]["locked"])

    def test_style_command_keeps_energy_and_updates_style(self):
        snapshots = self.machine.handle_command(
            {"v": 1, "kind": "command", "id": 43, "op": "set_style", "value": "breaking"}
        )
        self.assertEqual("breaking", snapshots[-1]["current"]["style"])
        self.assertEqual(3, snapshots[-1]["current"]["energy"])

    def test_duplicate_id_is_not_executed_twice(self):
        command = {"v": 1, "kind": "command", "id": 7, "op": "set_energy", "value": 4}
        self.assertEqual(4, len(self.machine.handle_command(command)))
        self.assertEqual([], self.machine.handle_command(command))

    def test_wrong_version_and_invalid_value_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "protocol version"):
            self.machine.handle_command(
                {"v": 2, "kind": "command", "id": 1, "op": "set_energy", "value": 4}
            )
        with self.assertRaisesRegex(ValueError, "energy"):
            self.machine.handle_command(
                {"v": 1, "kind": "command", "id": 2, "op": "set_energy", "value": 6}
            )


if __name__ == "__main__":
    unittest.main()
