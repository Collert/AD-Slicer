import subprocess
import tempfile
import os
import re

def slice_model(stl_path, infill_density=20, layer_height=0.2, nozzle_diameter=0.4, filament_density=1.24):
    # Check if we're in development mode (no prusa-slicer available)
    import shutil
    if not shutil.which("prusa-slicer"):
        print("⚠️  DEV MODE: PrusaSlicer not found, using mock weight calculation")
        # Mock calculation for development: estimate weight based on file size and infill
        try:
            file_size_mb = os.path.getsize(stl_path) / (1024 * 1024)  # File size in MB
            base_weight = file_size_mb * 10  # Rough estimate: 10g per MB
            infill_multiplier = (infill_density / 100) * 0.7 + 0.3  # 30% base + 70% infill
            estimated_weight = base_weight * infill_multiplier * (filament_density / 1.24)
            print(f"📊 Mock calculation: {file_size_mb:.2f}MB file → {estimated_weight:.2f}g estimated weight")
            return max(1.0, estimated_weight)  # Minimum 1g
        except Exception as e:
            print(f"❌ Mock calculation failed: {e}")
            return 25.0  # Default fallback weight
    
    # Production mode: use actual PrusaSlicer
    with tempfile.TemporaryDirectory() as tempdir:
        gcode_path = os.path.join(tempdir, "output.gcode")

        cmd = [
            "prusa-slicer", "-g", stl_path,
            "--output", gcode_path,
            f"--layer-height={layer_height}",
            f"--fill-density={min(infill_density, 99)}%",
            "--filament-diameter=1.75",
            f"--filament-density={filament_density}",
            "--support-material=1",
            "--support-material-style=organic",
            "--support-material-angle=30",
            "--support-material-extruder=0",
            "--support-material-interface-extruder=0",
            "--fill-pattern=gyroid",
            f"--nozzle-diameter={nozzle_diameter}",
            f"--first-layer-height={layer_height}",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Slicer error: {result.stderr}")

        # Extract weight from the G-code
        with open(gcode_path, "r") as f:
            for line in f:
                if "total filament used [g]" in line:
                    match = re.search(r"([\d.]+)", line)
                    if match:
                        return float(match.group(1))

        raise ValueError("Could not extract filament weight from G-code.")