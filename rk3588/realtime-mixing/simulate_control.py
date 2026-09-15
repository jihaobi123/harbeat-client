#!/usr/bin/env python3
"""Send the same event envelope that a future local wearable gateway will send."""
import argparse
import json
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['state', 'capabilities', 'start', 'pause', 'stop',
                                         'next', 'set_style', 'gesture', 'trigger_effect'])
    parser.add_argument('--value', help='style_id, gesture_id or effect_id')
    parser.add_argument('--event-id', default=None, help='Reuse ONLY when retrying the same event')
    parser.add_argument('--boot-id', default='manual-simulator-v1')
    args = parser.parse_args()
    base = 'http://127.0.0.1:9130/v1/'
    if args.action in ('state', 'capabilities'):
        req = urllib.request.Request(base + args.action)
    else:
        params = {}
        key = {'set_style': 'style_id', 'gesture': 'gesture_id',
               'trigger_effect': 'effect_id'}.get(args.action)
        if key:
            if not args.value:
                parser.error('--value is required for ' + args.action)
            params[key] = args.value
        payload = dict(schema_version='harbeat.control.v1', source='simulator',
                       device_id='sim-ring' if args.action in ('gesture', 'trigger_effect') else 'sim-wrist',
                       boot_id=args.boot_id, event_id=args.event_id or str(time.time_ns()),
                       action=args.action, params=params)
        req = urllib.request.Request(base + 'device-events', data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            print(response.read().decode())
    except urllib.error.HTTPError as exc:
        print(exc.read().decode())
        raise SystemExit(1)


if __name__ == '__main__':
    main()
