name: Web Service Inventory
description: HTTP inspection and site-content commands for web services.
phases:
  inspect:
    - linux.http.observation
    - linux.http-get
    - linux.nmap-http-methods
  content:
    - linux.cewl
