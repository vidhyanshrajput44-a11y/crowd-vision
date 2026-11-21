import React, { useEffect, useRef } from 'react';

interface HeatmapOverlayProps {
  grid?: number[][];
  opacity?: number; // 0.0 - 1.0
  width: number;
  height: number;
  className?: string;
}

export const HeatmapOverlay: React.FC<HeatmapOverlayProps> = ({
  grid,
  opacity = 0.65,
  width,
  height,
  className = '',
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !grid || grid.length === 0 || !grid[0] || grid[0].length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rows = grid.length;
    const cols = grid[0].length;

    // Offscreen canvas for fast interpolation
    const offscreen = document.createElement('canvas');
    offscreen.width = cols;
    offscreen.height = rows;
    const offCtx = offscreen.getContext('2d');
    if (!offCtx) return;

    const imgData = offCtx.createImageData(cols, rows);
    const data = imgData.data;

    // Determine max value in grid for normalization
    let maxVal = 0.001;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if (grid[r][c] > maxVal) maxVal = grid[r][c];
      }
    }

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = (r * cols + c) * 4;
        const norm = Math.min(Math.max(grid[r][c] / maxVal, 0), 1);

        if (norm < 0.05) {
          // Transparent
          data[idx] = 0;
          data[idx + 1] = 0;
          data[idx + 2] = 0;
          data[idx + 3] = 0;
        } else {
          // Thermal colormap: Blue -> Cyan -> Lime -> Yellow -> Red
          let red = 0;
          let green = 0;
          let blue = 0;

          if (norm < 0.25) {
            // Blue to Cyan
            const t = norm / 0.25;
            blue = 255;
            green = Math.floor(t * 220);
          } else if (norm < 0.5) {
            // Cyan to Lime
            const t = (norm - 0.25) / 0.25;
            green = 255;
            blue = Math.floor((1 - t) * 255);
            red = Math.floor(t * 100);
          } else if (norm < 0.75) {
            // Lime to Yellow
            const t = (norm - 0.5) / 0.25;
            red = Math.floor(100 + t * 155);
            green = 255;
            blue = 0;
          } else {
            // Yellow to Bright Red
            const t = (norm - 0.75) / 0.25;
            red = 255;
            green = Math.floor((1 - t) * 230);
            blue = 0;
          }

          data[idx] = red;
          data[idx + 1] = green;
          data[idx + 2] = blue;
          data[idx + 3] = Math.floor(norm * 255 * opacity);
        }
      }
    }

    offCtx.putImageData(imgData, 0, 0);

    // Clear display canvas and draw smoothed upscale
    ctx.clearRect(0, 0, width, height);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(offscreen, 0, 0, width, height);
  }, [grid, opacity, width, height]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className={`pointer-events-none absolute inset-0 ${className}`}
    />
  );
};
