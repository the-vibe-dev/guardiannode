from __future__ import annotations

import ssl
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from src import pairing_client
from src.backend_client import BackendClient
from src.family_tls import family_ca_ssl_context


def _ca_pem(*, legacy: bool, common_name: str = "GuardianNode Family CA") -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
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
    )
    if not legacy:
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        ).add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),
            critical=False,
        )
    return builder.sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)


def _assert_verification_stays_enabled(context: ssl.SSLContext) -> None:
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    partial_chain = getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    if partial_chain:
        assert context.verify_flags & partial_chain


def test_legacy_family_ca_clears_only_strict_shape_check(tmp_path):
    ca_path = tmp_path / "family-ca.pem"
    ca_path.write_bytes(_ca_pem(legacy=True))

    baseline = ssl.create_default_context(cafile=str(ca_path))
    context = family_ca_ssl_context(ca_path)

    _assert_verification_stays_enabled(context)
    strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
    assert context.verify_flags == baseline.verify_flags & ~strict


def test_current_family_ca_retains_default_strict_flags(tmp_path):
    ca_path = tmp_path / "family-ca.pem"
    ca_path.write_bytes(_ca_pem(legacy=False))

    baseline = ssl.create_default_context(cafile=str(ca_path))
    context = family_ca_ssl_context(ca_path)

    _assert_verification_stays_enabled(context)
    assert context.verify_flags == baseline.verify_flags


def test_unrecognized_legacy_shaped_ca_retains_default_strict_flags(tmp_path):
    ca_path = tmp_path / "other-ca.pem"
    ca_path.write_bytes(_ca_pem(legacy=True, common_name="Other Private CA"))

    baseline = ssl.create_default_context(cafile=str(ca_path))
    context = family_ca_ssl_context(ca_path)

    _assert_verification_stays_enabled(context)
    assert context.verify_flags == baseline.verify_flags


def test_runtime_and_pairing_clients_share_family_ca_context(tmp_path):
    ca_path = tmp_path / "family-ca.pem"
    ca_path.write_bytes(_ca_pem(legacy=True))

    runtime = BackendClient("https://server.test:8787", "token", ca_path=ca_path)._verify()
    pairing = pairing_client._transport_verify(
        "https://server.test:8787", ca_path, allow_loopback_http=False
    )

    assert isinstance(runtime, ssl.SSLContext)
    assert isinstance(pairing, ssl.SSLContext)
    _assert_verification_stays_enabled(runtime)
    _assert_verification_stays_enabled(pairing)
