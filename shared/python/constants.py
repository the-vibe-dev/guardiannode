"""Constants used across backend and agent."""

DEFAULT_MONITORED_APPS = [
    "Roblox.exe",
    "Discord.exe",
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "outlook.exe",
    "Teams.exe",
    "Steam.exe",
    "EpicGamesLauncher.exe",
    "MinecraftLauncher.exe",
    "javaw.exe",  # Minecraft Java
]

DEFAULT_MONITORED_DOMAINS = [
    "mail.google.com",
    "outlook.live.com",
    "outlook.office.com",
    "discord.com",
    "roblox.com",
    "tiktok.com",
]

MDNS_SERVICE_TYPE = "_guardiannode._tcp.local."
MDNS_DEFAULT_PORT = 8787

API_VERSION = "0.1.0"
AGENT_VERSION = "0.1.0"
PROTOCOL_VERSION = "0.1.0"

DEFAULT_BACKEND_PORT = 8787
DEFAULT_AGENT_PORT = 8765
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

PAIRING_CODE_TTL_SECONDS = 600
PAIRING_CODE_LENGTH = 6

PASSWORD_MIN_LENGTH = 10
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST_KB = 65536
ARGON2_PARALLELISM = 4

RECOVERY_CODE_WORDS = 12  # BIP39-style

ENCRYPTION_KEY_VERSION = 1
ENCRYPTION_ALGO = "AES-256-GCM"

DEFAULT_RETENTION_DAYS = {
    "critical": 90,
    "high": 90,
    "medium": 30,
    "low": 1,
    "screenshots_flagged": 30,
    "ocr_cache": 1,
    "audit_logs": 180,
}
