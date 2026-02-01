#!/bin/bash

source mask_env/bin/activate

spinner() {
  local pid=$1
  local label="$2"
  local spin='|/-\'
  local i=0

  while kill -0 $pid 2>/dev/null; do
    i=$(( (i+1) %4 ))
    printf "\r[%c] %s..." "${spin:$i:1}" "$label"
    sleep 0.1
  done

  printf "\r[✓] %s Done            \n" "$label"
}

run() {
  local label="$1"
  shift
  "$@" > /dev/null 2>&1 &
  spinner $! "$label"
}

run "Mask & Glitch      " python3 face_mask_glitch_video.py
run "Voice Encryption   " python3 audio.py
run "Transitions        " python3 introNoutro.py
run "Background & Pip   " python3 backNpip.py
run "Intro & Outro added" python3 introEndOutro.py

rm Anonymizer/output/.output{1,2,3,4}/* > /dev/null 2>&1

echo "[✓] Video Anonymizer    Done"
