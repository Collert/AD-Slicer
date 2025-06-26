from pathlib import Path
from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import JSONResponse
import tempfile
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from helpers import get_shopify_price
from slicer import slice_model 

app = FastAPI(debug=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://192.168.1.74:5173"],  # or ["*"] for all origins (not recommended for production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/ping")
async def ping():
    return {"message": "pong"}

@app.post("/api/get-quote")
async def get_quote(
    file: UploadFile = File(...),
    material: str = Form(...),
    variant: str = Form(...),
    infill: int = Form(...),
    layerHeight: float = Form(...),
    nozzleSize: float = Form(0.4)  # optional if you want to support different detail levels
):
    filename = file.filename

    # Get price per gram and density from Shopify before slicing
    try:
        price_per_gram, density = await get_shopify_price(material, variant if variant.startswith("gid://shopify/ProductVariant/") else None)
        print(f"Price per gram for {material} (variant {variant}): {price_per_gram}, density: {density}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Shopify error: {str(e)}"})

    with tempfile.TemporaryDirectory() as tempdir:
        stl_path = os.path.join(tempdir, filename)

        # Save uploaded STL to temp file
        with open(stl_path, "wb") as f:
            f.write(await file.read())

        try:
            print("Slicing model...")
            grams = slice_model(stl_path, infill_density=infill, layer_height=layerHeight, nozzle_diameter=nozzleSize, filament_density=density)
            print("Done slicing model.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"error": str(e)})

        estimated_price = round(round(grams) * price_per_gram, 2)

        return JSONResponse({
            "file": filename,
            "grams": round(grams, 2),
            "price": estimated_price,
            "material": material,
            "infill": infill,
            "layerHeight": layerHeight,
            "nozzleSize": nozzleSize,
            "price_per_gram": price_per_gram,
            "density": density
        })
