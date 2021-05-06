from pathlib import Path
from typing import Tuple
import random
from OpenSSL import crypto


def get_or_create_root_cert(work_dir: Path, webhook_hostname: str) -> Tuple[Path, Path]:
    cert_dir = work_dir / 'certs'
    cert_dir.mkdir(0o700, exist_ok=True)
    keypath = cert_dir / f'{webhook_hostname}-pkey.pem'
    certpath = cert_dir / f'{webhook_hostname}-cert.pem'
    if not (keypath.exists() and certpath.exists()):
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, 2048)

        cert = crypto.X509()
        cert.get_subject().C = "UK"
        cert.get_subject().ST = "London"
        cert.get_subject().L = "London"
        cert.get_subject().O = "Dummy Company Ltd"
        cert.get_subject().OU = "Dummy Company Ltd"
        cert.get_subject().CN = webhook_hostname
        cert.set_serial_number(random.randint(100000, 999999))
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(k)
        cert.sign(k, 'sha1')
        with open(certpath, "wb") as f:
            f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        with open(keypath, "wb") as f:
            f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
    return certpath, keypath
