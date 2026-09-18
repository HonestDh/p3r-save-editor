"""Persona 3 Reload save (de)obfuscation + GVAS container support.

Save files (SaveDataNNN.sav) are Unreal Engine GVAS files wrapped in a simple
obfuscation: every byte is XORed with a repeating 31-byte key and then two
2-bit fields are swapped (bits 4..5 with bits 0..1).  The transform is its own
inverse for the bit swap, so decode/encode differ only in the order of XOR.
"""

KEY = b"ae5zeitaix1joowooNgie3fahP5Ohph"

GVAS_MAGIC = b"GVAS"


def _swap_bits(byte: int) -> int:
    return ((byte >> 4) & 3) | ((byte & 3) << 4) | (byte & 0xCC)


def decode(raw: bytes) -> bytes:
    """Turn an on-disk .sav blob into a plain Unreal GVAS buffer."""
    key = KEY
    key_len = len(key)
    out = bytearray(len(raw))
    for i, byte in enumerate(raw):
        out[i] = _swap_bits(byte ^ key[i % key_len])
    return bytes(out)


def encode(gvas: bytes) -> bytes:
    """Turn a plain GVAS buffer back into the on-disk representation."""
    key = KEY
    key_len = len(key)
    out = bytearray(len(gvas))
    for i, byte in enumerate(gvas):
        out[i] = _swap_bits(byte) ^ key[i % key_len]
    return bytes(out)


def looks_like_gvas(data: bytes) -> bool:
    return data[:4] == GVAS_MAGIC
