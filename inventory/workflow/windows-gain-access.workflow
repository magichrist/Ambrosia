name: Windows Gain Access
description: Authorized Windows access assessment chain.
phases:
  reconnaissance:
    - windows.smb.audit
    - windows.nmap.discovery
    - windows.ldap.inventory
  exposure:
    - windows.rdp.exposure
    - windows.winrm.exposure
