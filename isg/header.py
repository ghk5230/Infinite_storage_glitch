"""Metadata header stored in frame 0 of every ISG video.

The header frame always uses HEADER_BLOCK-sized blocks and HEADER_NSYM
parity, regardless of the payload settings, so the decoder can bootstrap
without knowing anything about the file. It carries the payload's encoding
parameters, length, filename, and a SHA-256 for end-to-end verification.
"""

import struct
from dataclasses import dataclass

from . import ecc

MAGIC = b"ISG1"
VERSION = 1
HEADER_BLOCK = 8
HEADER_NSYM = 64
FNAME_FIELD = 256

FLAG_ENCRYPTED = 0x01

# magic, version, block, nsym, flags, payload_len, payload_frames, sha256, fname_len
_FMT = "<4sBBBBQI32sH"
_FIXED_LEN = struct.calcsize(_FMT) + FNAME_FIELD  # 310 bytes
ENCODED_LEN = ecc.encoded_len(_FIXED_LEN, HEADER_NSYM)  # 438 bytes


@dataclass
class Header:
    block: int
    nsym: int
    payload_len: int
    payload_frames: int
    sha256: bytes
    filename: str
    flags: int = 0

    @property
    def encrypted(self) -> bool:
        return bool(self.flags & FLAG_ENCRYPTED)


def build(hdr: Header) -> bytes:
    fname = hdr.filename.encode("utf-8")[:FNAME_FIELD]
    raw = struct.pack(
        _FMT,
        MAGIC,
        VERSION,
        hdr.block,
        hdr.nsym,
        hdr.flags,
        hdr.payload_len,
        hdr.payload_frames,
        hdr.sha256,
        len(fname),
    ) + fname.ljust(FNAME_FIELD, b"\x00")
    return ecc.encode(raw, HEADER_NSYM)


def parse(frame_bytes: bytes) -> Header:
    """Parse a header from the decoded bytes of frame 0."""
    try:
        raw = ecc.decode(frame_bytes[:ENCODED_LEN], HEADER_NSYM)
    except ecc.ReedSolomonError as e:
        raise ValueError("header copy unrecoverable") from e
    magic, version, block, nsym, flags, payload_len, payload_frames, sha256, fname_len = struct.unpack(
        _FMT, raw[: struct.calcsize(_FMT)]
    )
    if magic != MAGIC:
        raise ValueError("bad magic bytes: not an ISG video")
    if version != VERSION:
        raise ValueError(f"unsupported ISG version {version}")
    if block <= 0:
        raise ValueError("invalid header: block size must be greater than zero")
    if not 1 <= nsym < 255:
        raise ValueError("invalid header: nsym must be between 1 and 254")
    if payload_len == 0:
        raise ValueError("invalid header: payload length is zero")
    if payload_frames == 0:
        raise ValueError("invalid header: payload frame count is zero")
    if fname_len > FNAME_FIELD:
        raise ValueError("invalid header: filename is too long")
    fname = raw[struct.calcsize(_FMT):][:fname_len].decode("utf-8", errors="replace")
    return Header(block, nsym, payload_len, payload_frames, sha256, fname, flags)
