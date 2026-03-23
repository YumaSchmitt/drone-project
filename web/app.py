"""
Flask web app for the Drone Farmland Cutter.

Routes:
  GET  /                      — main UI
  POST /api/parse-kml         — parse uploaded KML file
  POST /api/fetch-kml         — fetch & parse Google My Maps KML URL
  POST /api/process           — upload media + params, start processing
  GET  /api/status/<job_id>   — poll job status
  GET  /api/download/<job_id> — download processed file
"""

import os
import sys
import json
import uuid
import threading
import time
import shutil

import requests
from flask import Flask, request, jsonify, render_template, send_file, abort

# Make demo/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "demo"))
from farmland_cutter import FarmlandCutter
from gps_utils import GPSBounds
from kml_parser import parse_kml_string

# ------------------------------------------------------------------ #
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB

JOBS_DIR = "/tmp/farmland_web_jobs"
os.makedirs(JOBS_DIR, exist_ok=True)

# In-memory job store: job_id -> dict
jobs: dict = {}
jobs_lock = threading.Lock()


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _job_dir(job_id: str) -> str:
    d = os.path.join(JOBS_DIR, job_id)
    os.makedirs(d, exist_ok=True)
    return d


def _set_job(job_id: str, **kwargs):
    with jobs_lock:
        if job_id not in jobs:
            jobs[job_id] = {}
        jobs[job_id].update(kwargs)


def _get_job(job_id: str) -> dict:
    with jobs_lock:
        return dict(jobs.get(job_id, {}))


# ------------------------------------------------------------------ #
# Background processing thread                                        #
# ------------------------------------------------------------------ #

def _process_job(job_id: str, input_path: str, output_path: str,
                 gps_bounds: GPSBounds, polygon, tight: bool,
                 bg_color, is_video: bool):
    try:
        _set_job(job_id, status="running", progress=0)
        cutter = FarmlandCutter(
            gps_bounds=gps_bounds,
            farmland_polygon=polygon,
            tight=tight,
            background_color=bg_color,
        )
        if is_video:
            import cv2
            cap = cv2.VideoCapture(input_path)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
            cap.release()

            w = int(cv2.VideoCapture(input_path).get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cv2.VideoCapture(input_path).get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cv2.VideoCapture(input_path).get(cv2.CAP_PROP_FPS)
            from gps_utils import build_mask, crop_to_polygon, tight_crop
            import numpy as np

            mask = cutter._get_mask(w, h)
            if tight:
                ys, xs = np.where(mask > 0)
                x0, x1 = int(xs.min()), int(xs.max())
                y0, y1 = int(ys.min()), int(ys.max())
                out_w, out_h = x1 - x0 + 1, y1 - y0 + 1
            else:
                x0, y0 = 0, 0
                out_w, out_h = w, h

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))
            cap2 = cv2.VideoCapture(input_path)
            idx = 0
            while True:
                ret, frame = cap2.read()
                if not ret:
                    break
                result = crop_to_polygon(frame, mask, bg_color)
                if tight:
                    result = result[y0:y1+1, x0:x1+1]
                writer.write(result)
                idx += 1
                _set_job(job_id, progress=int(idx / total * 100))
            cap2.release()
            writer.release()
        else:
            cutter.cut_image(input_path, output_path)

        _set_job(job_id, status="done", progress=100, output_path=output_path)
    except Exception as e:
        _set_job(job_id, status="error", error=str(e))
    finally:
        # clean up input file
        try:
            os.remove(input_path)
        except Exception:
            pass


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/parse-kml", methods=["POST"])
def parse_kml_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    text = f.read().decode("utf-8", errors="replace")
    try:
        polygons = parse_kml_string(text)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not polygons:
        return jsonify({"error": "No polygons found in KML"}), 400
    return jsonify({"polygons": polygons})


@app.route("/api/fetch-kml", methods=["POST"])
def fetch_kml_url():
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # Accept Google My Maps share URLs and convert to KML export URL
    # e.g. https://www.google.com/maps/d/edit?mid=1abc  →  /d/kml?mid=1abc
    import re
    mid_match = re.search(r"mid=([A-Za-z0-9_\-]+)", url)
    if "google.com/maps/d" in url and mid_match:
        mid = mid_match.group(1)
        url = f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1"

    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": f"Failed to fetch URL: {e}"}), 400

    try:
        polygons = parse_kml_string(resp.text)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not polygons:
        return jsonify({"error": "No polygons found in KML"}), 400
    return jsonify({"polygons": polygons})


@app.route("/api/process", methods=["POST"])
def start_process():
    # ---- parse form fields ---------------------------------------- #
    try:
        lat_min = float(request.form["lat_min"])
        lat_max = float(request.form["lat_max"])
        lon_min = float(request.form["lon_min"])
        lon_max = float(request.form["lon_max"])
        polygon_json = request.form["polygon"]       # JSON array of [lat, lon]
        tight = request.form.get("tight", "false").lower() == "true"
        bg_hex = request.form.get("bg_color", "#000000").lstrip("#")
        r, g, b = int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16)
        bg_color = (b, g, r)  # OpenCV uses BGR
    except (KeyError, ValueError) as e:
        return jsonify({"error": f"Invalid parameters: {e}"}), 400

    polygon = [tuple(pt) for pt in json.loads(polygon_json)]
    if len(polygon) < 3:
        return jsonify({"error": "Polygon must have at least 3 points"}), 400

    # ---- save uploaded file --------------------------------------- #
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    fname = f.filename or "upload"
    ext = os.path.splitext(fname)[1].lower()
    is_video = ext in (".mp4", ".mov", ".avi", ".mkv", ".webm")

    job_id = str(uuid.uuid4())
    jdir = _job_dir(job_id)
    input_path = os.path.join(jdir, f"input{ext}")
    output_ext = ".mp4" if is_video else ext or ".jpg"
    output_path = os.path.join(jdir, f"output{output_ext}")
    f.save(input_path)

    gps_bounds = GPSBounds(lat_min=lat_min, lat_max=lat_max,
                           lon_min=lon_min, lon_max=lon_max)

    _set_job(job_id, status="queued", progress=0,
             filename=f"farmland_cut{output_ext}", is_video=is_video)

    t = threading.Thread(
        target=_process_job,
        args=(job_id, input_path, output_path, gps_bounds,
              polygon, tight, bg_color, is_video),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def job_status(job_id: str):
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/download/<job_id>")
def download_file(job_id: str):
    job = _get_job(job_id)
    if not job or job.get("status") != "done":
        abort(404)
    path = job.get("output_path", "")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True,
                     download_name=job.get("filename", "output"))


@app.route("/api/demo-bounds")
def demo_bounds():
    """Return the GPS bounds for the built-in demo video."""
    bounds_path = os.path.join(
        os.path.dirname(__file__), "..", "demo", "output", "demo_bounds.json"
    )
    if os.path.exists(bounds_path):
        with open(bounds_path) as f:
            return jsonify(json.load(f))
    # Fallback: hard-coded values from generate_demo_video.py
    return jsonify({
        "lat_min": 31.76514,
        "lat_max": 31.77146,
        "lon_min": 35.20785,
        "lon_max": 35.21955,
    })


if __name__ == "__main__":
    print("Starting Drone Farmland Cutter web app …")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)
