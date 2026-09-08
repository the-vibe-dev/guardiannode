# Device Pairing

Used in separated mode to link a child device's agent to the parent's server.

## How pairing actually executes

The parent starts pairing in **Devices**, downloads the short-lived `.gnpair`
trust bundle, and privately transfers it to the child PC. The child installer
writes a protected `pending_pairing.json` containing the exact HTTPS server URL,
6-digit code, and bundle path (or a purpose-bound local bootstrap for all-in-one
installs). The SYSTEM GuardianNode Endpoint Broker reads this transaction and
stores the resulting CA and device credential in broker-owned storage:

- If broker-owned `Secure\device.json` or legacy `device.json` already holds a
  token, the pending file is ignored.
- The bundle must be current, name the exact server URL, contain a currently
  valid CA certificate, and match its SHA-256 fingerprint. mDNS remains advisory.
- Transient failures (server still booting) retry 5 times, 10s apart, then
  leave the file in place for the next agent start.
- A definitive pairing-code rejection (HTTP 4xx) deletes the file — codes are
  single-use and expire in 10 minutes, so retrying one forever is pointless.
- A local-bootstrap authorization failure leaves the file in place so an
  installer repair can issue a fresh device-bootstrap token and resume
  enrollment.

Manual source pairing is also available:

```powershell
GuardianNodeAgent.exe --pair --pair-bundle C:\SafeTransfer\family.gnpair --code 123456
```

`--server` may be supplied as an additional exact-URL check. HTTP is accepted
only for an explicit loopback source-development flow.

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
       │ display code, URL, CA words, bundle            │
       │                                                │
       │ parent transfers bundle and code to child PC   │
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

- Format: `gn_dev_<device_id>_<random_secret>` (the embedded device id provides
  one bounded lookup instead of scanning all devices)
- Stored on child device at `C:\ProgramData\GuardianNode\device.json` in legacy
  source-agent mode, or broker-owned secure storage in current public-alpha
  installer mode. The ProgramData ACL model was validated for the Windows 11
  public alpha installers and must be revalidated before each public installer
  release.
- Used in `Authorization: Bearer <token>` header for all subsequent API calls
- Backend stores only an HMAC-SHA256 digest under a separate server-only pepper.
  The family-beta migration revokes legacy Argon2 device credentials, requiring
  a one-time re-pair.
- Invalid-token requests are rate-limited per source IP
- Revokable from the dashboard (Devices → ⋮ → Revoke)

## mDNS discovery

The backend can advertise `_guardiannode._tcp.local` with TXT records:
- `version=0.1.0-alpha.3`
- `path=/api`

mDNS is not trusted for automatic pairing. If the agent has no configured
backend URL and discovers a GuardianNode server, it still refuses to pick it
automatically. A hostile or messy LAN could advertise a fake service. The parent
must set the server URL explicitly. After pairing, the paired backend URL is
stored in `device.json`, logged, and shown in the tray menu diagnostics.

## Manual fallback

Type the URL and pairing code by hand.

## Trust bundle

The `.gnpair` bundle is the out-of-band server identity handoff. It contains no
device bearer token, but it is short-lived and should still be transferred
privately. Compare the human-readable CA words on both screens before continuing.

## Failure modes

- Code expired → backend returns 410 Gone; wizard shows "Code expired, generate a new one"
- Code invalid → 400 Bad Request
- Network unreachable → wizard offers a "Retry" button and shows the manual fallback

## Audit

Every pairing attempt (successful and failed) is logged to `audit_logs` with timestamp, source IP, and result.
