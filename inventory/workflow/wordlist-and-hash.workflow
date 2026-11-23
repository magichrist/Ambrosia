name: Wordlist & Hash Utilities
description: Hash extraction, wordlist generation, and hash processing commands.
phases:
  extract:
    - windows.impacket-secretsdump
    - windows.impacket-dc-dump
    - windows.samdump2
  wordlists:
    - linux.crunch
    - linux.cewl
  hashes:
    - linux.hashcat-ntlm
    - linux.hashcat-shadow
    - linux.hashcat-show
