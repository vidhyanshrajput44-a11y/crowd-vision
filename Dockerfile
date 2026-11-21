# Multi-stage Production Dockerfile for CROWD VISION Platform on Render
# Stage 1: Build Frontend Single Page Application
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python & Computer Vision Runtime
FROM python:3.11-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PORT=10000 \
    APP_HOST=0.0.0.0

WORKDIR /app

# Install native OS libraries required by OpenCV (headless/codec), FFmpeg, and health probes
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python backend dependencies
COPY requirements.txt ./
COPY backend/requirements.txt ./backend/
COPY ai_agent/requirements.txt ./ai_agent/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source and assets
COPY backend/ ./backend/
COPY ai_agent/ ./ai_agent/
COPY cctvfootagerailway.mp4 ./cctvfootagerailway.mp4
COPY crowdvision_main.db ./crowdvision_main.db

# Copy compiled frontend SPA from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose dynamic Render port
EXPOSE 10000

# Health check probe against production FastAPI endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT:-10000}/api/health || exit 1

# Start FastAPI backend bound to 0.0.0.0 and Render dynamic $PORT
CMD ["sh", "-c", "python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-10000}"]
