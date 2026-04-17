#!/bin/bash
JETSON="mark@100.91.30.53"
SSH="ssh -o StrictHostKeyChecking=no -p 22 $JETSON"

echo "=== NAS music-files ==="
$SSH "ls /mnt/nas/harbeat/music-files/ | head -20; echo '---'; ls /mnt/nas/harbeat/music-files/ | wc -l"

echo ""
echo "=== NAS music-files subdirs ==="
$SSH "find /mnt/nas/harbeat/music-files -maxdepth 1 -type d | head -10"

echo ""
echo "=== NAS stems check ==="
$SSH "ls /mnt/nas/harbeat/music-files/stems/ 2>/dev/null | head -5; echo stems_count:; ls /mnt/nas/harbeat/music-files/stems/ 2>/dev/null | wc -l"

echo ""
echo "=== NAS shared check ==="
$SSH "ls /mnt/nas/harbeat/music-files/shared/ 2>/dev/null | head -5; echo shared_count:; ls /mnt/nas/harbeat/music-files/shared/ 2>/dev/null | wc -l"

echo ""
echo "=== NAS du ==="
$SSH "du -sh /mnt/nas/harbeat/music-files/*/ 2>/dev/null"

echo ""
echo "=== NAS models, backups ==="
$SSH "du -sh /mnt/nas/harbeat/models/ /mnt/nas/harbeat/backups/ /mnt/nas/harbeat/logs/ 2>/dev/null"

echo ""
echo "=== fstab NAS entry ==="
$SSH "cat /etc/fstab | grep -i nas 2>/dev/null || echo 'no fstab entry'"

echo ""
echo "=== Jetson .env ==="
$SSH "cat ~/harbeat/.env"
