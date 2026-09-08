from __future__ import annotations

from cryptography import x509

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
