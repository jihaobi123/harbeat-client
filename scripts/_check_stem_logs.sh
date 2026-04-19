#!/bin/bash
journalctl -u harbeat --no-pager -n 10000 2>/dev/null | grep -iE 'stem.separation.failed|demucs.exit|demucs.fail' | tail -20
