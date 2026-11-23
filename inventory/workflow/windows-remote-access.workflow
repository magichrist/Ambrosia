name: Windows Remote Access
description: Remote access commands grouped by authentication method and client type.
phases:
  credentials:
    - windows.evil-winrm
    - windows.impacket-psexec
    - windows.impacket-wmiexec
    - windows.cme-smb-hash
  desktop:
    - windows.xfreerdp-pth
    - windows.rdesktop-nla
  utilities:
    - windows.winexe
    - windows.cme-smb-exec
