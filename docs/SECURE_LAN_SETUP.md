# Secure LAN Setup

GuardianNode alpha deployments are intended for a single machine, a trusted home
LAN, or a trusted VPN. Do not expose the backend directly to the public internet.

## Safest Alpha Option

Single-machine mode is the safest alpha setup. The Windows agent, backend,
dashboard, Ollama, database, and encryption key all stay on one machine and the
backend can bind to `127.0.0.1`.

## Trusted Home LAN Assumptions

Separated mode sends child-device events to the parent-owned backend over the
local network. Unless you add TLS or a VPN, this traffic is local-network HTTP.
Use separated mode only on a trusted LAN during alpha testing.

Fresh native installs bind to `127.0.0.1` until first-run setup is complete. The
alpha does not yet include dashboard network controls; enabling LAN access is a
manual administrator step described in the server + child install guide.

When you deliberately enable LAN access, set both the bind address and the exact
trusted hostnames/IPs. Do not use `*` outside development mode.

```text
GUARDIANNODE_BIND_HOST=0.0.0.0
GUARDIANNODE_ALLOWED_HOSTS=192.168.1.42,guardian-server,127.0.0.1,localhost
```

Replace `192.168.1.42` and `guardian-server` with the actual LAN address and
hostname that child agents will use. The backend rejects unlisted Host headers.

Plain HTTP lab mode does not encrypt dashboard credentials, cookies, device
tokens, screenshots, or metadata in transit. For any deployment beyond a
temporary trusted lab, put the backend behind HTTPS or a trusted VPN and set:

```text
GUARDIANNODE_HTTPS_ONLY_COOKIES=true
```

## Remote Access

Recommended options:

- Tailscale
- WireGuard
- Another trusted VPN that keeps the backend off the public internet

Avoid public port-forwarding to the backend.

## Reverse Proxy TLS

Advanced users can place GuardianNode behind a trusted reverse proxy that
terminates TLS and restricts access to known devices or VPN clients. Keep the
backend itself firewalled from the public internet.

## Future Work

Built-in TLS, mTLS, and device certificates are planned. Until those are built
and tested, treat the backend as a local/private service.
