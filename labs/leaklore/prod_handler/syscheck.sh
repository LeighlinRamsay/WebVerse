#!/bin/sh
set -eu

cmd="${1:-}"

case "$cmd" in
  status)
    echo "machine_status=RUNNING"
    echo "uptime_seconds=48211"
    ;;
  processes)
    ps aux
    ;;
  uname)
    uname -a
    ;;
  net)
    ip a || ifconfig
    ;;
  mem)
    free -m
    ;;
  whoami)
    whoami
    ;;
  *)
    echo "Unknown subcommand: $*"
    ;;
esac
