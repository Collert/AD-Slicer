import pytest
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import json
from io import BytesIO

# Set up test environment
os.environ["SHOPIFY_TOKEN"] = "test_token_12345"

from main import app
from helpers import create_customer_product


@pytest.fixture
def client():
    """Create a test client for the FastAPI app"""
    return TestClient(app)


@pytest.fixture
def sample_stl_file():
    """Create a sample STL file for testing"""
    # Simple valid STL content (binary format)
    stl_header = b'\x00' * 80  # 80-byte header
    num_triangles = b'\x01\x00\x00\x00'  # 1 triangle (little-endian uint32)
    # One triangle: normal + 3 vertices + attribute byte count
    triangle = (
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00' +  # normal (3 floats)
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00' +  # vertex 1 (3 floats)
        b'\x00\x00\x80\x3f\x00\x00\x00\x00\x00\x00\x00\x00' +  # vertex 2 (3 floats)
        b'\x00\x00\x00\x00\x00\x00\x80\x3f\x00\x00\x00\x00' +  # vertex 3 (3 floats)
        b'\x00\x00'  # attribute byte count
    )
    return stl_header + num_triangles + triangle


@pytest.fixture
def sample_screenshot():
    """Create a sample PNG screenshot for testing"""
    # Minimal valid PNG file (1x1 transparent pixel)
    png_data = (
        b'\x89PNG\r\n\x1a\n'  # PNG signature
        b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'  # IHDR chunk
        b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
        b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'  # IDAT chunk
        b'\r\n-\xb4'
        b'\x00\x00\x00\x00IEND\xaeB`\x82'  # IEND chunk
    )
    return png_data


class TestSaveModelRoute:
    """Test suite for the /api/save-model endpoint"""
    
    @pytest.mark.asyncio
    async def test_create_customer_product_excludes_productCategory(self):
        """
        Test that the productCategory field is NOT included in the GraphQL mutation.
        This field is not supported by Shopify's ProductCreateInput type and causes errors.
        """
        mock_response_data = {
            "data": {
                "productCreate": {
                    "product": {
                        "id": "gid://shopify/Product/12345",
                        "title": "Test Product",
                        "handle": "test-product-handle",
                        "variants": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "gid://shopify/ProductVariant/67890"
                                    }
                                }
                            ]
                        }
                    },
                    "userErrors": []
                }
            }
        }
        
        # Mock the httpx client
        with patch('helpers.httpx.AsyncClient') as MockClient:
            mock_client_instance = MagicMock()
            mock_post = AsyncMock()
            mock_get = AsyncMock()
            mock_put = AsyncMock()
            
            # Set up mock responses
            # For product creation
            product_create_response = MagicMock()
            product_create_response.status_code = 200
            product_create_response.json.return_value = mock_response_data
            product_create_response.raise_for_status = MagicMock()
            
            # For publish mutation
            publish_response = MagicMock()
            publish_response.status_code = 200
            publish_response.json.return_value = {
                "data": {
                    "publishablePublish": {
                        "userErrors": []
                    }
                }
            }
            publish_response.raise_for_status = MagicMock()
            
            # For variant update
            variant_update_response = MagicMock()
            variant_update_response.status_code = 200
            variant_update_response.json.return_value = {
                "variant": {
                    "id": "gid://shopify/ProductVariant/67890",
                    "price": "10.00"
                }
            }
            variant_update_response.raise_for_status = MagicMock()
            
            # Configure mock responses in order
            mock_post.side_effect = [
                product_create_response,  # First POST for product creation
                publish_response,          # Second POST for publishing
            ]
            mock_put.return_value = variant_update_response
            
            # For material/variant name fetches
            material_response = MagicMock()
            material_response.status_code = 200
            material_response.json.return_value = {
                "product": {"title": "Test Material"}
            }
            
            variant_response = MagicMock()
            variant_response.status_code = 200
            variant_response.json.return_value = {
                "variant": {"title": "Test Variant"}
            }
            
            mock_get.side_effect = [material_response, variant_response]
            
            mock_client_instance.post = mock_post
            mock_client_instance.get = mock_get
            mock_client_instance.put = mock_put
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            MockClient.return_value = mock_client_instance
            
            # Call the function
            product_id, product_handle, variant_id = await create_customer_product(
                email="test@example.com",
                product_name="Test Product",
                material="gid://shopify/Product/111",
                variant="gid://shopify/ProductVariant/222",
                infill=15,
                layer_height=0.2,
                nozzle_size=0.4,
                filename="test.stl",
                file_path="/tmp/test.stl",
                weight=100.0,
                price=10.00,
                screenshot_path=None,
                complex=False
            )
            
            # Verify the function succeeded
            assert product_id == "gid://shopify/Product/12345"
            assert product_handle == "test-product-handle"
            assert variant_id == "gid://shopify/ProductVariant/67890"
            
            # Get the actual payload sent to the GraphQL API
            call_args = mock_post.call_args_list[0]
            actual_payload = call_args[1]['json']
            
            # Verify that productCategory is NOT in the product input
            product_input = actual_payload['variables']['product']
            assert 'productCategory' not in product_input, \
                "productCategory should not be included in ProductCreateInput as it's not a valid field"
            
            # Verify that essential fields are present
            assert product_input['title'] == "Test Product"
            assert product_input['handle'] is not None
            assert product_input['vendor'] == "AD-Customs"
            assert product_input['status'] == "UNLISTED"
            assert 'metafields' in product_input
            
    @pytest.mark.asyncio 
    async def test_save_model_endpoint_integration(self, client, sample_stl_file, sample_screenshot):
        """
        Integration test for the /api/save-model endpoint.
        Verifies that the endpoint correctly processes requests without errors.
        """
        mock_response_data = {
            "data": {
                "productCreate": {
                    "product": {
                        "id": "gid://shopify/Product/12345",
                        "title": "Test Model",
                        "handle": "test-model-handle",
                        "variants": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "gid://shopify/ProductVariant/67890"
                                    }
                                }
                            ]
                        }
                    },
                    "userErrors": []
                }
            }
        }
        
        # Mock the httpx client
        with patch('helpers.httpx.AsyncClient') as MockClient:
            mock_client_instance = MagicMock()
            mock_post = AsyncMock()
            mock_get = AsyncMock()
            mock_put = AsyncMock()
            
            # Set up mock responses
            product_create_response = MagicMock()
            product_create_response.status_code = 200
            product_create_response.json.return_value = mock_response_data
            product_create_response.raise_for_status = MagicMock()
            
            publish_response = MagicMock()
            publish_response.status_code = 200
            publish_response.json.return_value = {
                "data": {
                    "publishablePublish": {
                        "userErrors": []
                    }
                }
            }
            publish_response.raise_for_status = MagicMock()
            
            variant_update_response = MagicMock()
            variant_update_response.status_code = 200
            variant_update_response.json.return_value = {
                "variant": {
                    "id": "gid://shopify/ProductVariant/67890",
                    "price": "11.00"
                }
            }
            variant_update_response.raise_for_status = MagicMock()
            
            # Image upload response
            image_response = MagicMock()
            image_response.status_code = 200
            image_response.json.return_value = {
                "image": {
                    "id": 999,
                    "src": "https://example.com/image.png"
                }
            }
            image_response.raise_for_status = MagicMock()
            
            mock_post.side_effect = [
                product_create_response,
                publish_response,
                image_response,
            ]
            mock_put.return_value = variant_update_response
            
            # For material/variant name fetches
            material_response = MagicMock()
            material_response.status_code = 200
            material_response.json.return_value = {
                "product": {"title": "PLA"}
            }
            
            variant_response = MagicMock()
            variant_response.status_code = 200
            variant_response.json.return_value = {
                "variant": {"title": "Red"}
            }
            
            mock_get.side_effect = [material_response, variant_response]
            
            mock_client_instance.post = mock_post
            mock_client_instance.get = mock_get
            mock_client_instance.put = mock_put
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            MockClient.return_value = mock_client_instance
            
            # Create the request with files
            files = {
                'file': ('test.stl', BytesIO(sample_stl_file), 'application/octet-stream'),
                'screenshot': ('screenshot.png', BytesIO(sample_screenshot), 'image/png')
            }
            
            data = {
                'material': 'gid://shopify/Product/111',
                'variant': 'gid://shopify/ProductVariant/222',
                'infill': '15',
                'layerHeight': '0.2',
                'nozzleSize': '0.4',
                'name': 'Test Model',
                'email': 'test@example.com',
                'weight': '100.0',
                'price': '10.0',
                'complex': 'false'
            }
            
            # Send the request
            response = client.post('/api/save-model', files=files, data=data)
            
            # Verify the response
            assert response.status_code == 200
            response_data = response.json()
            assert response_data['message'] == 'Model saved and product created successfully'
            assert 'product_id' in response_data
            assert response_data['product_id'] == 'gid://shopify/Product/12345'
            assert response_data['product_handle'] == 'test-model-handle'
            assert response_data['variant_id'] == 'gid://shopify/ProductVariant/67890'
            
            # Verify productCategory was not included in the GraphQL call
            call_args = mock_post.call_args_list[0]
            actual_payload = call_args[1]['json']
            product_input = actual_payload['variables']['product']
            assert 'productCategory' not in product_input
            

class TestPingRoute:
    """Test suite for the /api/ping endpoint"""
    
    def test_ping_endpoint(self, client):
        """Test that the ping endpoint returns the correct response"""
        response = client.get('/api/ping')
        assert response.status_code == 200
        assert response.json() == {"message": "pong"}
