# Device Pairing

Used in separated mode to link a child device's agent to the parent's server.

## How pairing actually executes

The installer never talks to the backend itself. It writes
`C:\ProgramData\GuardianNode\pending_pairing.json` containing the wizard's
server URL and 6-digit code (or `{"local_bootstrap": true}` for all-in-one
installs). On every start, the agent checks for this file before its main
loop (`pairing_client.bootstrap_pairing`):

- If `device.json` already holds a token, the pending file is ignored.
- If the URL is blank, the agent browses mDNS for `_guardiannode._tcp` and
  uses the first server found.
- Transient failures (server still booting) retry 5 times, 10s apart, then
  leave the file in place for the next agent start.
- A definitive rejection (HTTP 4xx) deletes the file — codes are single-use
  and expire in 10 minutes, so retrying one forever is pointless.

Manual pairing is also available:
`GuardianNodeAgent.exe --pair --server http://192.168.1.42:8787 --code 123456`

## Local bootstrap (all-in-one installs)

When agent and backend share one machine, there is no parent account yet at
install time, so no one can issue a code. `POST /api/devices/pair/complete`
therefore accepts `{"local_bootstrap": true}` **only** when both hold:

1. The request originates from loopback (127.0.0.1 / ::1), and
2. **Zero** devices are currently paired.

Once the first device pairs, this path closes permanently. Every use is
audit-logged with `local_bootstrap: true` in the details.

## Brute-force protection

`pair/complete` is rate-limited per source IP: 10 failed attempts per
15 minutes, then HTTP 429 with `Retry-After`. Combined with the 10-minute
TTL and single-use codes, online guessing of a 6-digit code is impractical.

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
       │                                                │ wizard: mDNS browse
       │                                                ├──► finds server
       │                                                │ enter 6-digit code
       │                     │◄─────────────────────────┤ POST /api/devices/pair
       │                     │ verify code              │
       │                     │ issue device_id + token  │
       │                     ├─────────────────────────►│
       │                                                │ store token (SYSTEM ACL)
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
- Stored on child device at `C:\ProgramData\GuardianNode\device.json`, SYSTEM-only ACL
- Used in `Authorization: Bearer <token>` header for all subsequent API calls
- Backend stores only the Argon2 hash of the secret
- Invalid-token requests are rate-limited per source IP
- Revokable from the dashboard (Devices → ⋮ → Revoke)

## mDNS discovery

The backend advertises `_guardiannode._tcp.local` with TXT records:
- `version=0.1.0`
- `path=/api`

The installer's mDNS browser shows discovered servers; parent picks one and enters the pairing code.

**Ambiguity rule:** if the agent has no configured backend URL and discovers
**more than one** GuardianNode server, it refuses to pick one automatically
(a hostile or messy LAN could advertise a fake service). The parent must set
the server URL explicitly in that case. After pairing, the paired backend URL
is stored in `device.json`, logged, and shown in the tray menu diagnostics.

## Manual fallback

If mDNS is blocked (some segmented Wi-Fi setups), parent types the URL + pairing code by hand.

## QR code

Encodes `guardiannode://pair?host=<ip>&port=<port>&code=<code>&fp=<cert-fingerprint>`. Usable post-install via the tray "Connect to server" flow.

## Failure modes

- Code expired → backend returns 410 Gone; wizard shows "Code expired, generate a new one"
- Code invalid → 400 Bad Request
- Network unreachable → wizard offers a "Retry" button and shows the manual fallback

## Audit

Every pairing attempt (successful and failed) is logged to `audit_logs` with timestamp, source IP, and result.
