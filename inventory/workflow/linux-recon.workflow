name: Linux Recon
description: Host, service, and web inventory commands for Linux targets, grouped by phase.
phases:
  hosts:
    - linux.ping-check
    - linux.nmap-ping-sweep
    - linux.netdiscover
  services:
    - linux.nmap.discovery
    - linux.ssh.version
  web:
    - linux.http.observation
    - linux.http-get
    - linux.nmap-http-methods
