#!/usr/bin/env python3
"""
Test gRPC client for TravelPath Photo Service
Sends a test photo to the gRPC server
"""
import grpc
import sys
import os
import requests
from io import BytesIO

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.grpc import photo_service_pb2
from app.grpc import photo_service_pb2_grpc


def download_sample_car_image():
    """Download a sample car image from the internet"""
    print("📥 Downloading sample car image...")
    
    # Free car image from Unsplash
    url = "https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800&q=80"
    
    response = requests.get(url, timeout=30)
    if response.status_code == 200:
        print(f"✅ Downloaded {len(response.content)} bytes")
        return response.content
    else:
        raise Exception(f"Failed to download image: {response.status_code}")


def test_upload_photo():
    """Test uploading a photo via gRPC"""
    
    # Server address
    server = "travelpath.cocktails.rocks:50051"
    
    print(f"🔗 Connecting to gRPC server: {server}")
    
    # Create channel (without TLS for port 50051)
    channel = grpc.insecure_channel(
        server,
        options=[
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
        ]
    )
    
    # Create stub
    stub = photo_service_pb2_grpc.PhotoServiceStub(channel)
    
    # Download sample car image
    photo_data = download_sample_car_image()
    
    # Create GeoPoint
    geo_point = photo_service_pb2.GeoPoint(
        latitude=43.6114,
        longitude=3.8793
    )
    
    # Create request
    request = photo_service_pb2.PhotoRequest(
        # Photo metadata
        description="Test photo - Vintage car near La Panacée art gallery",
        ai_tags=["car", "vintage", "automobile", "test"],
        category="Urban",
        
        # Location
        location_name="La Panacée",
        geo_point=geo_point,
        continent="Europe",
        
        # Author
        author_id="test_user_001",
        author_name="Test User",
        author_avatar="",
        
        # Visibility
        visibility="PUBLIC",
        like_count=0,
        
        # Photo data
        photo_data=photo_data,
        content_type="image/jpeg",
        source_app="grpc_test_client"
    )
    
    print("📤 Sending photo to server...")
    print(f"   Location: La Panacée, Montpellier, France")
    print(f"   Coordinates: {geo_point.latitude}, {geo_point.longitude}")
    print(f"   Photo size: {len(photo_data)} bytes")
    
    try:
        # Send request
        response = stub.UploadPhoto(request, timeout=60)
        
        print("\n" + "=" * 50)
        if response.success:
            print("✅ SUCCESS!")
            print(f"   Photo ID: {response.photo_id}")
            print(f"   Media URLs: {list(response.media_urls)}")
            print(f"   Thumbnail: {response.thumbnail_url}")
        else:
            print("❌ FAILED!")
            print(f"   Error: {response.error_message}")
        print("=" * 50)
        
        return response.success
        
    except grpc.RpcError as e:
        print(f"\n❌ gRPC Error: {e.code()}")
        print(f"   Details: {e.details()}")
        return False
    finally:
        channel.close()


if __name__ == "__main__":
    print("=" * 50)
    print("🚗 TravelPath gRPC Test Client")
    print("=" * 50)
    print()
    
    success = test_upload_photo()
    
    print()
    if success:
        print("🎉 Test completed successfully!")
        sys.exit(0)
    else:
        print("💥 Test failed!")
        sys.exit(1)

