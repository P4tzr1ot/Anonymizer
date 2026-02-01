#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cv2
import mediapipe as mp
import numpy as np
import json
import os
import subprocess
import shutil
from dataclasses import dataclass
from tqdm import tqdm

# ======================
# CONFIG
# ======================

@dataclass
class Config:
    input_dir: str = "input"
    output_dir: str = "output/.output1"

    mask_path: str = "resources/mask.png"
    keypoints_path: str = "resources/mask_keypoints.json"

    max_width: int = 1280
    frame_skip: int = 2
    landmark_interval: int = 5
    max_faces: int = 1

    glitch_intensity: int = 3
    noise_level: int = 80
    max_band_width: int = 30
    max_shift: int = 30
    seed: int = 42


CFG = Config()
rng = np.random.default_rng(CFG.seed)

LEFT_EYE = 33
RIGHT_EYE = 263
CHIN = 152

os.makedirs(CFG.output_dir, exist_ok=True)

# ======================
# LOAD STATIC RESOURCES
# ======================

with open(CFG.keypoints_path, "r") as f:
    MASK_KP = json.load(f)

MASK = cv2.imread(CFG.mask_path, cv2.IMREAD_UNCHANGED)
if MASK is None or MASK.shape[2] != 4:
    raise RuntimeError("Masque RGBA requis (PNG avec alpha)")

# ======================
# UTILS
# ======================

def resize_frame(frame):
    h, w = frame.shape[:2]
    if w <= CFG.max_width:
        return frame, 1.0
    scale = CFG.max_width / w
    return cv2.resize(frame, (int(w * scale), int(h * scale))), scale


def landmark_xy(lm, idx, w, h):
    return int(lm[idx].x * w), int(lm[idx].y * h)


def apply_glitch(frame):
    h, w, _ = frame.shape
    out = frame.copy()

    for _ in range(CFG.glitch_intensity):
        y = rng.integers(0, h)
        bh = rng.integers(5, CFG.max_band_width + 1)
        shift = rng.integers(-CFG.max_shift, CFG.max_shift + 1)
        out[y:y + bh] = np.roll(out[y:y + bh], shift, axis=1)

    noise = rng.integers(0, CFG.noise_level, size=(h, w), dtype=np.uint8)
    out[:, :, 1] = np.clip(out[:, :, 1].astype(np.uint16) + noise, 0, 255)

    return out.astype(np.uint8)


def blend_rgba(frame, overlay):
    alpha = overlay[:, :, 3:4] / 255.0
    frame[:] = (alpha * overlay[:, :, :3] + (1 - alpha) * frame)
    return frame.astype(np.uint8)

# ======================
# VIDEO PROCESSING
# ======================

def process_video(video_path, temp_video):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Vidéo illisible : {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    ret, first = cap.read()
    if not ret:
        raise RuntimeError("Première frame invalide")

    first, _ = resize_frame(first)
    h, w = first.shape[:2]

    out = cv2.VideoWriter(
        temp_video,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (w, h),
    )

    mp_face = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=CFG.max_faces,
        refine_landmarks=False,
    )

    last_landmarks = None
    prev_frame = first

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    for i in tqdm(range(total), desc=os.path.basename(video_path)):
        ret, frame = cap.read()
        if not ret:
            break

        frame, _ = resize_frame(frame)

        if i % CFG.frame_skip != 0:
            out.write(prev_frame)
            continue

        if i % CFG.landmark_interval == 0:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = mp_face.process(rgb)
            if result.multi_face_landmarks:
                last_landmarks = result.multi_face_landmarks[0].landmark

        if last_landmarks:
            left = landmark_xy(last_landmarks, LEFT_EYE, w, h)
            right = landmark_xy(last_landmarks, RIGHT_EYE, w, h)
            chin = landmark_xy(last_landmarks, CHIN, w, h)

            src = np.float32([
                MASK_KP["left_eye"],
                MASK_KP["right_eye"],
                MASK_KP["chin"],
            ])
            dst = np.float32([left, right, chin])

            M = cv2.getAffineTransform(src, dst)
            warped = cv2.warpAffine(
                MASK, M, (w, h),
                borderMode=cv2.BORDER_TRANSPARENT
            )

            frame = blend_rgba(frame, warped)
            frame = apply_glitch(frame)

        out.write(frame)
        prev_frame = frame

    cap.release()
    out.release()
    mp_face.close()

# ======================
# AUDIO EXPORT
# ======================

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

def export_with_audio(video_in, temp_video, final_video):
    if not FFMPEG_AVAILABLE:
        os.rename(temp_video, final_video)
        return

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", video_in,
            "-map", "0:v:0",
            "-map", "1:a?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-shortest",
            final_video,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    os.remove(temp_video)

# ======================
# MAIN
# ======================

def main():
    if not os.path.exists(CFG.input_dir):
        raise RuntimeError("Dossier input/ manquant")

    videos = [
        f for f in os.listdir(CFG.input_dir)
        if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))
    ]

    if not videos:
        raise RuntimeError("Aucune vidéo trouvée")

    for video in videos:
        path = os.path.join(CFG.input_dir, video)
        name, _ = os.path.splitext(video)

        temp_video = os.path.join(CFG.output_dir, f"{name}_no_audio.mp4")
        final_video = os.path.join(CFG.output_dir, f"{name}_final.mp4")

        process_video(path, temp_video)
        export_with_audio(path, temp_video, final_video)

        print(f"✔ Terminé : {final_video}")

if __name__ == "__main__":
    main()
