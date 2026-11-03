#!/usr/bin/env bash
# arm_flags.sh <arm>: the claude flags of an arm. full: the user's setup (Serena's claude-code context, its three hooks). light: a short Serena context, no hook.
S=$(cd "$(dirname "$0")" && pwd)
case "$1" in
  light) printf '%s\n' --settings '{"disableAllHooks": true}' --strict-mcp-config --mcp-config "$S/mcp-light.json" ;;
  full) ;;
  *) echo "unknown arm $1" >&2; exit 1 ;;
esac
