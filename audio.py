#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import shutil
import logging

# ======================
# CONFIG
# ======================
INPUT_DIR = Path("output/.output1")
OUTPUT_DIR = Path("output/.output2")

OUTPUT_PREFIX = "source"
OUTPUT_EXT = ".mp4"

PITCH_UP = 1.25
PITCH_DOWN = 0.80

AUDIO_RATE = 44100
AUDIO_CHANNELS = 2
AUDIO_BITRATE = "192k"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
MAX_WORKERS = max(1, shutil.os.cpu_count() - 1)

# ======================
# LOGGING
# ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s"
)
log = logging.getLogger("batch")

# ======================
# UTILS
# ======================
def require_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg introuvable")
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe introuvable")

def next_output_name(index: int) -> Path:
    return OUTPUT_DIR / f"{OUTPUT_PREFIX}{index}{OUTPUT_EXT}"

def run(cmd: list):
    """Exécute FFmpeg et capture stderr pour debug"""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode != 0:
        log.error(f"FFmpeg ERROR:\n{result.stderr}")
        raise subprocess.CalledProcessError(result.returncode, cmd)

def has_audio(video: Path) -> bool:
    """Retourne True si la vidéo contient une piste audio"""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(video)
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True
    )
    return bool(result.stdout.strip())

# ======================
# PIPELINE VIDEO/AUDIO
# ======================
def process_video(job):
    input_video, output_video = job
    input_video = input_video.resolve()
    output_video = output_video.resolve()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if not has_audio(input_video):
            log.info(f"No audio → copy: {input_video.name}")
            run(["ffmpeg", "-y", "-i", str(input_video), "-c", "copy", str(output_video)])
            return f"{output_video.name} (no audio)"

        # Filtre audio : duplicate, pitch up/down, mix, volume boost
        filter_complex = (
            f"[0:a]asplit=2[a1][a2];"
            f"[a1]asetrate={AUDIO_RATE}*{PITCH_UP},atempo={1/PITCH_UP}[up];"
            f"[a2]asetrate={AUDIO_RATE}*{PITCH_DOWN},atempo={1/PITCH_DOWN}[down];"
            f"[up][down]amix=inputs=2[aout];"
            f"[aout]volume=2[aout2]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_video),
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout2]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", AUDIO_BITRATE,
            "-ac", str(AUDIO_CHANNELS),
            "-ar", str(AUDIO_RATE),
            "-shortest",
            str(output_video)
        ]

        log.info(f"Processing {input_video.name} → {output_video.name}")
        run(cmd)

        return output_video.name

    except subprocess.CalledProcessError:
        log.error(f"FAILED {input_video.name}")
        return f"ERREUR → {input_video.name}"

# ======================
# MAIN
# ======================
def main():
    require_ffmpeg()

    if not INPUT_DIR.exists():
        raise RuntimeError(f"Dossier input introuvable: {INPUT_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    videos = sorted(
        p for p in INPUT_DIR.iterdir()
        if p.suffix.lower() in VIDEO_EXTENSIONS
    )

    if not videos:
        raise RuntimeError("Aucune vidéo trouvée dans input")

    jobs = [
        (video, next_output_name(i + 1))
        for i, video in enumerate(videos)
    ]

    log.info(f"{len(jobs)} vidéos | {MAX_WORKERS} workers")

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(process_video, job) for job in jobs]

        for f in as_completed(futures):
            log.info(f"✔ {f.result()}")

if __name__ == "__main__":
    main()
