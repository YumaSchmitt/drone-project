# Drone Farmland Cutter

Cut drone video and images to a GPS-defined farmland boundary.

## Overview

This tool takes a top-down video or image (from a drone like DJI Mavic, or a
Google Earth recording) and masks/crops it to a farmland polygon defined by GPS
coordinates. Everything outside the polygon is blacked out.

```
Full frame (GPS bounds known)          After cutting to polygon
┌─────────────────────────┐            ┌─────────────────────────┐
│  ░░░░░░  fields  ░░░░░░ │            │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
│  ░░░ [GPS polygon] ░░░░ │   ──────►  │  ▓▓▓ [farmland]  ▓▓▓▓▓ │
│  ░░░░░░  fields  ░░░░░░ │            │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
└─────────────────────────┘            └─────────────────────────┘
```

## Quick Start

```bash
pip install -r demo/requirements.txt
cd demo/
python run_demo.py
```

Outputs are written to `demo/output/`:

| File | Description |
|---|---|
| `demo_input.mp4` | Synthetic Google Earth-like farmland video |
| `demo_cut_video.mp4` | Video cut to the GPS farmland polygon |
| `demo_cut_frame.jpg` | Single frame cut to the polygon |
| `demo_preview.jpg` | Polygon overlay preview |
| `demo_bounds.json` | GPS bounding box of the scene |

## Using with Your Own Video

### 1. Know your GPS bounds

For a **Google Earth recording**, read off the lat/lon of the four corners of the
visible area before recording.

For **DJI Mavic footage**, the GPS exif/telemetry gives you the flight path; the
frame bounds can be computed from altitude and field of view.

### 2. Define the farmland polygon

Edit the `FARMLAND_POLYGON` list in `run_demo.py` (or pass it directly to
`FarmlandCutter`). Each point is `(latitude, longitude)`.

```python
FARMLAND_POLYGON = [
    (31.7695, 35.2110),   # north-west corner
    (31.7698, 35.2148),   # north-east corner
    (31.7685, 35.2152),   # south-east corner
    (31.7675, 35.2130),   # south
    (31.7678, 35.2107),   # south-west corner
]
```

### 3. Run the cutter

```python
from demo.gps_utils import GPSBounds
from demo.farmland_cutter import FarmlandCutter

bounds = GPSBounds(lat_min=..., lat_max=..., lon_min=..., lon_max=...)
cutter = FarmlandCutter(bounds, FARMLAND_POLYGON)

cutter.cut_image("frame.jpg", "frame_cut.jpg")
cutter.cut_video("flight.mp4", "flight_cut.mp4")
```

## Project Structure

```
demo/
├── gps_utils.py            GPS ↔ pixel coordinate conversion + masking
├── farmland_cutter.py      FarmlandCutter class (video + image)
├── generate_demo_video.py  Synthetic Google Earth farmland video generator
├── run_demo.py             End-to-end demo runner
└── requirements.txt
```

## Roadmap

- [ ] Support DJI `.SRT` subtitle files for per-frame GPS telemetry
- [ ] Interactive polygon editor (click on map to define boundaries)
- [ ] KML/GeoJSON import for farm boundaries
- [ ] Tight crop mode (output only the bounding box of the polygon)
- [ ] Batch processing multiple parcels from one flight
