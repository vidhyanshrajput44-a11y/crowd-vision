"""Generate a realistic synthetic multi-zone crowd test video (MP4) for CrowdVision testing.

Draws a textured venue background with moving human-proportioned silhouettes entering Entrance A,
migrating to Main Stage and Food Court, and creating realistic density buildup so OpenCV HOG/MOG2
and YOLO detectors can detect and ByteTrack can track individuals smoothly.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def generate_synthetic_crowd_video(
    output_path: str | Path,
    duration_sec: float = 8.0,
    fps: float = 10.0,
    width: int = 640,
    height: int = 480,
    seed: int = 42,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)
    n_frames = int(duration_sec * fps)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open VideoWriter for {out}")

    # Build background with floor tiles and venue signs
    bg = np.full((height, width, 3), (230, 234, 238), dtype=np.uint8)

    # Grid lines
    for x in range(0, width, 40):
        cv2.line(bg, (x, 0), (x, height), (215, 220, 225), 1)
    for y in range(0, height, 40):
        cv2.line(bg, (0, y), (width, y), (215, 220, 225), 1)

    # Zone signs: Main Stage
    cv2.rectangle(bg, (16, 16), (320, 60), (60, 75, 95), -1)
    cv2.putText(bg, "MAIN STAGE", (105, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (240, 244, 248), 2)

    # Zone signs: Entrance A
    cv2.rectangle(bg, (360, 16), (620, 44), (50, 95, 160), -1)
    cv2.putText(bg, "ENTRANCE A", (435, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    n_people = 24

    # Initial positions (clustered near right side / entrance)
    xs = rng.uniform(width * 0.55, width * 0.94, size=n_people)
    ys = rng.uniform(height * 0.08, height * 0.88, size=n_people)

    # Target destinations:
    # 14 toward Main Stage (left-top)
    # 5 toward Entrance A area
    # 5 toward bottom area (Food Court)
    txs = np.concatenate([
        rng.uniform(width * 0.08, width * 0.46, size=14),
        rng.uniform(width * 0.58, width * 0.90, size=5),
        rng.uniform(width * 0.10, width * 0.45, size=5),
    ])
    tys = np.concatenate([
        rng.uniform(height * 0.16, height * 0.48, size=14),
        rng.uniform(height * 0.14, height * 0.44, size=5),
        rng.uniform(height * 0.60, height * 0.90, size=5),
    ])

    colors = [
        (int(rng.integers(20, 160)), int(rng.integers(20, 160)), int(rng.integers(20, 180)))
        for _ in range(n_people)
    ]

    # Pre-roll 4 static frames
    for _ in range(4):
        writer.write(bg)

    for f_idx in range(n_frames):
        frame = bg.copy()
        progress = f_idx / max(float(n_frames - 1), 1.0)
        active_count = min(n_people, 6 + int(progress * (n_people - 6)))

        for i in range(active_count):
            dx = txs[i] - xs[i]
            dy = tys[i] - ys[i]
            dist = float(np.hypot(dx, dy))

            if dist > 6.0:
                speed = 3.8 + (i % 3) * 0.8
                xs[i] += (dx / dist) * speed + float(rng.normal(0, 0.6))
                ys[i] += (dy / dist) * speed + float(rng.normal(0, 0.6))
            else:
                xs[i] += float(rng.normal(0, 1.5))
                ys[i] += float(rng.normal(0, 1.5))

            cx = int(np.clip(xs[i], 20, width - 20))
            cy = int(np.clip(ys[i], 45, height - 20))
            color = colors[i]

            # Torso rectangle
            cv2.rectangle(frame, (cx - 8, cy - 26), (cx + 8, cy - 6), color, -1)
            # Head circle
            cv2.circle(frame, (cx, cy - 33), 6, (45, 50, 60), -1)

            # Legs with walking motion
            stride = int(3 * np.sin(f_idx * 0.6 + i))
            cv2.line(frame, (cx - 4, cy - 6), (cx - 5 - stride, cy + 8), (35, 35, 45), 3)
            cv2.line(frame, (cx + 4, cy - 6), (cx + 5 + stride, cy + 8), (35, 35, 45), 3)

        writer.write(frame)

    writer.release()
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic CrowdVision test video")
    parser.add_argument("--output", default="uploads/videos/sample_crowd_festival.mp4")
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--fps", type=float, default=10.0)
    args = parser.parse_args()

    path = generate_synthetic_crowd_video(args.output, duration_sec=args.duration, fps=args.fps)
    print(f"Generated synthetic test video at: {path.resolve()}")
