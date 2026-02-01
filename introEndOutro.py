#!/usr/bin/env python3
import os
import subprocess
import sys

INPUT_DIR = "output/.output4"
OUTPUT_DIR = "output"
INTRO = "resources/intro.mp4"
OUTRO = "resources/outro.mp4"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi")

def get_resolution(video):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0", video
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    width, height = map(int, result.stdout.strip().split(","))
    return width, height

def main():
    if not os.path.isfile(INTRO) or not os.path.isfile(OUTRO):
        print("Fichiers intro ou outro introuvables")
        sys.exit(1)
    if not os.path.isdir(INPUT_DIR):
        print("Dossier input introuvable")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    videos = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(VIDEO_EXTENSIONS)]
    if not videos:
        print("Aucune vidéo trouvée")
        sys.exit(0)

    for video in videos:
        input_video = os.path.join(INPUT_DIR, video)
        output_video = os.path.join(OUTPUT_DIR, video)
        print(f"Traitement : {video}")

        width, height = get_resolution(input_video)

        cmd = [
            "ffmpeg", "-y",
            "-i", INTRO,
            "-i", input_video,
            "-i", OUTRO,
            "-filter_complex",
            f"[0:v]scale={width}:{height},setsar=1[intro];"
            f"[1:v]scale={width}:{height},setsar=1[main];"
            f"[2:v]scale={width}:{height},setsar=1[outro];"
            "[intro][0:a][main][1:a][outro][2:a]concat=n=3:v=1:a=1[outv][outa]",
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-movflags", "+faststart",
            output_video
        ]
        subprocess.run(cmd, check=True)

    print("Terminé.")

if __name__ == "__main__":
    main()
