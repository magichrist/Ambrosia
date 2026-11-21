name: Windows Full Chain
description: Comprehensive authorized Windows assessment workflow.
phases:
  phase 1:
    - windows.basic-discovery
    - windows.smb.audit
    - windows.nmap.discovery
  phase 2:
    - windows.ldap.inventory
    - windows.rdp.exposure
    - windows.winrm.exposure
    - windows.http.observation
