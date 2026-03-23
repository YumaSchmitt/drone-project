"""
run_demo.py — end-to-end demo of the drone farmland cutter.

Steps:
  1. Generate a synthetic Google Earth-like farmland video (demo_input.mp4)
  2. Define a GPS polygon for one farmland parcel
  3. Cut the video and a single frame to that polygon
  4. Save a preview image showing the GPS polygon overlay

Run:
    cd demo/
    python run_demo.py

Outputs (written to ./output/):
    demo_input.mp4         — synthetic source video
    demo_cut_video.mp4     — video masked to the farmland polygon
    demo_cut_frame.jpg     — single frame masked to the farmland polygon
    demo_preview.jpg       — polygon overlay preview (green = inside, border = cyan)
    demo_bounds.json       — GPS bounding box of the scene
"""

import json
import os
import sys

import cv2

from generate_demo_video import generate, SCENE_CENTER_LAT, SCENE_CENTER_LON
from gps_utils import GPSBounds
from farmland_cutter import FarmlandCutter

OUTPUT_DIR = "output"

# --------------------------------------------------------------------------- #
# Define a GPS polygon for the farmland parcel we want to cut                 #
#                                                                             #
# The demo scene covers roughly 1200 m × 700 m centred on:                   #
#   31.7683° N,  35.2137° E   (near Jerusalem, used as a placeholder)        #
#                                                                             #
# The polygon below selects a mid-left section of that scene.                #
# Coordinates are (latitude, longitude).                                      #
# --------------------------------------------------------------------------- #
FARMLAND_POLYGON = [
    (31.7695, 35.2110),   # top-left corner
    (31.7698, 35.2148),   # top-right corner
    (31.7685, 35.2152),   # bottom-right corner
    (31.7675, 35.2130),   # bottom-left corner
    (31.7678, 35.2107),   # bottom-left wing
]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 1. Generate demo video                                              #
    # ------------------------------------------------------------------ #
    video_path  = os.path.join(OUTPUT_DIR, "demo_input.mp4")
    bounds_path = os.path.join(OUTPUT_DIR, "demo_bounds.json")

    print("=" * 60)
    print("Step 1 — Generating synthetic Google Earth demo video …")
    print("=" * 60)
    bounds_dict = generate(video_path, bounds_path)

    # ------------------------------------------------------------------ #
    # 2. Build GPS bounds + cutter                                        #
    # ------------------------------------------------------------------ #
    gps_bounds = GPSBounds(
        lat_min=bounds_dict["lat_min"],
        lat_max=bounds_dict["lat_max"],
        lon_min=bounds_dict["lon_min"],
        lon_max=bounds_dict["lon_max"],
    )

    cutter = FarmlandCutter(
        gps_bounds=gps_bounds,
        farmland_polygon=FARMLAND_POLYGON,
        tight=False,                  # keep full frame size; mask outside = black
        background_color=(0, 0, 0),
    )

    # ------------------------------------------------------------------ #
    # 3. Cut a single frame (snapshot)                                    #
    # ------------------------------------------------------------------ #
    print("\nStep 2 — Extracting and cutting a single frame …")
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 100)   # grab frame 100
    ret, frame = cap.read()
    cap.release()

    if ret:
        frame_path = os.path.join(OUTPUT_DIR, "demo_input_frame.jpg")
        cut_frame_path = os.path.join(OUTPUT_DIR, "demo_cut_frame.jpg")
        cv2.imwrite(frame_path, frame)
        cutter.cut_image(frame_path, cut_frame_path)
    else:
        print("  Warning: could not read a frame from the video.")

    # ------------------------------------------------------------------ #
    # 4. Cut the full video                                               #
    # ------------------------------------------------------------------ #
    print("\nStep 3 — Cutting video to farmland polygon …")
    cut_video_path = os.path.join(OUTPUT_DIR, "demo_cut_video.mp4")
    cutter.cut_video(video_path, cut_video_path)

    # ------------------------------------------------------------------ #
    # 5. Save polygon preview                                             #
    # ------------------------------------------------------------------ #
    print("\nStep 4 — Generating polygon preview …")
    preview = cutter.preview_polygon(width=1280, height=720)
    preview_path = os.path.join(OUTPUT_DIR, "demo_preview.jpg")
    cv2.imwrite(preview_path, preview)
    print(f"Preview saved: {preview_path}")

    # ------------------------------------------------------------------ #
    # Summary                                                             #
    # ------------------------------------------------------------------ #
    print("\n" + "=" * 60)
    print("Demo complete! Output files:")
    for fname in sorted(os.listdir(OUTPUT_DIR)):
        fpath = os.path.join(OUTPUT_DIR, fname)
        size_kb = os.path.getsize(fpath) // 1024
        print(f"  {fname:<35} {size_kb:>6} KB")
    print("=" * 60)
    print("\nFarmland GPS polygon used:")
    for i, (lat, lon) in enumerate(FARMLAND_POLYGON):
        print(f"  Point {i+1}: lat={lat:.6f}  lon={lon:.6f}")
    print("\nTo use with your own video:")
    print("  1. Replace FARMLAND_POLYGON with your actual GPS boundary")
    print("  2. Set gps_bounds to match your video's geographic extent")
    print("  3. Call cutter.cut_video() or cutter.cut_image()")


if __name__ == "__main__":
    main()
