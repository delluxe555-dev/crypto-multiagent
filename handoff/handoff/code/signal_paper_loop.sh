#!/bin/bash
# silent 15-minute scan loop; logs only
cd /workspace/crypto-agents
while true; do
  python3 signal_paper.py --scan >/dev/null 2>&1
  python3 confluence_paper.py --scan >/dev/null 2>&1
  python3 dominance.py --snapshot >/dev/null 2>&1
  now=$(date +%s)
  sleep $(( 900 - (now % 900) + 90 ))
done
