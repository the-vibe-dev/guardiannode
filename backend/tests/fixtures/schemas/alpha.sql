CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  display_name VARCHAR(128),
  password_hash VARCHAR(256),
  recovery_hash VARCHAR(256),
  role VARCHAR(32),
  created_at DATETIME,
  last_login DATETIME
);
INSERT INTO users (
  id, display_name, password_hash, recovery_hash, role, created_at
) VALUES (
  1, 'Existing Parent', 'password-hash', 'recovery-hash', 'admin', '2026-01-01'
);
