from base64 import b64decode
from hashlib import sha256
from Crypto.Hash import RIPEMD160

def pubkey_to_hex(pub_key: str, key_type: str) -> str:
    """
    Converts a public key to its consensus hex representation based on the key type.

    Args:
        pub_key (str): The base64-encoded public key.
        key_type (str): The type of the public key. Supported types:
                        - "/cosmos.crypto.secp256k1.PubKey"
                        - "/cosmos.crypto.ed25519.PubKey"
    
    Returns:
        str: The consensus hex representation of the public key.
    """
    pubkey_bytes = b64decode(pub_key)

    if key_type == "/cosmos.crypto.secp256k1.PubKey":
        sha256_digest = sha256(pubkey_bytes).digest()
        ripemd160 = RIPEMD160.new()
        ripemd160.update(sha256_digest)
        ripemd160_digest = ripemd160.digest()
        consensus_hex = ''.join(format(byte, '02x') for byte in ripemd160_digest).upper()

    elif key_type == "/cosmos.crypto.ed25519.PubKey":
        sha256_digest = sha256(pubkey_bytes).digest()
        consensus_hex = ''.join(format(byte, '02x') for byte in sha256_digest).upper()

    else:
        raise ValueError(f"Unsupported key type: {key_type}")

    return consensus_hex