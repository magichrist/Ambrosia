# Windows assessment pack — actions

Pack id: `windows-assessment`  
Version: 1.0.0  
All actions are read-only and declare `network_observe` as their effect.
See `docs/limitations.md` for the explicit safety boundary and per-module
limitations.

## Actions

| Action ID | Declares target scope field | Required artifact (same target) | Output artifact types |
|---|---|---|---|
| `network.nmap.service_discovery` | `target` | none | `network.service`, `network.host`, `observation` |
| `windows.smb.configuration_audit` | `target` | `network.service` where `service_name == smb` | `windows.domain`, `windows.host_role`, `observation` |
| `windows.ldap.domain_inventory` | `target` | `network.service` where `service_name == ldap` | `windows.domain`, `observation` |
| `windows.http.method_observation` | `target` | `network.service` where `service_name == http` | `observation` |
| `windows.rdp.exposure_observation` | `target` | `network.service` where `service_name == rdp` | `observation` |
| `windows.winrm.exposure_observation` | `target` | `network.service` where `service_name == winrm` | `observation` |

## How discovered artifacts drive further actions

Each service-discovery action requires a `network.service` artifact on the
same target, so the context matcher only surfaces it after discovery has
observed that service on the target:

1. Run `network.nmap.service_discovery` on an in-scope target.
2. If SMB (port 445) is discovered, a `network.service` artifact with
   `service_name == smb` is created; the matcher then offers
   `windows.smb.configuration_audit`.
3. If LDAP (port 389/636) is discovered, `windows.ldap.domain_inventory` is
   offered.
4. If HTTP (port 80/443/8080) is discovered, `windows.http.method_observation`
   is offered.
5. If RDP (port 3389) is discovered, `windows.rdp.exposure_observation` is
   offered.
6. If WinRM (port 5985/5986) is discovered, `windows.winrm.exposure_observation`
   is offered.

The SMB audit, in turn, produces `windows.domain` and `windows.host_role`
artifacts, which can unlock domain-level actions in future packs.

## Example discovery preset

See `examples/basic_discovery_preset.yaml` for a declarative preset that runs
bounded service discovery and lists the follow-up actions each discovered
service would suggest.
