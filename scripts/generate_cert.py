'''
File:   generate_cert.py
Brief:  Self-signed TLS certificate for serving the stand over HTTPS
        (voice input on iOS/Safari requires a secure context).
Author: Mistress-Lukutar
Date:   2026-11-28
Version: v0.1.0

Web Speech API recognition (the microphone button in the chat) only
works in a secure context. When the stand is opened from a phone as
``http://<lan-ip>:8011``, Safari never asks for microphone access and
the button fails. Serving the same stand over HTTPS unlocks it.

The script generates a self-signed RSA certificate + private key into
``certs/`` (gitignored) with subject alternative names for localhost,
127.0.0.1 and every ``--host`` address passed on the command line
(typically the LAN IP of the computer running the stand).

Usage (from the repository root):

    python scripts/generate_cert.py                       # localhost only
    python scripts/generate_cert.py --host 192.168.1.42   # + LAN IP
    python scripts/generate_cert.py --host 192.168.1.42 --host 10.0.0.5

Then start the stand with the SSL env vars (see README,
"Голосовой ввод с телефона"):

    SSL_CERTFILE=certs/dev-cert.pem SSL_KEYFILE=certs/dev-key.pem scripts/start.sh
'''

from __future__ import annotations

import argparse
import ipaddress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

DEFAULT_OUTPUT_DIR = Path("certs")
DEFAULT_DAYS = 825
DEFAULT_HOSTS = ("localhost", "127.0.0.1")


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a self-signed TLS certificate for the stand. "
            "Voice input on iOS/Safari requires HTTPS (secure context)."
        ),
    )
    parser.add_argument(
        "--host",
        action="append",
        default=[],
        help="extra address for the certificate SANs (repeatable, "
        "e.g. the LAN IP of this computer)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="output directory (default: %(default)s)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="certificate lifetime in days (default: %(default)s)",
    )
    return parser


def _build_san(hosts: list[str]) -> x509.SubjectAlternativeName:
    """Collect subject alternative names from the default and extra hosts.

    Args:
        hosts: Extra addresses; DNS names and IP literals are both accepted.

    Returns:
        A SAN extension listing every unique address.
    """
    dns_names: list[x509.DNSName] = []
    ip_addresses: list[x509.IPAddress] = []
    for name in [*DEFAULT_HOSTS, *hosts]:
        try:
            addr = ipaddress.ip_address(name)
        except ValueError:
            entry = x509.DNSName(name)
            if entry not in dns_names:
                dns_names.append(entry)
        else:
            entry = x509.IPAddress(addr)
            if entry not in ip_addresses:
                ip_addresses.append(entry)
    return x509.SubjectAlternativeName([*dns_names, *ip_addresses])


def generate_certificate(
    out_dir: Path, hosts: list[str], days: int
) -> tuple[Path, Path]:
    """Generate a self-signed server certificate and private key.

    Args:
        out_dir: Directory to write ``dev-cert.pem`` / ``dev-key.pem`` into.
        hosts: Extra addresses for the subject alternative names.
        days: Certificate lifetime in days.

    Returns:
        Paths of the written (certificate, private key) files.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "Digital Mechanic Dev"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Digital Mechanic"),
        ]
    )
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(_build_san(hosts), critical=False)
        .sign(key, hashes.SHA256())
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    cert_path = out_dir / "dev-cert.pem"
    key_path = out_dir / "dev-key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    try:  # best effort: restrict the key on POSIX
        key_path.chmod(0o600)
    except OSError:
        pass
    return cert_path, key_path


def main() -> int:
    """Run the generator and print follow-up instructions."""
    args = build_argument_parser().parse_args()
    cert_path, key_path = generate_certificate(args.out, args.host, args.days)
    print(f"[generate_cert] certificate: {cert_path}")
    print(f"[generate_cert] private key:  {key_path}")
    print(
        "[generate_cert] start the stand over HTTPS:\n"
        "  bash:  SSL_CERTFILE=... SSL_KEYFILE=... scripts/start.sh\n"
        "  cmd:   set SSL_CERTFILE=... & set SSL_KEYFILE=... & scripts\\start.bat"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
