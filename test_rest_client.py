#!/usr/bin/env python3
"""
Test REST client for TravelPath Photo Service
Sends a test photo via REST API (works through HTTPS)
"""
import requests
import base64
import json

def download_sample_car_image():
    """Download a sample car image from the internet"""
    print("📥 Downloading sample car image...")
    
    url = "https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800&q=80"
    
    response = requests.get(url, timeout=30)
    if response.status_code == 200:
        print(f"✅ Downloaded {len(response.content)} bytes")
        return response.content
    else:
        raise Exception(f"Failed to download image: {response.status_code}")


def test_upload_photo_rest():
    """Test uploading a photo via REST API"""
    
    server = "https://travelpath.cocktails.rocks"
    
    print(f"🔗 Connecting to REST API: {server}")
    
    # Download sample car image
    photo_data = download_sample_car_image()
    
    # Encode to base64
    photo_base64 = base64.b64encode(photo_data).decode('utf-8')
    
    # Create request payload
    payload = {
        "photo_base64": photo_base64,
        "filename": "test_car.jpg",
        "content_type": "image/jpeg",
        "place_name": "La Panacée",
        "address": "14 Rue de l'École de Pharmacie",
        "city": "Montpellier",
        "latitude": 43.6114,
        "longitude": 3.8793,
        "google_place_id": "ChIJFx5wVRuvthIRLCTMxRUbLvk",
        "source_app": "rest_test_client",
        "source_user_id": "test_user_001",
        "place_types": ["art_gallery", "museum"]
    }
    
    print("📤 Sending photo to server...")
    print(f"   Location: La Panacée, Montpellier, France")
    print(f"   Coordinates: 43.6114, 3.8793")
    print(f"   Photo size: {len(photo_data)} bytes")
    
    try:
        response = requests.post(
            f"{server}/photos/upload",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        print("\n" + "=" * 50)
        
        if response.status_code == 201:
            data = response.json()
            print("✅ SUCCESS!")
            print(f"   Photo ID: {data.get('photo_id')}")
            print(f"   Photo URL: {data.get('photo_url')}")
            print(f"   Matched Place ID: {data.get('matched_place_id')}")
            return True
        else:
            print(f"❌ FAILED! Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("🚗 TravelPath REST API Test Client")
    print("=" * 50)
    print()
    
    success = test_upload_photo_rest()
    
    print()
    if success:
        print("🎉 Test completed successfully!")
    else:
        print("💥 Test failed!")



