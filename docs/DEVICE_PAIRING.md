# Device Pairing

Used in separated mode to link a child device's agent to the parent's server.

## How pairing actually executes

The installer never talks to the backend itself. It writes
`C:\ProgramData\GuardianNode\pending_pairing.json` containing the wizard's
server URL and 6-digit code (or `{"local_bootstrap": true}` for all-in-one
installs). In current broker-enabled builds, the GuardianNode Endpoint Broker
reads this file and stores the resulting device credential in broker-owned
storage. Legacy/source agent mode checks the same file before its main loop
(`pairing_client.bootstrap_pairing`):

- If broker-owned `Secure\device.json` or legacy `device.json` already holds a
  token, the pending file is ignored.
- The agent requires an explicit server URL. mDNS discovery is advisory only in
  this alpha because a LAN advertisement does not authenticate the parent server.
- Transient failures (server still booting) retry 5 times, 10s apart, then
  leave the file in place for the next agent start.
- A definitive pairing-code rejection (HTTP 4xx) deletes the file — codes are
  single-use and expire in 10 minutes, so retrying one forever is pointless.
- A local-bootstrap authorization failure leaves the file in place so an
  installer repair can issue a fresh device-bootstrap token and resume
  enrollment.

Manual pairing is also available:
`GuardianNodeAgent.exe --pair --server http://192.168.1.42:8787 --code 123456`

## Local bootstrap (all-in-one installs)

When agent and backend share one machine, there is no parent account yet at
install time, so no one can issue a code. `POST /api/devices/bootstrap-local`
accepts a purpose-bound `device_bootstrap_token` **only** when both hold:

1. The request originates from loopback (127.0.0.1 / ::1), and
2. **Zero** devices are currently paired.

The administrator setup token is never accepted at a device endpoint. Once the
first device pairs, the local-bootstrap path closes permanently. Every use is
audit-logged with `local_bootstrap: true` in the details.

## Brute-force protection

`pair/complete` and `bootstrap-local` are rate-limited per source IP: 10 failed
attempts per 15 minutes, then HTTP 429 with `Retry-After`. Combined with the
10-minute TTL and single-use codes, online guessing of a 6-digit code is
impractical.

## Flow

```
Parent dashboard          Backend                    Child PC
       │                     │                          │
       │ "Add Device"        │                          │
       ├────────────────────►│                          │
       │                     │ generate 6-digit code    │
       │                     │ TTL = 10 min             │
       │                     │ hash + store             │
       │◄────────────────────┤                          │
       │ display code+QR     │                          │
       │                                                │
       │ parent walks code over to child PC             │
       │                                                │
       │                                                │ enter server URL
       │                                                │ enter 6-digit code
       │                     │◄─────────────────────────┤ POST /api/devices/pair
       │                     │ verify code              │
       │                     │ issue device_id + token  │
       │                     ├─────────────────────────►│
       │                                                │ store token (ProgramData)
       │                                                │
       │ dashboard shows new device under "Devices"     │
```

## Pairing code

- 6 numeric digits
- Argon2-hashed at rest
- 10-minute TTL
- Single-use — invalidated after a successful pair

## Token

- Format: `gn_dev_<device_id>_<random_secret>` (the embedded device id lets the
  backend verify exactly one Argon2 hash per request instead of scanning all
  devices; legacy opaque tokens from older pairings keep working)
- Stored on child device at `C:\ProgramData\GuardianNode\device.json`. The
  current ProgramData ACL model must be validated on clean standard-user
  Windows installs before public installer distribution.
- Used in `Authorization: Bearer <token>` header for all subsequent API calls
- Backend stores only the Argon2 hash of the secret
- Invalid-token requests are rate-limited per source IP
- Revokable from the dashboard (Devices → ⋮ → Revoke)

## mDNS discovery

The backend can advertise `_guardiannode._tcp.local` with TXT records:
- `version=0.1.0-alpha.1`
- `path=/api`

mDNS is not trusted for automatic pairing. If the agent has no configured
backend URL and discovers a GuardianNode server, it still refuses to pick it
automatically. A hostile or messy LAN could advertise a fake service. The parent
must set the server URL explicitly. After pairing, the paired backend URL is
stored in `device.json`, logged, and shown in the tray menu diagnostics.

## Manual fallback

Type the URL and pairing code by hand.

## QR code

QR pairing is planned for a later fingerprint-pinning flow. In this alpha, type
the trusted server URL and pairing code explicitly.

## Failure modes

- Code expired → backend returns 410 Gone; wizard shows "Code expired, generate a new one"
- Code invalid → 400 Bad Request
- Network unreachable → wizard offers a "Retry" button and shows the manual fallback

## Audit

Every pairing attempt (successful and failed) is logged to `audit_logs` with timestamp, source IP, and result.
