# Secure LAN Setup

GuardianNode alpha deployments are intended for a single machine, a trusted home
LAN, or a trusted VPN. Do not expose the backend directly to the public internet.

## Safest Alpha Option

Single-machine mode is the safest alpha setup. The Windows agent, backend,
dashboard, Ollama, database, and encryption key all stay on one machine and the
backend can bind to `127.0.0.1`.

## Trusted Home LAN Assumptions

Separated mode sends child-device events to the parent-owned backend over HTTPS
using GuardianNode's local family CA. Use it only on a trusted LAN or VPN during
alpha testing; TLS authenticates and encrypts the connection but does not turn
the backend into a public-internet service.

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

The server installer creates a private CA and certificate containing the
configured IP/host names. In the dashboard, **Devices → Add device** exports a
short-lived `.gnpair` file. Transfer that file privately, compare the displayed
CA check words, and select it in the child installer. The agent stores the CA in
its protected directory and refuses the wrong issuer, fingerprint, URL, or an
expired bundle.

Plain HTTP is rejected beyond loopback. The loopback-only development exception
must use development mode and must never carry real family data:

```text
GUARDIANNODE_DEV_MODE=true
GUARDIANNODE_TLS_ENABLED=false
```

## Remote Access

Recommended options:

- Tailscale
- WireGuard
- Another trusted VPN that keeps the backend off the public internet

Avoid public port-forwarding to the backend.

## Reverse Proxies

Advanced users may place GuardianNode behind a trusted reverse proxy, but the
child agent must be enrolled with that proxy's exact trusted CA and URL. Keep
the backend itself firewalled from the public internet.

## Remaining Transport Work

Mutual TLS and per-device client certificates remain future work. Treat the
backend as a local/private service even though server-authenticated TLS is built in.
