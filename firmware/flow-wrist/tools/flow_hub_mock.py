#!/usr/bin/env python3
"""Small Flow Hub BLE Central for Mac bring-up and RK3588 handoff."""

from __future__ import annotations

import argparse
import asyncio
import secrets
from copy import deepcopy


SERVICE_UUID = "464c4f57-0001-4f57-8101-000000000001"
COMMAND_UUID = "464c4f57-0001-4f57-8101-000000000002"
STATE_UUID = "464c4f57-0001-4f57-8101-000000000003"
CATALOG_UUID = "464c4f57-0001-4f57-8101-000000000004"
PROTOCOL_VERSION = 1
STYLES = ("hiphop", "breaking", "funk", "locking")


class HubStateMachine:
    def __init__(self, session_id=None, transition_seconds=12):
        self.session_id = session_id or secrets.token_hex(8)
        self.transition_seconds = max(4, int(transition_seconds))
        self.revision = 0
        self.current = {"energy": 3, "style": "hiphop", "bpm": 96}
        self.seen_ids = set()

    def catalog(self):
        return {
            "v": PROTOCOL_VERSION,
            "kind": "catalog",
            "energy_min": 1,
            "energy_max": 5,
            "styles": [
                {"id": style, "label": style.upper(), "order": index + 1}
                for index, style in enumerate(STYLES)
            ],
        }

    def initial_snapshot(self):
        return self._snapshot(0, "idle", False, 0, None)

    def _snapshot(self, command_id, phase, locked, eta_ms, target, error=None):
        self.revision += 1
        return {
            "v": PROTOCOL_VERSION,
            "kind": "snapshot",
            "session_id": self.session_id,
            "revision": self.revision,
            "ack_id": command_id,
            "phase": phase,
            "locked": locked,
            "eta_ms": eta_ms,
            "current": deepcopy(self.current),
            "target": deepcopy(target),
            "error": error,
        }

    def _validate(self, command):
        if command.get("v") != PROTOCOL_VERSION:
            raise ValueError("unsupported protocol version")
        if command.get("kind") != "command" or not isinstance(command.get("id"), int):
            raise ValueError("invalid command envelope")
        if command["id"] <= 0:
            raise ValueError("command id must be positive")
        operation = command.get("op")
        value = command.get("value")
        if operation == "set_energy":
            if not isinstance(value, int) or not 1 <= value <= 5:
                raise ValueError("energy must be 1..5")
        elif operation == "set_style":
            if value not in STYLES:
                raise ValueError("unknown style")
        else:
            raise ValueError("unknown operation")

    def handle_command(self, command):
        self._validate(command)
        command_id = command["id"]
        if command_id in self.seen_ids:
            return []
        self.seen_ids.add(command_id)

        target = deepcopy(self.current)
        if command["op"] == "set_energy":
            target["energy"] = command["value"]
        else:
            target["style"] = command["value"]

        seconds = self.transition_seconds
        snapshots = [
            self._snapshot(command_id, "accepted", True, seconds * 1000, target),
            self._snapshot(command_id, "preparing", True, max(0, seconds - 4) * 1000, target),
            self._snapshot(command_id, "transitioning", True, 3000, target),
        ]
        self.current = deepcopy(target)
        snapshots.append(self._snapshot(command_id, "completed", False, 0, target))
        return snapshots


async def run_ble(device_prefix, transition_seconds, verbose):
    try:
        import cbor2
        from bleak import BleakClient, BleakScanner
    except ImportError as exc:
        raise SystemExit(
            "Install dependencies first: python3 -m pip install -r tools/requirements-hub-mock.txt"
        ) from exc

    print(f"Scanning for {device_prefix}...")
    device = await BleakScanner.find_device_by_filter(
        lambda found, advertisement: bool(found.name and found.name.startswith(device_prefix))
        or SERVICE_UUID in [item.lower() for item in advertisement.service_uuids],
        timeout=20.0,
    )
    if device is None:
        raise SystemExit(f"No {device_prefix} peripheral found")

    machine = HubStateMachine(transition_seconds=transition_seconds)
    transition_lock = asyncio.Lock()
    async with BleakClient(device) as client:
        try:
            pair = getattr(client, "pair", None)
            if pair is not None:
                await pair()
        except (NotImplementedError, AttributeError):
            pass

        async def write_snapshot(snapshot):
            if verbose:
                print("STATE", snapshot)
            await client.write_gatt_char(STATE_UUID, cbor2.dumps(snapshot), response=True)

        async def process_command(data):
            async with transition_lock:
                try:
                    command = cbor2.loads(bytes(data))
                    print("COMMAND", command)
                    snapshots = machine.handle_command(command)
                    if not snapshots:
                        print(f"Duplicate command {command.get('id')} ignored")
                        return
                    await write_snapshot(snapshots[0])
                    await asyncio.sleep(1)
                    await write_snapshot(snapshots[1])
                    await asyncio.sleep(max(1, transition_seconds - 4))
                    await write_snapshot(snapshots[2])
                    await asyncio.sleep(3)
                    await write_snapshot(snapshots[3])
                except Exception as exc:  # keep the mock alive for the next command
                    print("Command rejected:", exc)

        def on_command(_characteristic, data):
            asyncio.create_task(process_command(data))

        await client.start_notify(COMMAND_UUID, on_command)
        try:
            await client.write_gatt_char(
                CATALOG_UUID, cbor2.dumps(machine.catalog()), response=True
            )
            await write_snapshot(machine.initial_snapshot())
        except Exception as exc:
            if "Insufficient Encryption" in str(exc):
                raise SystemExit(
                    "The Central connected but did not pair. On macOS this can be a "
                    "CoreBluetooth limitation; use RK3588/BlueZ or a mobile BLE Central "
                    "and keep the Wrist encrypted characteristics enabled."
                ) from exc
            raise
        print(f"Connected to {device.name}; Flow Wrist is ready")
        await asyncio.Event().wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="FLOW-WRIST", help="BLE name prefix")
    parser.add_argument("--transition-seconds", type=int, default=12)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_ble(args.device, args.transition_seconds, args.verbose))


if __name__ == "__main__":
    main()
