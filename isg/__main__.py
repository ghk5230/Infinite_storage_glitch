"""Command-line interface.

Usage:
    python -m isg embed secret.zip -o storage.mp4
    python -m isg simulate storage.mp4 -o youtubed.mp4 --bitrate 2M
    python -m isg extract youtubed.mp4 -o restored/
"""

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="isg",
        description="Infinite Storage Glitch: store any file as a YouTube-survivable video.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_embed = sub.add_parser("embed", help="encode a file into a video")
    p_embed.add_argument("input", help="file to encode")
    p_embed.add_argument("-o", "--output", required=True, help="output .mp4 path")
    p_embed.add_argument("--block", type=int, default=8,
                         help="pixels per bit-block side (default 8, aligned to the codec's "
                              "8x8 DCT grid; larger = more robust, less capacity)")
    p_embed.add_argument("--nsym", type=int, default=32,
                         help="Reed-Solomon parity bytes per 255-byte codeword (default 32)")
    p_embed.add_argument("--width", type=int, default=1280)
    p_embed.add_argument("--height", type=int, default=720)
    p_embed.add_argument("--fps", type=int, default=30)
    p_embed.add_argument("-p", "--password", default=None,
                         help="encrypt the file with AES-256-GCM before encoding")

    p_extract = sub.add_parser("extract", help="decode a video back into the original file")
    p_extract.add_argument("input", help="ISG video (e.g. downloaded from YouTube)")
    p_extract.add_argument("-o", "--output", default=None,
                           help="output file or directory (default: original filename here)")
    p_extract.add_argument("-p", "--password", default=None,
                           help="password, if the video was encrypted")

    p_sim = sub.add_parser("simulate", help="re-encode at low bitrate to mimic YouTube's compression")
    p_sim.add_argument("input", help="video to degrade")
    p_sim.add_argument("-o", "--output", required=True)
    p_sim.add_argument("--bitrate", default="2M", help="target bitrate (default 2M, roughly YouTube 720p)")

    p_gui = sub.add_parser("gui", help="launch the graphical interface in your browser")
    p_gui.add_argument("--port", type=int, default=8765)
    p_gui.add_argument("--no-browser", action="store_true",
                       help="don't open the browser automatically")

    args = parser.parse_args(argv)

    if args.command == "embed":
        from . import encoder
        stats = encoder.embed(
            args.input, args.output,
            block=args.block, nsym=args.nsym,
            width=args.width, height=args.height, fps=args.fps,
            password=args.password,
        )
        print(f"encoded {stats['input_bytes']:,} bytes "
              f"-> {stats['total_frames']} frames ({stats['duration_s']:.1f}s) "
              f"-> {stats['video_bytes']:,} byte video"
              + (" [encrypted]" if stats["encrypted"] else ""))
        print(f"sha256: {stats['sha256']}")

    elif args.command == "extract":
        from . import decoder
        stats = decoder.extract(args.input, args.output, password=args.password)
        print(f"wrote {stats['bytes']:,} bytes to {stats['output_path']}"
              + (" [decrypted]" if stats["encrypted"] else ""))
        if stats["sha256_ok"]:
            print("sha256 verified: file recovered perfectly")
        else:
            print("WARNING: sha256 mismatch -- recovered data is corrupted", file=sys.stderr)
            return 1

    elif args.command == "simulate":
        from . import simulate
        simulate.reencode(args.input, args.output, args.bitrate)
        print(f"re-encoded at {args.bitrate} -> {args.output}")

    elif args.command == "gui":
        from .gui import server
        server.run(port=args.port, open_browser=not args.no_browser)

    return 0


if __name__ == "__main__":
    sys.exit(main())
