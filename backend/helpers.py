import httpx
import os
from dotenv import load_dotenv

SHOPIFY_DOMAIN = "jvvkum-8d.myshopify.com"  # Replace with your shop domain

load_dotenv()

SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")  # Ensure this is set in your environment
print(SHOPIFY_TOKEN)

async def get_shopify_price(material_gid, variant_gid=None):
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    # Extract numeric IDs from GIDs
    def extract_id(gid):
        return gid.split("/")[-1] if gid and gid.startswith("gid://shopify/") else None
    product_id = extract_id(material_gid)
    variant_id = extract_id(variant_gid) if variant_gid and variant_gid.startswith("gid://shopify/ProductVariant/") else None

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