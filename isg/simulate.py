"""Simulate YouTube's re-encoding so robustness can be tested without uploading.

YouTube transcodes 720p30 uploads to roughly 1.5-4 Mbps H.264/VP9. Re-encoding
at a similarly low bitrate locally is a good (slightly pessimistic) stand-in.
"""

import os
import subprocess

import imageio_ffmpeg


def reencode(input_path: str, output_path: str, bitrate: str = "2M") -> None:
    if not bitrate:
        raise ValueError("bitrate is required")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", input_path,
            "-c:v", "libx264",
            "-b:v", bitrate,
            "-maxrate", bitrate,
            "-bufsize", "2M",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ],
        check=True,
    )
