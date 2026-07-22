"""Video -> file decoder."""

import hashlib
import os

import cv2

from . import crypto, ecc, framing, header


def _safe_filename(filename: str) -> str:
    name = os.path.basename(filename.replace("\\", os.sep)).strip()
    return name or "recovered.bin"


def _is_directory_target(path: str) -> bool:
    separators = [os.sep]
    if os.altsep:
        separators.append(os.altsep)
    return os.path.isdir(path) or any(path.endswith(sep) for sep in separators)


def recover_payload(video_path: str, progress=None) -> tuple[header.Header, bytes, bool]:
    """Recover the stored payload (still encrypted if it was encrypted).

    Returns (header, payload_bytes, sha256_ok). No password needed -- the
    header SHA covers the payload as stored, so integrity can be verified
    without decrypting. `progress` is called as progress(phase, fraction).
    """
    def report(phase, frac):
        if progress:
            progress(phase, frac)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"could not open video: {video_path}")
    try:
        ok, frame0 = cap.read()
        if not ok:
            raise ValueError("video has no frames")

        gray0 = cv2.cvtColor(frame0, cv2.COLOR_BGR2GRAY)
        hdr = _parse_any_header_copy(framing.frame_to_bytes(gray0, header.HEADER_BLOCK))

        encoded_len = ecc.encoded_len(hdr.payload_len, hdr.nsym)
        stored_len = ecc.interleaved_len(encoded_len)

        chunks = []
        for i in range(hdr.payload_frames):
            ok, frame = cap.read()
            if not ok:
                raise ValueError(
                    f"video ended early: expected {hdr.payload_frames} payload "
                    f"frames, got {i}"
                )
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            chunks.append(framing.frame_to_bytes(gray, hdr.block))
            if i % 10 == 0:
                report("reading frames", i / hdr.payload_frames)
    finally:
        cap.release()

    encoded = ecc.deinterleave(b"".join(chunks)[:stored_len], encoded_len)
    try:
        data = ecc.decode(encoded, hdr.nsym,
                          progress=lambda f: report("repairing errors", f))
    except ecc.ReedSolomonError as e:
        raise ValueError(
            "payload too corrupted for Reed-Solomon to repair -- try a larger "
            "--block or --nsym when encoding, or download at the original resolution"
        ) from e
    data = data[: hdr.payload_len]

    sha_ok = hashlib.sha256(data).digest() == hdr.sha256
    return hdr, data, sha_ok


def extract(video_path: str, output: str | None = None,
            password: str | None = None, progress=None) -> dict:
    """Decode an ISG video back into the original file.

    `output` may be a directory (original filename is used) or a file path.
    Returns a stats dict including whether the SHA-256 matched.
    """
    hdr, data, sha_ok = recover_payload(video_path, progress)

    if hdr.encrypted:
        if not password:
            raise ValueError("this video is encrypted -- a password is required")
        if progress:
            progress("decrypting", 0.9)
        data = crypto.decrypt(data, password)  # raises ValueError on wrong password

    filename = _safe_filename(hdr.filename)
    if output is None:
        output = filename
    elif _is_directory_target(output):
        os.makedirs(output, exist_ok=True)
        output = os.path.join(output, filename)
    else:
        parent = os.path.dirname(os.path.abspath(output))
        if parent:
            os.makedirs(parent, exist_ok=True)
    with open(output, "wb") as f:
        f.write(data)

    return {
        "output_path": output,
        "filename": filename,
        "bytes": len(data),
        "sha256_ok": sha_ok,
        "encrypted": hdr.encrypted,
        "block": hdr.block,
        "nsym": hdr.nsym,
    }


def _parse_any_header_copy(frame_bytes: bytes) -> header.Header:
    """Frame 0 holds several tiled copies of the header; accept the first good one."""
    last_error = None
    for offset in range(0, len(frame_bytes) - header.ENCODED_LEN + 1, header.ENCODED_LEN):
        try:
            return header.parse(frame_bytes[offset:offset + header.ENCODED_LEN])
        except ValueError as e:
            last_error = e
    raise ValueError(
        "could not recover the header -- this is not an ISG video, or it was "
        "re-encoded too aggressively (or downloaded at the wrong resolution)"
    ) from last_error
