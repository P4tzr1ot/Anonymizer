#!/usr/bin/env python3
import os
import random
import subprocess
import json
import sys

# ================= CONFIG =================
BACKGROUND_NAME = "resources/background.mp4"
INPUT_DIR = "output/.output3"
OUTPUT_DIR = "output/.output4"
OUTPUT_NAME = "output.mp4"

MARGIN = 80
PIP_SCALE = 0.7
POP = 0.3
FADE = 0.3
AUDIO_FADE = 0.3
# ==========================================


def ffprobe_json(path):
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams", path
    ]
    out = subprocess.check_output(cmd).decode()
    return json.loads(out)


def get_duration(path):
    return float(ffprobe_json(path)["format"]["duration"])


def get_resolution(path):
    data = ffprobe_json(path)
    for s in data["streams"]:
        if s.get("codec_type") == "video":
            return int(s["width"]), int(s["height"])
    raise RuntimeError("Impossible de lire la résolution")


def has_audio(path):
    data = ffprobe_json(path)
    for s in data["streams"]:
        if s.get("codec_type") == "audio":
            return True
    return False


def random_center(bg_w, bg_h, pip_w, pip_h):
    min_x = MARGIN
    max_x = bg_w - pip_w - MARGIN
    min_y = MARGIN
    max_y = bg_h - pip_h - MARGIN

    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2

    ox = random.uniform(-(max_x - min_x) * 0.2, (max_x - min_x) * 0.2)
    oy = random.uniform(-(max_y - min_y) * 0.2, (max_y - min_y) * 0.2)

    x = int(max(min_x, min(cx + ox, max_x)))
    y = int(max(min_y, min(cy + oy, max_y)))

    return x, y


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    bg = os.path.join(script_dir, BACKGROUND_NAME)
    if not os.path.isfile(bg):
        print("ERREUR : background.mp4 introuvable")
        sys.exit(1)

    input_dir = os.path.join(script_dir, INPUT_DIR)
    if not os.path.isdir(input_dir):
        print(f"ERREUR : dossier '{INPUT_DIR}' introuvable")
        sys.exit(1)

    output_dir = os.path.join(script_dir, OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, OUTPUT_NAME)

    sources = [
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.lower().endswith(".mp4")
    ]

    if not sources:
        print("ERREUR : aucune vidéo .mp4 dans output2")
        sys.exit(1)

    sources.sort()

    bg_dur = get_duration(bg)
    bg_w, bg_h = get_resolution(bg)

    usable_start = 2
    usable_end = bg_dur - 2
    usable_total = usable_end - usable_start

    inputs = [f"-i {bg}"]
    filters = []

    audio_inputs = []
    if has_audio(bg):
        audio_inputs.append("[0:a]")

    overlay_chain = "[0:v]"
    current_t = usable_start

    slot = usable_total / len(sources)

    for idx, src in enumerate(sources):
        dur = get_duration(src)
        src_w, src_h = get_resolution(src)
        audio_ok = has_audio(src)

        pip_dur = max(min(dur, slot), 0.3)

        pip_h = int(bg_h * PIP_SCALE)
        pip_w = int(src_w * pip_h / src_h)
        pip_w -= pip_w % 2

        x, y = random_center(bg_w, bg_h, pip_w, pip_h)

        inputs.append(f"-i {src}")
        in_index = idx + 1

        filters.append(
            f"[{in_index}:v]trim=0:{pip_dur},setpts=PTS-STARTPTS,"
            f"scale={pip_w}:{pip_h},"
            f"split[v1_{idx}][v2_{idx}];"
            f"[v1_{idx}]noise=alls=30:allf=t+u,shuffleplanes=1:2:0,"
            f"scale={pip_w}:{pip_h}[vnoise_{idx}];"
            f"[v2_{idx}][vnoise_{idx}]blend=all_mode=difference:"
            f"enable='lt(t,{POP})'[vglitch_{idx}];"
            f"[vglitch_{idx}]fade=t=in:st=0:d={POP},"
            f"fade=t=out:st={pip_dur - FADE}:d={FADE}:alpha=1,"
            f"setpts=PTS+{current_t}/TB[pip{idx}];"
        )

        filters.append(
            f"{overlay_chain}[pip{idx}]overlay="
            f"x={x}:y={y}:enable='between(t,{current_t},{current_t + pip_dur})'"
            f"[v{idx}];"
        )

        overlay_chain = f"[v{idx}]"

        if audio_ok:
            delay_ms = int(current_t * 1000)
            filters.append(
                f"[{in_index}:a]atrim=0:{pip_dur},asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d={AUDIO_FADE},"
                f"afade=t=out:st={pip_dur - AUDIO_FADE}:d={AUDIO_FADE},"
                f"adelay={delay_ms}|{delay_ms}[a{idx}];"
            )
            audio_inputs.append(f"[a{idx}]")

        current_t += pip_dur

    if audio_inputs:
        filters.append(
            f"{''.join(audio_inputs)}amix="
            f"inputs={len(audio_inputs)}:normalize=1[aout]"
        )
        audio_map = '-map "[aout]" -c:a aac'
    else:
        audio_map = "-an"

    filter_complex = "".join(filters)
    final_duration = current_t + 2

    cmd = (
        f'ffmpeg -y {" ".join(inputs)} '
        f'-filter_complex "{filter_complex}" '
        f'-map "{overlay_chain}" {audio_map} '
        f'-t {final_duration} '
        f'-c:v libx264 -preset veryfast -crf 18 "{output_path}"'
    )

    print(cmd)
    os.system(cmd)


if __name__ == "__main__":
    main()
