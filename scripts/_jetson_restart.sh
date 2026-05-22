#!/usr/bin/env bash
set -u
PW='123456'
echo "host=$(hostname)"
echo "--- restart harbeat ---"
echo "$PW" | sudo -S systemctl restart harbeat 2>&1 | tail -5
sleep 4
echo "is-active: $(systemctl is-active harbeat)"
pgrep -af 'uvicorn app.main' | head -1
echo "--- install NOPASSWD sudoers ---"
echo "$PW" | sudo -S bash -c 'cat > /etc/sudoers.d/harbeat-mark <<SUDOERS
mark ALL=(root) NOPASSWD: /bin/systemctl restart harbeat, /bin/systemctl status harbeat, /bin/systemctl stop harbeat, /bin/systemctl start harbeat
SUDOERS
chmod 440 /etc/sudoers.d/harbeat-mark
visudo -cf /etc/sudoers.d/harbeat-mark'
echo "--- verify NOPASSWD ---"
sudo -n -l 2>&1 | grep -E 'NOPASSWD|harbeat' | head -5
echo "--- quick smoke ---"
curl -s http://127.0.0.1:8000/api/music/flourish | head -c 200
echo
