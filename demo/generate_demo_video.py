"""
Generates a synthetic top-down farmland demo video that simulates a Google Earth
recording. The output video has a known GPS bounding box so it can be fed directly
into FarmlandCutter.

The generated scene contains:
  - Multiple crop fields with different colours
  - Dirt roads / field dividers
  - A slow pan + zoom to mimic a Google Earth flyover

Run:
    python generate_demo_video.py
Outputs:
    demo_input.mp4   — the simulated Google Earth recording
    demo_bounds.json — the GPS bounding box of the full frame
"""

import json
import math
import random
import sys

import cv2
import numpy as np

# --------------------------------------------------------------------------- #
# Scene configuration                                                         #
# --------------------------------------------------------------------------- #
FRAME_W, FRAME_H = 1280, 720
FPS = 30
DURATION_SEC = 10          # total video length

# GPS bounding box for the *full* rendered scene (chosen to match a real area)
SCENE_CENTER_LAT = 31.7683
SCENE_CENTER_LON = 35.2137
SCENE_WIDTH_M = 1200       # metres wide
SCENE_HEIGHT_M = 700       # metres tall

CROP_COLORS = [
    (34, 139, 34),    # dark green  – maize / corn
    (124, 190, 70),   # lime green  – wheat
    (180, 210, 100),  # yellow-green – barley
    (85, 160, 60),    # medium green – soybeans
    (200, 230, 140),  # pale yellow  – harvested
    (60, 120, 50),    # deep green   – alfalfa
]
ROAD_COLOR   = (120, 100, 80)   # dirt road
SHADOW_COLOR = (30, 60, 20)     # hedge / tree shadow
SOIL_COLOR   = (100, 80, 60)    # bare soil patches

RANDOM_SEED = 42


# --------------------------------------------------------------------------- #
# Terrain generation                                                          #
# --------------------------------------------------------------------------- #
def _add_noise(img: np.ndarray, sigma: float = 8) -> np.ndarray:
    noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def generate_farmland_image(w: int, h: int, seed: int = RANDOM_SEED) -> np.ndarray:
    """Render a top-down farmland scene of size (w, h)."""
    rng = random.Random(seed)
    np.random.seed(seed)

    canvas = np.full((h, w, 3), SOIL_COLOR, dtype=np.uint8)

    # ---- draw rectangular crop fields ------------------------------------- #
    n_fields = rng.randint(8, 14)
    for _ in range(n_fields):
        x0 = rng.randint(0, w - 80)
        y0 = rng.randint(0, h - 60)
        fw = rng.randint(80, 280)
        fh = rng.randint(60, 200)
        x1, y1 = min(x0 + fw, w), min(y0 + fh, h)
        color = rng.choice(CROP_COLORS)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), color, -1)

        # crop row texture lines
        n_rows = (y1 - y0) // 6
        for row in range(n_rows):
            ly = y0 + row * 6
            dark = tuple(max(0, c - 20) for c in color)
            cv2.line(canvas, (x0, ly), (x1, ly), dark, 1)

    # ---- draw some irregular polygon fields ------------------------------- #
    for _ in range(4):
        n_pts = rng.randint(4, 7)
        cx = rng.randint(100, w - 100)
        cy = rng.randint(100, h - 100)
        pts = []
        for i in range(n_pts):
            angle = 2 * math.pi * i / n_pts + rng.uniform(-0.3, 0.3)
            r = rng.randint(40, 120)
            pts.append((int(cx + r * math.cos(angle)),
                        int(cy + r * math.sin(angle))))
        color = rng.choice(CROP_COLORS)
        cv2.fillPoly(canvas, [np.array(pts, dtype=np.int32)], color)

    # ---- dirt roads ------------------------------------------------------- #
    for _ in range(rng.randint(3, 6)):
        x = rng.randint(20, w - 20)
        cv2.line(canvas, (x, 0), (x + rng.randint(-30, 30), h),
                 ROAD_COLOR, rng.randint(4, 8))
    for _ in range(rng.randint(2, 4)):
        y = rng.randint(20, h - 20)
        cv2.line(canvas, (0, y), (w, y + rng.randint(-20, 20)),
                 ROAD_COLOR, rng.randint(4, 8))

    # ---- hedge / tree lines ----------------------------------------------- #
    for _ in range(rng.randint(4, 8)):
        x0 = rng.randint(0, w)
        y0 = rng.randint(0, h)
        x1 = x0 + rng.randint(-200, 200)
        y1 = y0 + rng.randint(-150, 150)
        cv2.line(canvas, (x0, y0), (x1, y1), SHADOW_COLOR, 3)

    canvas = _add_noise(canvas, sigma=6)
    return canvas


# --------------------------------------------------------------------------- #
# Camera animation (simulated Google Earth flyover)                           #
# --------------------------------------------------------------------------- #
def _lerp(a, b, t):
    return a + (b - a) * t


def _ease_inout(t):
    """Smooth-step."""
    return t * t * (3 - 2 * t)


def render_frame(base: np.ndarray, cx: float, cy: float,
                 scale: float, out_w: int, out_h: int) -> np.ndarray:
    """
    Extract a sub-region of *base* centred at (cx, cy) with the given scale
    (scale > 1 → zoom in) and resize to (out_w, out_h).
    """
    src_w = out_w / scale
    src_h = out_h / scale
    x0 = cx - src_w / 2
    y0 = cy - src_h / 2
    x1 = x0 + src_w
    y1 = y0 + src_h

    # clamp
    x0, y0 = max(x0, 0), max(y0, 0)
    x1 = min(x1, base.shape[1])
    y1 = min(y1, base.shape[0])

    src_pts = np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    dst_pts = np.float32([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]])
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    return cv2.warpPerspective(base, M, (out_w, out_h))


def build_keyframes(w: int, h: int):
    """Return a list of (cx, cy, scale) keyframes for the camera path."""
    return [
        (w * 0.5,  h * 0.5,  1.0),   # start: full overview
        (w * 0.45, h * 0.48, 1.4),   # zoom in slightly
        (w * 0.42, h * 0.52, 1.8),   # continue zoom
        (w * 0.50, h * 0.55, 2.2),   # pan right
        (w * 0.55, h * 0.50, 2.0),   # pan back
        (w * 0.5,  h * 0.5,  1.0),   # zoom out to overview
    ]


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #
def generate(output_path: str = "demo_input.mp4",
             bounds_path: str = "demo_bounds.json") -> dict:
    print("Generating farmland scene …")
    # Use a large base image (4× the output) for high-quality zoom
    base_w, base_h = FRAME_W * 2, FRAME_H * 2
    base = generate_farmland_image(base_w, base_h)

    keyframes = build_keyframes(base_w, base_h)
    total_frames = FPS * DURATION_SEC
    n_segments = len(keyframes) - 1
    frames_per_seg = total_frames // n_segments

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, FPS, (FRAME_W, FRAME_H))

    frame_idx = 0
    for seg in range(n_segments):
        kf_a = keyframes[seg]
        kf_b = keyframes[seg + 1]
        seg_frames = frames_per_seg if seg < n_segments - 1 else (total_frames - frame_idx)
        for i in range(seg_frames):
            t = _ease_inout(i / max(seg_frames - 1, 1))
            cx    = _lerp(kf_a[0], kf_b[0], t)
            cy    = _lerp(kf_a[1], kf_b[1], t)
            scale = _lerp(kf_a[2], kf_b[2], t)
            frame = render_frame(base, cx, cy, scale, FRAME_W, FRAME_H)
            writer.write(frame)
            frame_idx += 1

    writer.release()
    print(f"Video written: {output_path}  ({frame_idx} frames, {FPS} fps)")

    # ---- compute GPS bounds for the full base image ----------------------- #
    lat_delta = (SCENE_HEIGHT_M / 2) / 111320
    lon_delta = (SCENE_WIDTH_M  / 2) / (111320 * math.cos(math.radians(SCENE_CENTER_LAT)))
    bounds = {
        "lat_min": SCENE_CENTER_LAT - lat_delta,
        "lat_max": SCENE_CENTER_LAT + lat_delta,
        "lon_min": SCENE_CENTER_LON - lon_delta,
        "lon_max": SCENE_CENTER_LON + lon_delta,
        "center_lat": SCENE_CENTER_LAT,
        "center_lon": SCENE_CENTER_LON,
        "width_m": SCENE_WIDTH_M,
        "height_m": SCENE_HEIGHT_M,
        "note": (
            "These GPS bounds represent the full scene captured in the video. "
            "The camera pans and zooms but the underlying scene GPS extent stays fixed."
        ),
    }
    with open(bounds_path, "w") as f:
        json.dump(bounds, f, indent=2)
    print(f"GPS bounds written: {bounds_path}")
    return bounds


if __name__ == "__main__":
    out_video = sys.argv[1] if len(sys.argv) > 1 else "demo_input.mp4"
    out_bounds = sys.argv[2] if len(sys.argv) > 2 else "demo_bounds.json"
    generate(out_video, out_bounds)
