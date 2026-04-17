#!/bin/bash
set -e

JETSON="mark@100.91.30.53"
SSH="ssh -o StrictHostKeyChecking=no -p 22 $JETSON"

echo "=== 1. Verify Jetson ==="
$SSH "hostname; uname -m; whoami"

echo ""
echo "=== 2. NAS connectivity ==="
$SSH "ping -c 2 -W 2 192.168.5.63 2>/dev/null && echo 'NAS_REACHABLE' || echo 'NAS_UNREACHABLE'"

echo ""
echo "=== 3. NAS mount status ==="
$SSH "mount | grep nas || echo 'NAS not mounted'"

echo ""
echo "=== 4. CIFS tools ==="
$SSH "dpkg -l 2>/dev/null | grep cifs || echo 'cifs-utils not installed'"

echo ""
echo "=== 5. /mnt/nas dir ==="
$SSH "ls -la /mnt/nas/harbeat/ 2>/dev/null || echo '/mnt/nas/harbeat does not exist'"

echo ""
echo "=== 6. Docker volumes on Jetson ==="
$SSH "docker volume ls 2>/dev/null || echo 'no docker access'"

echo ""
echo "=== 7. Local data dir ==="
$SSH "ls -la ~/harbeat/data/ 2>/dev/null; du -sh ~/harbeat/data/*/ 2>/dev/null || echo 'empty or missing'"
