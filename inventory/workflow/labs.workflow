name: Web Service Attack Walkthrough
description: >-
  Discovery, enumeration, and exploitation commands from three lab exercises,
  in order. Set each target, port, and URL when prompted; nothing is hardcoded.
  Repeated entries mean run the same preset again with a different input (e.g.
  another port or username). Shared input ids (host, url) mean a value set once
  is reused by every command that declares it; edit it when the target changes.
phases:
  full-port-scan:
    - labs.nmap-full-scan
  service-enumeration:
    - labs.netcat-connect
    - labs.netcat-connect
    - labs.netcat-connect
    - labs.smtp-vrfy-user
    - labs.smtp-vrfy-user
    - labs.smtp-vrfy-user
  webdav:
    - labs.webdav-options
    - labs.webdav-upload
    - labs.webdav-download
  service-fingerprinting:
    - labs.nmap-service-scan
  exploitation:
    - labs.apache-path-traversal-rce
  slow-port-scan:
    - labs.nmap-slow-range-scan
  http-enumeration:
    - labs.http-headers
