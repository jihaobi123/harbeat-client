"""NCM (NetEase Cloud Music) encrypted file decryption.

Port of electron/ncmDecrypt.ts to Python using pycryptodome.
Supports .ncm files with AES-128-ECB key decryption and modified RC4 stream cipher.
"""
from __future__ import annotations

import json
import os
import struct
import tempfile

from Crypto.Cipher import AES


# NCM encryption constants
CORE_KEY = bytes([0x68, 0x7A, 0x48, 0x52, 0x41, 0x6D, 0x73, 0x6F,
                  0x35, 0x6B, 0x49, 0x6E, 0x62, 0x61, 0x78, 0x57])

META_KEY = bytes([0x23, 0x31, 0x34, 0x6C, 0x6A, 0x6B, 0x5F, 0x21,
                  0x5C, 0x5D, 0x26, 0x30, 0x55, 0x3C, 0x27, 0x28])

MAGIC = bytes([0x43, 0x54, 0x45, 0x4E, 0x46, 0x44, 0x41, 0x4D])


def _unpad_pkcs7(data: bytes) -> bytes:
    if not data:
        return data
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        return data
    return data[:-pad_len]


def decrypt_ncm(ncm_path: str, output_dir: str | None = None) -> dict:
    """Decrypt a .ncm file and return audio info.

    Returns:
        dict with keys: audio_path, format, title, artist
    """
    with open(ncm_path, "rb") as f:
        buf = f.read()

    offset = 0

    # 1. Verify magic header
    if buf[offset:offset + 8] != MAGIC:
        raise ValueError("Not a valid NCM file (bad magic header)")
    offset += 10  # 8 bytes magic + 2 bytes padding

    # 2. Decrypt RC4 key with AES-128-ECB (CORE_KEY)
    key_len = struct.unpack_from("<I", buf, offset)[0]
    offset += 4
    key_data = bytearray(buf[offset:offset + key_len])
    offset += key_len

    # XOR each byte with 0x64
    for i in range(len(key_data)):
        key_data[i] ^= 0x64

    cipher_core = AES.new(CORE_KEY, AES.MODE_ECB)
    rc4_key = _unpad_pkcs7(cipher_core.decrypt(bytes(key_data)))
    # Skip "neteasecloudmusic" prefix (17 bytes)
    rc4_key = rc4_key[17:]

    # 3. Decrypt metadata with AES-128-ECB (META_KEY)
    meta_len = struct.unpack_from("<I", buf, offset)[0]
    offset += 4

    title = os.path.splitext(os.path.basename(ncm_path))[0]
    artist = "Unknown"
    detected_format = "mp3"

    if meta_len > 0:
        meta_data = bytearray(buf[offset:offset + meta_len])
        offset += meta_len

        # XOR each byte with 0x63
        for i in range(len(meta_data)):
            meta_data[i] ^= 0x63

        # Skip "163 key(Don't modify):" prefix, then base64 decode
        import base64
        meta_b64 = bytes(meta_data[22:])
        meta_encrypted = base64.b64decode(meta_b64)

        cipher_meta = AES.new(META_KEY, AES.MODE_ECB)
        meta_decrypted = _unpad_pkcs7(cipher_meta.decrypt(meta_encrypted))

        # Parse metadata JSON (skip "music:" prefix)
        try:
            meta_str = meta_decrypted.decode("utf-8")
            if meta_str.startswith("music:"):
                meta_str = meta_str[6:]
            meta_json = json.loads(meta_str)
            detected_format = meta_json.get("format", "mp3")
            title = meta_json.get("musicName", title)
            raw_artist = meta_json.get("artist", [])
            if isinstance(raw_artist, list) and raw_artist:
                artist = ", ".join(
                    a[0] if isinstance(a, (list, tuple)) else str(a)
                    for a in raw_artist
                )
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    else:
        offset += meta_len

    # 4. Skip CRC and album image
    offset += 5  # CRC32 (4) + padding (1)
    image_size = struct.unpack_from("<I", buf, offset)[0]
    offset += 4
    offset += image_size

    # 5. Build RC4 key stream (KSA)
    key_box = list(range(256))
    j = 0
    for i in range(256):
        j = (key_box[i] + j + rc4_key[i % len(rc4_key)]) & 0xFF
        key_box[i], key_box[j] = key_box[j], key_box[i]

    # 6. Decrypt audio data using modified RC4 stream cipher
    audio_data = bytearray(len(buf) - offset)
    for i in range(len(audio_data)):
        idx = (i + 1) & 0xFF
        si = key_box[idx]
        sj = key_box[(si + key_box[(idx + si) & 0xFF]) & 0xFF]
        audio_data[i] = buf[offset + i] ^ sj

    # 7. Auto-detect format from audio header
    if len(audio_data) > 4:
        if audio_data[:4] == b"fLaC":
            detected_format = "flac"
        elif audio_data[0] == 0xFF and (audio_data[1] & 0xE0) == 0xE0:
            detected_format = "mp3"
        elif audio_data[:3] == b"ID3":
            detected_format = "mp3"

    # 8. Write decrypted audio to output
    if output_dir is None:
        output_dir = os.path.join(tempfile.gettempdir(), "harbeat-ncm")
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(ncm_path))[0]
    out_path = os.path.join(output_dir, f"{base_name}.{detected_format}")
    with open(out_path, "wb") as f:
        f.write(audio_data)

    return {
        "audio_path": out_path,
        "format": detected_format,
        "title": title,
        "artist": artist,
    }
