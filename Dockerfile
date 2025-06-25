# Stage 1: Build frontend
FROM node:20 AS frontend-build

WORKDIR /app
COPY slicer ./slicer
WORKDIR /app/slicer

# Install dependencies and build
RUN npm install && node js/rollup.js kiri

# Stage 2: Final image with FastAPI + built frontend + PrusaSlicer CLI
FROM python:3.11-slim

# Install dependencies for PrusaSlicer
RUN apt-get update && apt-get install -y \
    libwebkit2gtk-4.1-dev \
    wget \
    fuse \
    && rm -rf /var/lib/apt/lists/*

# Download and extract PrusaSlicer AppImage
WORKDIR /opt
RUN wget -O PrusaSlicer.AppImage "https://github.com/prusa3d/PrusaSlicer/releases/download/version_2.8.1/PrusaSlicer-2.8.1+linux-x64-newer-distros-GTK3-202409181416.AppImage" && \
    chmod +x PrusaSlicer.AppImage && \
    ./PrusaSlicer.AppImage --appimage-extract && \
    ln -s /opt/squashfs-root/usr/bin/prusa-slicer /usr/local/bin/prusa-slicer && \
    rm PrusaSlicer.AppImage

# Set workdir for app
WORKDIR /app

ENV PYTHONPATH="${PYTHONPATH}:/app/backend"

# Copy backend
COPY backend ./backend

# Copy frontend build from previous stage
COPY --from=frontend-build /app/slicer/out/kiri ./slicer/dist

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment flag
ENV ENV=production

# Expose the port
EXPOSE 8282

# Run the app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8282"]
