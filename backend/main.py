from pathlib import Path
from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import JSONResponse
import tempfile
import os
import uuid
from fastapi.middleware.cors import CORSMiddleware
import re

from helpers import get_shopify_price, create_customer_product
from slicer import slice_model 

app = FastAPI(debug=True)

# Create uploads directory for persistent file storage
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://192.168.1.74:5173", "https://slicer.adbits.ca"],  # or ["*"] for all origins (not recommended for production)
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
    print(layerHeight, nozzleSize)
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
            grams = slice_model(stl_path, infill_density=infill, layer_height=layerHeight, nozzle_diameter=max(nozzleSize, 0.4), filament_density=density)
            print("Done slicing model.")
        except RuntimeError as e:
            import traceback
            traceback.print_exc()
            error_msg = str(e)
            # Check if it's a model loading error
            if "Loading of a model file failed" in error_msg or "Slicer error" in error_msg:
                return JSONResponse(
                    status_code=400, 
                    content={
                        "error": "Invalid model file. Please ensure your STL file is valid and not corrupted.",
                        "details": "The uploaded file could not be processed. Try re-exporting your model or using a different file format."
                    }
                )
            else:
                # Other runtime errors still return 500
                return JSONResponse(status_code=500, content={"error": f"Processing error: {error_msg}"})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"error": f"Unexpected error: {str(e)}"})

        estimated_price = round(round(grams) * price_per_gram, 2)

        if float(layerHeight) <= 0.08:
            estimated_price *= 1.2

        if float(nozzleSize) < 0.4:
            estimated_price *= 1.2

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

@app.post("/api/save-model")
async def save_model(
    file: UploadFile = File(...),
    screenshot: UploadFile = File(None),  # Optional screenshot
    material: str = Form(...),
    variant: str = Form(...),
    infill: int = Form(...),
    layerHeight: float = Form(...),
    nozzleSize: float = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    weight: float = Form(...),
    price: float = Form(...),
    complex: bool = Form(False)
):
    print(name)
    # Make the name safe for filesystem
    safe_name = re.sub(r'[^\w\-_\.]', '_', name.strip())
    if not safe_name:
        safe_name = uuid.uuid4().hex[:8]  # Generate a random name if empty
    
    # Get file extension from uploaded file
    file_extension = Path(file.filename).suffix if file.filename else ".stl"
    safe_filename = f"{safe_name}{file_extension}"
    stl_path = UPLOADS_DIR / safe_filename

    # Save uploaded file to persistent storage
    with open(stl_path, "wb") as f:
        f.write(await file.read())

    # Handle screenshot if provided (use temp directory)
    screenshot_path = None
    if screenshot:
        with tempfile.TemporaryDirectory() as temp_screenshot_dir:
            screenshot_filename = f"{safe_name}_screenshot.png"
            screenshot_path = os.path.join(temp_screenshot_dir, screenshot_filename)
            with open(screenshot_path, "wb") as f:
                f.write(await screenshot.read())
            print(f"Screenshot saved temporarily as: {screenshot_filename}")

            # Create product in Shopify with customer ownership metafields
            try:
                product_id, product_handle, variant_id = await create_customer_product(
                    email=email,
                    product_name=name,
                    material=material,
                    variant=variant,
                    infill=infill,
                    layer_height=layerHeight,
                    nozzle_size=nozzleSize,
                    filename=safe_filename,
                    file_path=str(stl_path),
                    weight=weight,
                    price=price,
                    screenshot_path=screenshot_path,
                    complex=complex
                )
                print(f"Created product: {product_id} with handle: {product_handle}")
            except Exception as e:
                import traceback
                traceback.print_exc()
                return JSONResponse(status_code=500, content={"error": f"Product creation error: {str(e)}"})
    else:
        # Create product without screenshot
        try:
            product_id, product_handle, variant_id = await create_customer_product(
                email=email,
                product_name=name,
                material=material,
                variant=variant,
                infill=infill,
                layer_height=layerHeight,
                nozzle_size=nozzleSize,
                filename=safe_filename,
                file_path=str(stl_path),
                weight=weight,
                price=price,
                screenshot_path=None
            )
            print(f"Created product: {product_id} with handle: {product_handle}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"error": f"Product creation error: {str(e)}"})

    return JSONResponse({
        "message": "Model saved and product created successfully",
        "saved_as": safe_filename,
        "saved_path": str(stl_path),
        "screenshot_provided": screenshot is not None,
        "name": name,
        "email": email,
        "product_id": product_id,
        "variant_id": variant_id,
        "product_handle": product_handle,
        "material": material,
        "infill": infill,
        "layerHeight": layerHeight,
        "nozzleSize": nozzleSize,
    })