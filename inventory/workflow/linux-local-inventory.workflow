name: Linux Local Inventory
description: Local host facts and filesystem checks on Linux systems.
phases:
  system:
    - linux.os-info
    - linux.listening-ports
    - linux.echo-shell-options
  filesystem:
    - linux.find-writable-sh
    - linux.strings-btmp
    - linux.grep-uppercase
