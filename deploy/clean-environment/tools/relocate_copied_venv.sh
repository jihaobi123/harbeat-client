#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <venv-root> <old-release-root> <new-release-root>" >&2
  exit 2
fi

VENV_ROOT="$(realpath "$1")"
OLD_RELEASE="$2"
NEW_RELEASE="$3"

case "$VENV_ROOT" in
  /opt/harbeat/releases/*/venv) ;;
  *) echo "venv must be below /opt/harbeat/releases: $VENV_ROOT" >&2; exit 2 ;;
esac
case "$OLD_RELEASE" in /opt/harbeat/releases/*) ;; *) exit 2 ;; esac
case "$NEW_RELEASE" in /opt/harbeat/releases/*) ;; *) exit 2 ;; esac

mapfile -t scripts < <(grep -R -I -l -F "$OLD_RELEASE" "$VENV_ROOT/bin" || true)
if [[ ${#scripts[@]} -gt 0 ]]; then
  sed -i "s#${OLD_RELEASE}#${NEW_RELEASE}#g" "${scripts[@]}"
fi

find "$VENV_ROOT" -type f -path '*.dist-info/direct_url.json' -delete

if grep -R -I -l -F "$OLD_RELEASE" "$VENV_ROOT" | grep -q .; then
  echo "old release references remain" >&2
  exit 3
fi
if find "$VENV_ROOT" -type f -path '*.dist-info/direct_url.json' -print -quit | grep -q .; then
  echo "direct URL metadata remains" >&2
  exit 3
fi

echo "relocated_venv=$VENV_ROOT"

