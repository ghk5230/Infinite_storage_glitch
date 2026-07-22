"""Convert between raw bytes and black/white block frames.

Each bit of the payload becomes a `block x block` square of pixels:
1 -> white (255), 0 -> black (0). Large blocks survive lossy re-encoding
because the decoder samples the block *average*, and compression noise
rarely moves an all-black or all-white square across the 50% threshold.
"""

import numpy as np


def capacity_bytes(width: int, height: int, block: int) -> int:
    """Payload bytes that fit in one frame at the given block size."""
    return (width // block) * (height // block) // 8


def bytes_to_frame(data: bytes, width: int, height: int, block: int) -> np.ndarray:
    """Render exactly capacity_bytes() worth of data as a grayscale frame."""
    cols = width // block
    rows = height // block
    expected = rows * cols // 8
    if len(data) != expected:
        raise ValueError(f"expected {expected} bytes, got {len(data)}")
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    grid = (bits.reshape(rows, cols) * 255).astype(np.uint8)
    frame = np.repeat(np.repeat(grid, block, axis=0), block, axis=1)
    if frame.shape != (height, width):
        # block doesn't divide the frame evenly; pad the remainder with black
        padded = np.zeros((height, width), dtype=np.uint8)
        padded[: frame.shape[0], : frame.shape[1]] = frame
        frame = padded
    return frame


def frame_to_bytes(frame_gray: np.ndarray, block: int) -> bytes:
    """Recover the payload from a (possibly compression-damaged) frame."""
    h, w = frame_gray.shape
    rows = h // block
    cols = w // block
    blocks = frame_gray[: rows * block, : cols * block].reshape(rows, block, cols, block)
    means = blocks.mean(axis=(1, 3))
    bits = (means > 127).astype(np.uint8)
    return np.packbits(bits.ravel()).tobytes()
