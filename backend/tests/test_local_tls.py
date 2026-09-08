from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app import settings as settings_mod
from app.services import local_tls


def test_family_tls_creates_private_ca_and_expected_server_sans():
    settings_mod.settings.allowed_hosts = "127.0.0.1,localhost,guardiannode.local"
    certificate_path, key_path = local_tls.ensure_server_certificate()
    cert = x509.load_pem_x509_certificate(open(certificate_path, "rb").read())
    ca_cert = x509.load_pem_x509_certificate(
        settings_mod.settings.tls_ca_cert_path.read_bytes()
    )
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    ca_subject_key = ca_cert.extensions.get_extension_for_class(
        x509.SubjectKeyIdentifier
    ).value
    ca_authority_key = ca_cert.extensions.get_extension_for_class(
        x509.AuthorityKeyIdentifier
    ).value
    server_authority_key = cert.extensions.get_extension_for_class(
        x509.AuthorityKeyIdentifier
    ).value
    server_key_usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value

    assert settings_mod.settings.tls_ca_cert_path.is_file()
    assert settings_mod.settings.tls_ca_key_path.is_file()
    assert "guardiannode.local" in sans.get_values_for_type(x509.DNSName)
    assert "localhost" in sans.get_values_for_type(x509.DNSName)
    assert "127.0.0.1" in [str(value) for value in sans.get_values_for_type(x509.IPAddress)]
    assert ca_authority_key.key_identifier == ca_subject_key.digest
    assert server_authority_key.key_identifier == ca_subject_key.digest
    assert server_key_usage.digital_signature is True
    assert server_key_usage.key_cert_sign is False
    assert len(local_tls.ca_fingerprint()) == 64
    assert len(local_tls.fingerprint_words()) == 8
    assert open(key_path, "rb").read().startswith(b"-----BEGIN PRIVATE KEY-----")
    assert not settings_mod.settings.tls_key_path.read_bytes().startswith(b"-----BEGIN")


def test_family_tls_reuses_unexpired_matching_leaf():
    first = local_tls.ensure_server_certificate()
    first_bytes = open(first[0], "rb").read()
    second = local_tls.ensure_server_certificate()
    assert second == first
    assert open(second[0], "rb").read() == first_bytes
    local_tls.cleanup_runtime_key(second[1])
    assert not settings_mod.settings.tls_key_path.read_bytes().startswith(b"-----BEGIN")


def test_family_tls_renews_legacy_leaf_without_authority_key_identifier():
    first = local_tls.ensure_server_certificate()
    local_tls.cleanup_runtime_key(first[1])
    ca_bytes = settings_mod.settings.tls_ca_cert_path.read_bytes()
    ca_fingerprint = local_tls.ca_fingerprint()
    ca_cert, ca_key = local_tls._load_or_create_ca()
    legacy_key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(UTC)
    legacy = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "guardiannode.local")])
        )
        .issuer_name(ca_cert.subject)
        .public_key(legacy_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName(local_tls._sans()), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    settings_mod.settings.tls_cert_path.write_bytes(
        legacy.public_bytes(serialization.Encoding.PEM)
    )

    renewed_path, runtime_key = local_tls.ensure_server_certificate()
    renewed = x509.load_pem_x509_certificate(open(renewed_path, "rb").read())
    authority_key = renewed.extensions.get_extension_for_class(
        x509.AuthorityKeyIdentifier
    ).value
    expected = x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key())

    assert renewed.serial_number != legacy.serial_number
    assert authority_key.key_identifier == expected.key_identifier
    assert settings_mod.settings.tls_ca_cert_path.read_bytes() == ca_bytes
    assert local_tls.ca_fingerprint() == ca_fingerprint
    local_tls.cleanup_runtime_key(runtime_key)
