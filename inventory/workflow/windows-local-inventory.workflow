name: Windows Local Inventory
description: Local system and network configuration facts on Windows hosts.
phases:
  system:
    - windows.system-info
    - windows.ipconfig
  names:
    - windows.nbtstat-remote
