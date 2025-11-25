import httpx
import os
from dotenv import load_dotenv
import re
import uuid
from pathlib import Path

SHOPIFY_DOMAIN = "jvvkum-8d.myshopify.com"  # Replace with your shop domain

# Load environment variables from .env file in the same directory
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
print(f"SHOPIFY_TOKEN loaded: {SHOPIFY_TOKEN is not None}")

if not SHOPIFY_TOKEN:
    raise ValueError("SHOPIFY_TOKEN environment variable is not set. Please check your .env file.")

async def get_shopify_price(material_gid, variant_gid=None):
    if not SHOPIFY_TOKEN:
        raise ValueError("SHOPIFY_TOKEN is not available")
        
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    print(f"Getting price for material_gid: {material_gid}, variant_gid: {variant_gid}")
    
    # Extract numeric IDs from GIDs
    def extract_id(gid):
        return gid.split("/")[-1] if gid and gid.startswith("gid://shopify/") else None
    product_id = extract_id(material_gid)
    variant_id = extract_id(variant_gid) if variant_gid and variant_gid.startswith("gid://shopify/ProductVariant/") else None
    
    print(f"Extracted product_id: {product_id}, variant_id: {variant_id}")

    async with httpx.AsyncClient() as client:
        if variant_id:
            url = f"https://{SHOPIFY_DOMAIN}/admin/api/2023-10/variants/{variant_id}.json?fields=price,metafields"
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()["variant"]
            price = float(data["price"])
            # Fetch metafields for the variant
            meta_url = f"https://{SHOPIFY_DOMAIN}/admin/api/2023-10/variants/{variant_id}/metafields.json"
            meta_resp = await client.get(meta_url, headers=headers)
            meta_resp.raise_for_status()
            metafields = meta_resp.json().get("metafields", [])
        else:
            url = f"https://{SHOPIFY_DOMAIN}/admin/api/2023-10/products/{product_id}.json?fields=variants,metafields"
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            product = resp.json()["product"]
            variants = product["variants"]
            price = float(variants[0]["price"]) if variants else 0.0
            # Fetch metafields for the product
            meta_url = f"https://{SHOPIFY_DOMAIN}/admin/api/2023-10/products/{product_id}/metafields.json"
            meta_resp = await client.get(meta_url, headers=headers)
            meta_resp.raise_for_status()
            metafields = meta_resp.json().get("metafields", [])
        # Find custom.density metafield
        density = None
        for mf in metafields:
            if mf.get("namespace") == "custom" and mf.get("key") == "density":
                try:
                    density = float(mf.get("value"))
                except Exception:
                    density = None
                break
        if density is None:
            density = 1.24  # Default density if not found or invalid
        return price, density

async def create_customer_product(
        email: str, 
        product_name: str, 
        material: str, 
        variant: str, 
        infill: int, 
        layer_height: float, 
        nozzle_size: float, 
        filename: str, 
        file_path: str, 
        weight: float = None, 
        price: float = None,
        screenshot_path: str = None,
        complex: bool = False
    ):
    """
    Create a product in Shopify with custom.owner metafield set to customer email.
    This allows filtering products by customer in the storefront.
    """
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Create a unique product handle
    safe_handle = re.sub(r'[^\w\-]', '-', f"{product_name}-{email.split('@')[0]}-{uuid.uuid4().hex[:8]}").lower()
    
    async with httpx.AsyncClient() as client:
        # Create the product - Shopify will automatically create a default variant
        product_mutation = """
        mutation productCreate($product: ProductCreateInput!) {
            productCreate(product: $product) {
                product {
                    id
                    title
                    handle
                    variants(first: 1) {
                        edges {
                            node {
                                id
                            }
                        }
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
            
        # Fetch material and variant names from Shopify
        material_name = "Unknown Material"
        variant_name = ""
        
        try:
            # Extract numeric IDs from GIDs
            def extract_id(gid):
                return gid.split("/")[-1] if gid and gid.startswith("gid://shopify/") else None
            
            material_id = extract_id(material)
            variant_id = extract_id(variant) if variant and variant.startswith("gid://shopify/ProductVariant/") else None
            
            if material_id:
                # Fetch material (product) name
                material_url = f"https://{SHOPIFY_DOMAIN}/admin/api/2023-10/products/{material_id}.json?fields=title"
                material_resp = await client.get(material_url, headers=headers)
                if material_resp.status_code == 200:
                    material_data = material_resp.json()
                    material_name = material_data["product"]["title"]
            
            if variant_id:
                # Fetch variant name
                variant_url = f"https://{SHOPIFY_DOMAIN}/admin/api/2023-10/variants/{variant_id}.json?fields=title"
                variant_resp = await client.get(variant_url, headers=headers)
                if variant_resp.status_code == 200:
                    variant_data = variant_resp.json()
                    variant_name = variant_data["variant"]["title"]
                    # Don't show "Default Title" as it's not meaningful
                    if variant_name == "Default Title":
                        variant_name = ""
        
        except Exception as e:
            print(f"Failed to fetch material/variant names: {str(e)}")
            # Continue with fallback values

        # Create detailed description with all parameters
        description = f"""
        <p><strong>Customer:</strong>{email}</p>
        <p><strong>File:</strong> {filename}</p>
        <p><strong>Material:</strong> {material_name}{" - " + variant_name if variant_name else ""}</p>
        <p><strong>Infill:</strong> {infill}%</p>
        <p><strong>Layer Height:</strong> {layer_height}mm</p>
        <p><strong>Nozzle Size:</strong> {nozzle_size}mm</p>
        """
        
        # Create product input (without variants)
        product_input = {
            "title": product_name,
            "descriptionHtml": description,
            "handle": safe_handle,
            "vendor": "AD-Customs",
            "status": "UNLISTED",  # Make product active on online store
            # "publications": [
            #     {
            #         "publicationId": "gid://shopify/Publication/261868257584"  # Online Store publication ID
            #     }
            # ],
            "metafields": [
                {
                    "namespace": "custom",
                    "key": "owner",
                    "value": email,
                    "type": "single_line_text_field"
                }
            ]
        }
        
        # Add manual-review tag if the model is complex
        if complex:
            product_input["tags"] = ["manual-review"]
        
        variables = {
            "product": product_input
        }
        
        payload = {
            "query": product_mutation,
            "variables": variables
        }
        
        # Debug: Print what we're actually sending
        print(f"DEBUG: Sending GraphQL mutation with variables: {variables}")
        print(f"DEBUG: Product input keys: {list(product_input.keys())}")
        
        url = f"https://{SHOPIFY_DOMAIN}/admin/api/2023-10/graphql.json"
        
        # Create the product - Shopify automatically creates a default variant
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        
        if "errors" in data:
            raise Exception(f"GraphQL errors: {data['errors']}")
        
        user_errors = data.get("data", {}).get("productCreate", {}).get("userErrors", [])
        if user_errors:
            raise Exception(f"Product creation errors: {user_errors}")
        
        product = data.get("data", {}).get("productCreate", {}).get("product")
        if not product:
            raise Exception("Failed to create product")
        
        product_id = product["id"]
        product_handle = product["handle"]
        
        # Now publish the product to the online store using the new publishablePublish mutation
        try:
            publish_mutation = """
            mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) {
                publishablePublish(id: $id, input: $input) {
                    userErrors {
                        field
                        message
                    }
                }
            }
            """
            
            publish_variables = {
                "id": product_id,
                "input": [
                    {
                        "publicationId": "gid://shopify/Publication/261868257584"
                    }
                ]
            }
            
            publish_payload = {
                "query": publish_mutation,
                "variables": publish_variables
            }
            
            print(f"Publishing product {product_id} to online store...")
            publish_resp = await client.post(url, headers=headers, json=publish_payload)
            publish_resp.raise_for_status()
            publish_data = publish_resp.json()
            
            if "errors" in publish_data:
                print(f"Failed to publish product: {publish_data['errors']}")
                # Don't fail the entire operation if publishing fails
            else:
                publish_user_errors = publish_data.get("data", {}).get("publishablePublish", {}).get("userErrors", [])
                if publish_user_errors:
                    print(f"Publish errors: {publish_user_errors}")
                else:
                    print(f"Successfully published product {product_id} to online store")
                    
        except Exception as e:
            print(f"Failed to publish product {product_id}: {str(e)}")
            # Don't fail the entire operation if publishing fails
        
        # Get the default variant ID that Shopify automatically created
        variant_id = None
        variants = product.get("variants", {}).get("edges", [])
        if variants:
            variant_id = variants[0]["node"]["id"]
        
        # Update the default variant with price and weight using REST API
        if variant_id:
            try:
                # Extract numeric IDs
                numeric_product_id = product_id.split("/")[-1]
                numeric_variant_id = variant_id.split("/")[-1]
                
                # Update variant using REST API
                variant_url = f"https://{SHOPIFY_DOMAIN}/admin/api/2023-10/variants/{numeric_variant_id}.json"
                
                variant_data = {"variant": {}}
                
                # Always set price (default to 0.00 if not provided)
                variant_data["variant"]["price"] = str(price + 1) if price is not None else "0.00"
                
                # Set weight if provided
                if weight is not None:
                    variant_data["variant"]["weight"] = weight
                    variant_data["variant"]["weight_unit"] = "g"
                
                print(f"Updating variant {variant_id} with data: {variant_data}")
                
                variant_resp = await client.put(variant_url, headers=headers, json=variant_data)
                variant_resp.raise_for_status()
                variant_result = variant_resp.json()
                print(f"Successfully updated variant {variant_id}")
                
            except Exception as e:
                print(f"Failed to update variant {variant_id}: {str(e)}")
                import traceback
                traceback.print_exc()
                # Don't fail the entire operation if variant update fails
        
        print(f"Created product for customer {email}: {product_id} (handle: {product_handle})")
        
        # Add screenshot as product image if provided (use REST API)
        if screenshot_path and os.path.exists(screenshot_path):
            try:
                # Convert screenshot to base64 for Shopify
                import base64
                with open(screenshot_path, "rb") as img_file:
                    img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                
                # Extract numeric product ID from GraphQL ID
                numeric_product_id = product_id.split("/")[-1]
                
                # Use REST API to upload product image
                image_url = f"https://{SHOPIFY_DOMAIN}/admin/api/2023-10/products/{numeric_product_id}/images.json"
                
                image_data = {
                    "image": {
                        "attachment": img_base64,
                        "filename": f"{product_name}_screenshot.png",
                        "alt": f"3D render of {product_name}"
                    }
                }
                
                img_resp = await client.post(image_url, headers=headers, json=image_data)
                img_resp.raise_for_status()
                img_result = img_resp.json()
                
                if "image" in img_result:
                    print(f"Successfully uploaded screenshot for product {product_id}")
                    print(f"Image URL: {img_result['image'].get('src', 'N/A')}")
                else:
                    print(f"Unexpected response when uploading image: {img_result}")
                        
            except Exception as e:
                print(f"Failed to upload screenshot for product {product_id}: {str(e)}")
                # Don't fail the entire operation if image upload fails
        
        if variant_id:
            print(f"Default variant ID: {variant_id}")
                
        return product_id, product_handle, variant_id
