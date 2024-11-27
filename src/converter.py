from base64 import b64decode
from hashlib import sha256
from Crypto.Hash import RIPEMD160

def pubkey_to_consensus_hex(pub_key):
    pubkey_bytes = b64decode(pub_key)
    sha256_digest = sha256(pubkey_bytes).digest()
    ripemd160 = RIPEMD160.new()
    ripemd160.update(sha256_digest)
    ripemd160_digest = ripemd160.digest()
    consensus_hex = ''.join(format(byte, '02x') for byte in ripemd160_digest).upper()
    return consensus_hex