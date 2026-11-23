name: Network Discovery
description: Host discovery, name lookups, and port checks across network segments.
phases:
  hosts:
    - linux.netdiscover
    - linux.nmap-ping-sweep
    - windows.nmap-ping-sweep
  names:
    - linux.dnsenum
    - windows.nbtscan
    - windows.nbtstat-remote
  ports:
    - windows.basic-discovery
