import subprocess
import tempfile
import os
import re

def slice_model(stl_path, infill_density=20, layer_height=0.2, nozzle_diameter=0.4, filament_density=1.24):
    with tempfile.TemporaryDirectory() as tempdir:
        gcode_path = os.path.join(tempdir, "output.gcode")

        cmd = [
            "prusa-slicer", "-g", stl_path,
            "--output", gcode_path,
            f"--layer-height={layer_height}",
            f"--fill-density={infill_density}%",
            "--filament-diameter=1.75",
            f"--filament-density={filament_density}",
            "--support-material=1",
            "--support-material-style=organic",
            "--support-material-angle=30",
            "--support-material-extruder=0",
            "--support-material-interface-extruder=0",
            "--fill-pattern=gyroid",
            f"--nozzle-diameter={nozzle_diameter}"
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