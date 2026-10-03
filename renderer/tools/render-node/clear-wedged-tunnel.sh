#!/bin/bash
# Clear a WEDGED reverse-tunnel forward on the VPS.
#
# The failure it fixes
# --------------------
# The Windows-side ssh dies without a clean FIN -- a network drop, a suspend, or a reboot.
# The VPS-side sshd child keeps the remote-forward listener it created, so
#   127.0.0.1:8760 on the VPS
# still has a LISTEN socket, but nothing behind it: connections are ACCEPTED and then hang
# until they time out. The next tunnel then cannot bind and ssh exits with
#   Error: remote port forwarding failed for listen port 8760
# so the node can never come back on its own. This is the most likely thing to meet the
# machine after a reboot, because the pre-reboot session is exactly that kind of corpse.
#
# Safety
# ------
# It kills ONE process: the sshd child that currently owns the 127.0.0.1:8760 listener --
# and only when that is provably not the session running this script. It never touches the
# master sshd, never touches other sessions (the user's -L 6185 / -L 6099 tunnel is a
# different sshd and is left alone), and never touches mania-render.service, AstrBot,
# NapCat, UFW or nginx. Run it only when the "remote port forwarding failed" signature is
# present; node-launcher.ps1 checks for exactly that before invoking it.
#
# Usage (from Windows):
#   Get-Content clear-wedged-tunnel.sh -Raw | ssh -i <key> root@www.liuliyue.com "tr -d '\r' | bash -s"

set -u

ME=$(ps -o ppid= -p $$ | tr -d ' ')
OWNER=$(ss -lntp 2>/dev/null | grep '127.0.0.1:8760' | grep -oP 'pid=\K[0-9]+' | head -1)

echo "my session sshd = $ME"
echo "8760 listener owner = ${OWNER:-<none>}"

if [ -z "${OWNER:-}" ]; then
  echo "nothing to clear: no listener on 127.0.0.1:8760"
  exit 0
fi

if [ "$OWNER" = "$ME" ]; then
  echo "REFUSE: the 8760 listener belongs to this very session -- not killing it"
  exit 1
fi

# Only ever a per-session child ("sshd: root"), never the master daemon ("sshd -D ...").
OWNER_CMD=$(ps -o cmd= -p "$OWNER" 2>/dev/null || echo "")
case "$OWNER_CMD" in
  *"sshd -D"*) echo "REFUSE: $OWNER is the master sshd daemon"; exit 1 ;;
  *sshd*)      : ;;
  *)           echo "REFUSE: $OWNER is not an sshd ($OWNER_CMD)"; exit 1 ;;
esac

echo "killing wedged session sshd pid=$OWNER"
kill -TERM "$OWNER" 2>/dev/null
sleep 2
if kill -0 "$OWNER" 2>/dev/null; then
  kill -KILL "$OWNER" 2>/dev/null
  sleep 1
fi

if ss -lntp 2>/dev/null | grep -q '127.0.0.1:8760'; then
  echo "STILL HELD: 8760 is still listening after the kill"
  ss -lntp 2>/dev/null | grep 8760
  exit 1
fi

echo "8760 now FREE on the VPS -- the supervisor's next reconnect will bind it"
