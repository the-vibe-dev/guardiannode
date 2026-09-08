"""TLS context for an explicitly enrolled GuardianNode family CA."""
from __future__ import annotations

import ssl
from pathlib import Path

from cryptography import x509
from cryptography.x509.oid import NameOID


def _is_legacy_family_ca(cert: x509.Certificate) -> bool:
    """Recognize the exact CA shape emitted by early GuardianNode betas."""
    if cert.subject != cert.issuer:
        return False
    common_names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(common_names) != 1 or common_names[0].value != "GuardianNode Family CA":
        return False
    try:
        constraints = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        key_usage = cert.extensions.get_extension_for_class(x509.KeyUsage)
    except x509.ExtensionNotFound:
        return False
    if (
        not constraints.critical
        or not constraints.value.ca
        or constraints.value.path_length != 0
        or not key_usage.critical
        or not key_usage.value.key_cert_sign
        or not key_usage.value.crl_sign
    ):
        return False
    try:
        cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
    except x509.ExtensionNotFound:
        pass
    else:
        return False
    try:
        cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
    except x509.ExtensionNotFound:
        return True
    return False


def family_ca_ssl_context(ca_path: str | Path) -> ssl.SSLContext:
    """Build a verifying client context for an enrolled family CA.

    Python 3.13 enables OpenSSL strict certificate-shape checks. Early beta
    family roots lack SKI/AKI, so strict mode rejects them even after their
    server leaf is renewed. Only that exact legacy CA shape receives the
    compatibility flag; CA-chain, expiry, and hostname verification stay on.
    """
    path = Path(ca_path)
    context = ssl.create_default_context(cafile=str(path))
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict_flag:
        cert = x509.load_pem_x509_certificate(path.read_bytes())
        if _is_legacy_family_ca(cert):
            context.verify_flags &= ~strict_flag
    return context
