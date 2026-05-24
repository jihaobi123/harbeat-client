#!/usr/bin/env bash
# RK3588 Edge Agent deploy script
# Usage: ./deploy.sh [--restart] [--dry-run]
#
# 1. Backs up /home/cat/cypher to .bak.<timestamp>
# 2. SFTP copies rk3588_edge/ files
# 3. Optionally restarts cypher.target
#
# Requires: ssh, scp, sshpass (optional for password auth)

set -euo pipefail

# ── Config (set via env vars or edit inline) ──────────────────────────
RK_HOST="${RK_HOST:-}"
RK_USER="${RK_USER:-cat}"
RK_PORT="${RK_PORT:-22}"
RK_REMOTE_DIR="${RK_REMOTE_DIR:-/home/cat/cypher}"
RK_SERVICE="${RK_SERVICE:-cypher.target}"
SSH_PASS="${SSH_PASS:-}"

# ── Args ──────────────────────────────────────────────────────────────
DO_RESTART=false
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --restart) DO_RESTART=true ;;
        --dry-run) DRY_RUN=true ;;
        *) echo "Unknown arg: $arg"; exit 1 ;;
    esac
done

if [ -z "$RK_HOST" ]; then
    echo "ERROR: RK_HOST not set. Export it or edit deploy.sh."
    echo "Usage: RK_HOST=192.168.1.100 ./deploy.sh [--restart] [--dry-run]"
    exit 1
fi

# ── SSH command ───────────────────────────────────────────────────────
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -p ${RK_PORT}"
if [ -n "$SSH_PASS" ]; then
    SSH_CMD="sshpass -p '${SSH_PASS}' ssh ${SSH_OPTS}"
    SCP_CMD="sshpass -p '${SSH_PASS}' scp ${SSH_OPTS}"
else
    SSH_CMD="ssh ${SSH_OPTS}"
    SCP_CMD="scp ${SSH_OPTS}"
fi

# ── Local source ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_FILES=(
    "config.py"
    "state_manager.py"
    "sync_worker.py"
    "strategy_selector.py"
    "session_manager.py"
    "audio_engine.py"
    "main.py"
    "requirements.txt"
)

echo "=== HarBeat RK3588 Edge Deploy ==="
echo "Target: ${RK_USER}@${RK_HOST}:${RK_PORT} → ${RK_REMOTE_DIR}"
echo "Source: ${SCRIPT_DIR}"
echo "Restart: ${DO_RESTART}"
echo "Dry-run: ${DRY_RUN}"
echo ""

# ── Step 1: Backup ────────────────────────────────────────────────────
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${RK_REMOTE_DIR}.bak.${TIMESTAMP}"

echo "→ Backing up ${RK_REMOTE_DIR} → ${BACKUP_DIR} ..."
if [ "$DRY_RUN" = false ]; then
    ${SSH_CMD} "${RK_USER}@${RK_HOST}" "
        if [ -d '${RK_REMOTE_DIR}' ]; then
            cp -a '${RK_REMOTE_DIR}' '${BACKUP_DIR}'
            echo 'Backup OK: ${BACKUP_DIR}'
        else
            mkdir -p '${RK_REMOTE_DIR}'
            echo 'Fresh dir created: ${RK_REMOTE_DIR}'
        fi
    "
fi

# ── Step 2: Copy files ────────────────────────────────────────────────
echo ""
echo "→ Copying rk3588_edge files ..."
for f in "${SRC_FILES[@]}"; do
    src="${SCRIPT_DIR}/${f}"
    if [ ! -f "$src" ]; then
        echo "  SKIP: ${f} (not found)"
        continue
    fi
    echo "  COPY: ${f}"
    if [ "$DRY_RUN" = false ]; then
        ${SCP_CMD} "$src" "${RK_USER}@${RK_HOST}:${RK_REMOTE_DIR}/${f}"
    fi
done

# ── Step 3: Install dependencies (optional) ───────────────────────────
echo ""
echo "→ Checking Python deps ..."
if [ "$DRY_RUN" = false ]; then
    ${SSH_CMD} "${RK_USER}@${RK_HOST}" "
        cd '${RK_REMOTE_DIR}' && pip install -r requirements.txt --quiet 2>&1 | tail -1
    " || echo "  (pip install skipped or failed — may be OK if deps are pre-installed)"
fi

# ── Step 4: Restart ──────────────────────────────────────────────────
if [ "$DO_RESTART" = true ]; then
    echo ""
    echo "→ Restarting ${RK_SERVICE} ..."
    if [ "$DRY_RUN" = false ]; then
        ${SSH_CMD} "${RK_USER}@${RK_HOST}" "
            sudo systemctl restart '${RK_SERVICE}' && echo '  Service restarted OK'
        "
    fi
else
    echo ""
    echo "→ Restart skipped (use --restart to restart ${RK_SERVICE})"
fi

echo ""
echo "=== Deploy complete ==="
echo "Verify: curl http://${RK_HOST}:9100/health"
