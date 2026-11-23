name: Windows Survey
description: Service, share, and directory inventory commands for Windows hosts.
phases:
  discovery:
    - windows.basic-discovery
    - windows.nmap.discovery
    - windows.smb.audit
  directory:
    - windows.ldap.inventory
  exposure:
    - windows.rdp.exposure
    - windows.winrm.exposure
    - windows.http.observation
