"""File -> video encoder."""

import hashlib
import math
import os

import imageio_ffmpeg
import numpy as np

from . import crypto, ecc, framing, header


def embed(
    input_path: str,
    output_path: str,
    block: int = 8,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    nsym: int = 32,
    crf: int = 18,
    password: str | None = None,
    progress=None,
) -> dict:
    """Encode input_path into an H.264 video at output_path.

    `progress`, if given, is called as progress(phase: str, fraction: float).
    Returns a stats dict (frames, duration, sizes).
    """
    if block <= 0:
        raise ValueError("block size must be greater than zero")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be greater than zero")
    if fps <= 0:
        raise ValueError("fps must be greater than zero")
    if not 1 <= nsym < 255:
        raise ValueError("nsym must be between 1 and 254")
    if not 0 <= crf <= 51:
        raise ValueError("crf must be between 0 and 51")
    if width % block or height % block:
        raise ValueError(f"block size {block} must evenly divide {width}x{height}")
    if framing.capacity_bytes(width, height, block) <= 0:
        raise ValueError("frame dimensions are too small for the selected block size")

    def report(phase, frac):
        if progress:
            progress(phase, frac)

    with open(input_path, "rb") as f:
        data = f.read()
    if not data:
        raise ValueError("input file is empty")
    input_bytes = len(data)

    flags = 0
    if password:
        report("encrypting", 0.0)
        data = crypto.encrypt(data, password)
        flags |= header.FLAG_ENCRYPTED

    # The header SHA covers the (possibly encrypted) payload as stored, so
    # recovery can be verified without knowing the password.
    sha = hashlib.sha256(data).digest()
    encoded = ecc.interleave(
        ecc.encode(data, nsym, progress=lambda f: report("adding error correction", f))
    )
    cap = framing.capacity_bytes(width, height, block)
    payload_frames = math.ceil(len(encoded) / cap)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    hdr = header.build(header.Header(
        block=block,
        nsym=nsym,
        payload_len=len(data),
        payload_frames=payload_frames,
        sha256=sha,
        filename=os.path.basename(input_path),
        flags=flags,
    ))
    # Tile as many copies of the header as fit; the decoder tries each copy
    # until one survives, so a burst hitting frame 0 isn't fatal.
    header_cap = framing.capacity_bytes(width, height, header.HEADER_BLOCK)
    hdr_padded = (hdr * (header_cap // len(hdr))).ljust(header_cap, b"\x00")

    writer = imageio_ffmpeg.write_frames(
        output_path,
        (width, height),
        fps=fps,
        codec="libx264",
        quality=None,
        # never resize: a 1080-tall frame would get padded to 1088, shifting
        # the block grid; x264 handles non-multiple-of-16 sizes via crop flags
        macro_block_size=1,
        pix_fmt_out="yuv420p",
        output_params=[
            "-crf", str(crf),
            "-preset", "medium",
            "-movflags", "+faststart",
        ],
    )
    writer.send(None)  # seed the generator
    try:
        _send_gray(writer, framing.bytes_to_frame(hdr_padded, width, height, header.HEADER_BLOCK))
        for i in range(payload_frames):
            chunk = encoded[i * cap:(i + 1) * cap].ljust(cap, b"\x00")
            _send_gray(writer, framing.bytes_to_frame(chunk, width, height, block))
            if i % 10 == 0:
                report("rendering frames", i / payload_frames)
        report("rendering frames", 1.0)
    finally:
        writer.close()

    return {
        "input_bytes": input_bytes,
        "encoded_bytes": len(encoded),
        "payload_frames": payload_frames,
        "total_frames": payload_frames + 1,
        "duration_s": (payload_frames + 1) / fps,
        "video_bytes": os.path.getsize(output_path),
        "sha256": sha.hex(),
        "encrypted": bool(flags & header.FLAG_ENCRYPTED),
    }


def _send_gray(writer, frame_gray: np.ndarray) -> None:
    rgb = np.repeat(frame_gray[:, :, np.newaxis], 3, axis=2)
    writer.send(np.ascontiguousarray(rgb))
