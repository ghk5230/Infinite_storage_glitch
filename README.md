# Infinite Storage Glitch

Store **any file** as a noise-filled video that survives YouTube's re-compression.
Upload the video, delete the file, download the video later, and decode it back —
bit-for-bit identical, verified by SHA-256.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# launch the GUI (opens in your browser)
.venv\Scripts\python -m isg gui
```

The GUI has three tabs: **Encode** (drag & drop any file, optional AES-256
password encryption, live progress, video preview), **Decode** (drop a video,
get the file back with SHA-256 verification), and **Stress test** (one click
crushes the video with YouTube-grade compression and proves the data
survives — the demo moment).

Or use the CLI:

```powershell
# file -> video (add -p <password> for AES-256-GCM encryption)
.venv\Scripts\python -m isg embed secret.zip -o storage.mp4 -p hunter2

# prove it survives YouTube-grade compression (no upload needed)
.venv\Scripts\python -m isg simulate storage.mp4 -o degraded.mp4 --bitrate 2M

# video -> file (restores original filename, verifies SHA-256)
.venv\Scripts\python -m isg extract degraded.mp4 -o restored/ -p hunter2
```

## How it works

YouTube re-encodes every upload with aggressive lossy compression, so a naive
"1 pixel = 1 bit" video comes back scrambled. Three layers make the data survive:

1. **8×8 black/white blocks.** Each bit is drawn as an 8×8 pixel square — pure
   black or pure white. The decoder samples each block's *average* brightness,
   so compression noise almost never flips a bit. 8 px specifically aligns the
   data grid with H.264/VP9's 8×8 DCT transform grid; measurements showed
   misaligned sizes (4, 5 px) suffer 20–60% byte error rates at YouTube-like
   bitrates while 8 px gets ~0%.
2. **Reed–Solomon error correction** (32 parity bytes per 255-byte codeword,
   corrects 16) repairs the bits that still flip.
3. **Byte interleaving.** Compression damage is bursty — one bad frame region
   corrupts a long run of bytes, which would overwhelm a single codeword. The
   encoded stream is transposed so consecutive stored bytes belong to
   *different* codewords, spreading any burst thinly across all of them.

Frame 0 is a metadata header (filename, size, encoding params, SHA-256),
encoded extra-robustly and tiled 4× for redundancy, so the decoder is fully
self-bootstrapping — any ISG video decodes with zero configuration.

**Encryption (optional):** with a password, the file is encrypted with
AES-256-GCM before encoding. The key is derived with scrypt (memory-hard),
and GCM authentication means a wrong password is detected reliably. The
header's SHA-256 covers the *encrypted* payload, so anyone can verify a
video survived YouTube intact — but only the password holder can read it.

## Measured robustness (720p30, 300 KB random payload)

| Setting            | 2 Mbps | 1.5 Mbps | 1 Mbps |
|--------------------|--------|----------|--------|
| `--block 8` (default) | ✅ perfect | ✅ perfect | ❌ |
| `--block 16`          | ✅ perfect | ✅ perfect | ✅ perfect |

YouTube serves 720p at roughly 1.5–4 Mbps, so the defaults carry comfortable
margin; use `--block 16` if you want paranoid mode. (At a hard 1 Mbps,
full-density noise simply exceeds the channel's information capacity —
that's physics, not a bug.)

## Capacity

| Setting | Payload rate | Per minute of video |
|---------|-------------|---------------------|
| 720p30, block 8 (default) | ~47 KB/s | ~2.8 MB |
| 1080p30, block 8 (`--width 1920 --height 1080`) | ~106 KB/s | ~6.4 MB |
| 720p30, block 16 (paranoid) | ~12 KB/s | ~0.7 MB |

## The real YouTube round trip

1. `python -m isg embed file.zip -o storage.mp4` and upload `storage.mp4`.
2. Wait for YouTube to finish processing the HD version.
3. Download at the **same resolution you uploaded**, e.g.
   `yt-dlp -f "bv*[height=720]" <url>` — a rescaled download breaks the block grid.
4. `python -m isg extract downloaded.mp4`

## Caveats

- Using YouTube as arbitrary file storage is against its Terms of Service —
  this is a proof-of-concept for a competition, not a backup strategy. Never
  keep the video as the only copy of anything.
- Reed–Solomon in pure Python is the bottleneck: expect a few seconds per MB.
- If YouTube ever re-encodes old videos at lower quality (it does, years
  later, e.g. to AV1), stored data may degrade — another reason this is a
  demo, not a vault.

## Project layout

```
isg/
  framing.py   bits <-> black/white block frames
  ecc.py       Reed-Solomon + burst interleaver
  header.py    self-describing metadata frame
  crypto.py    AES-256-GCM password encryption (scrypt KDF)
  encoder.py   file -> mp4 (bundled ffmpeg via imageio-ffmpeg)
  decoder.py   mp4 -> file (OpenCV frame reader)
  simulate.py  local stand-in for YouTube's re-encode
  __main__.py  CLI
  gui/         Flask backend + web frontend (python -m isg gui)
```
