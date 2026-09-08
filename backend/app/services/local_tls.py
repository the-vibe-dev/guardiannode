"""Built-in family CA and renewable trusted-LAN server certificate."""
from __future__ import annotations

import ipaddress
import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app import settings as settings_mod
from app.services import encryption

_CA_AAD = b"GuardianNode family TLS CA key v1"
_LEAF_AAD = b"GuardianNode TLS leaf key v1"
_WORD_COUNT = 8


def _restricted_write(path, data: bytes) -> None:  # noqa: ANN001
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _new_ca() -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "GuardianNode Family CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return cert, key


def _load_or_create_ca() -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    settings = settings_mod.settings
    if settings.tls_ca_cert_path.exists() and settings.tls_ca_key_path.exists():
        cert = x509.load_pem_x509_certificate(settings.tls_ca_cert_path.read_bytes())
        raw = encryption.decrypt_bytes(settings.tls_ca_key_path.read_bytes(), aad=_CA_AAD)
        key = serialization.load_pem_private_key(raw, password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise RuntimeError("family CA key has an invalid type")
        return cert, key
    cert, key = _new_ca()
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    _restricted_write(settings.tls_ca_key_path, encryption.encrypt_bytes(private, aad=_CA_AAD))
    _restricted_write(settings.tls_ca_cert_path, cert.public_bytes(serialization.Encoding.PEM))
    return cert, key


def _sans() -> list[x509.GeneralName]:
    settings = settings_mod.settings
    configured = [
        *settings.effective_allowed_hosts(),
        *(part.strip() for part in settings.tls_san_hosts.split(",") if part.strip()),
        settings.bind_host,
        socket.gethostname(),
    ]
    names: list[x509.GeneralName] = []
    seen: set[str] = set()
    for raw in configured:
        host = raw.strip().strip("[]")
        if not host or host in {"*", "testserver", "0.0.0.0", "::"} or host in seen:
            continue
        seen.add(host)
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            names.append(x509.DNSName(host.lower()))
    return names


def ensure_server_certificate(*, renew_before_days: int = 30) -> tuple[str, str]:
    settings = settings_mod.settings
    ca_cert, ca_key = _load_or_create_ca()
    if settings.tls_cert_path.exists() and settings.tls_key_path.exists():
        cert = x509.load_pem_x509_certificate(settings.tls_cert_path.read_bytes())
        expires = cert.not_valid_after_utc
        expected = {str(item.value) for item in _sans()}
        actual = {str(item.value) for item in cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value}
        if expires > datetime.now(UTC) + timedelta(days=renew_before_days) and expected == actual:
            return str(settings.tls_cert_path), str(_materialize_leaf_key())

    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(UTC)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "guardiannode.local")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName(_sans()), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    _restricted_write(settings.tls_cert_path, cert.public_bytes(serialization.Encoding.PEM))
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    _restricted_write(settings.tls_key_path, encryption.encrypt_bytes(private, aad=_LEAF_AAD))
    return str(settings.tls_cert_path), str(_materialize_leaf_key())


def _materialize_leaf_key():  # noqa: ANN201
    """Create the short-lived key file required by uvicorn's path-only TLS API."""
    settings = settings_mod.settings
    raw = settings.tls_key_path.read_bytes()
    if raw.startswith(b"-----BEGIN"):
        # One-time migration from the beta's plaintext leaf-key storage.
        private = raw
        _restricted_write(settings.tls_key_path, encryption.encrypt_bytes(private, aad=_LEAF_AAD))
    else:
        private = encryption.decrypt_bytes(raw, aad=_LEAF_AAD)
    runtime = settings.tls_dir / f".server-key.{os.getpid()}.runtime.pem"
    _restricted_write(runtime, private)
    return runtime


def cleanup_runtime_key(path: str) -> None:
    candidate = settings_mod.settings.tls_dir / Path(path).name
    if candidate.parent == settings_mod.settings.tls_dir and candidate.name.endswith(".runtime.pem"):
        candidate.unlink(missing_ok=True)


def ca_fingerprint() -> str:
    cert, _key = _load_or_create_ca()
    return cert.fingerprint(hashes.SHA256()).hex()


def fingerprint_words() -> list[str]:
    digest = bytes.fromhex(ca_fingerprint())
    # Stable spoken groups without relying on locale or an online word service.
    return [f"gn-{value:02x}" for value in digest[:_WORD_COUNT]]


def ca_pem() -> str:
    _load_or_create_ca()
    return settings_mod.settings.tls_ca_cert_path.read_text("ascii")
