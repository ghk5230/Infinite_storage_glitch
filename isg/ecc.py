"""Reed-Solomon error correction layer.

RSCodec(nsym) splits the stream into codewords of (255 - nsym) data bytes
plus nsym parity bytes, and can correct up to nsym/2 corrupted bytes per
codeword. nsym=32 tolerates 16 bad bytes per 255 -- plenty for the residual
bit flips that survive the block-average decoding.
"""

import math

import numpy as np
from reedsolo import RSCodec, ReedSolomonError  # noqa: F401 (re-exported)


def _validate_nsym(nsym: int) -> None:
    if not 1 <= nsym < 255:
        raise ValueError("nsym must be between 1 and 254")


def encoded_len(data_len: int, nsym: int) -> int:
    """Exact length of the RS-encoded stream for a given payload length."""
    _validate_nsym(nsym)
    if data_len == 0:
        return 0
    chunks = math.ceil(data_len / (255 - nsym))
    return data_len + chunks * nsym


# Batches are multiples of the codeword size, so processing the stream in
# slices produces byte-identical output to one big call -- it only exists to
# let long operations report progress.
_BATCH_CODEWORDS = 512


def encode(data: bytes, nsym: int, progress=None) -> bytes:
    _validate_nsym(nsym)
    rsc = RSCodec(nsym)
    step = (255 - nsym) * _BATCH_CODEWORDS
    out = bytearray()
    for i in range(0, len(data), step):
        out += rsc.encode(data[i:i + step])
        if progress:
            progress(min(i + step, len(data)) / len(data))
    return bytes(out)


def decode(data: bytes, nsym: int, progress=None) -> bytes:
    _validate_nsym(nsym)
    rsc = RSCodec(nsym)
    step = 255 * _BATCH_CODEWORDS
    out = bytearray()
    for i in range(0, len(data), step):
        out += rsc.decode(data[i:i + step])[0]
        if progress:
            progress(min(i + step, len(data)) / len(data))
    return bytes(out)


# Compression damage is bursty: one mangled frame region corrupts a long run
# of consecutive bytes, overwhelming the single codeword it lands in. The
# interleaver transposes the stream so consecutive stored bytes come from
# *different* codewords, spreading any burst thinly across all of them.

def interleaved_len(data_len: int, width: int = 255) -> int:
    return math.ceil(data_len / width) * width


def interleave(data: bytes, width: int = 255) -> bytes:
    rows = math.ceil(len(data) / width)
    padded = data.ljust(rows * width, b"\x00")
    return np.frombuffer(padded, dtype=np.uint8).reshape(rows, width).T.tobytes()


def deinterleave(data: bytes, orig_len: int, width: int = 255) -> bytes:
    rows = math.ceil(orig_len / width)
    m = np.frombuffer(data[: rows * width], dtype=np.uint8).reshape(width, rows)
    return m.T.tobytes()[:orig_len]
