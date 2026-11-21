name: Linux Recon
description: Read-only Linux reconnaissance chain.
phases:
  discovery:
    - linux.nmap.discovery
    - linux.ssh.version
    - linux.http.observation
