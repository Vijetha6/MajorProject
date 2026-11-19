"""
Helper script to detect your local IPv4 address for network access.
Run this to find your laptop's IP address on the Wi-Fi network.
"""
import socket

def get_local_ip():
    """Get the local IPv4 address of this machine."""
    try:
        # Create a socket and connect to an external address
        # This doesn't actually send data, just determines the route
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception as e:
        print(f"Error detecting IP: {e}")
        return "127.0.0.1"

if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 5000  # Default Flask port
    
    print("=" * 70)
    print("LOCAL NETWORK ACCESS CONFIGURATION")
    print("=" * 70)
    print(f"\n📱 Your laptop's local IP address: {local_ip}")
    print(f"\n🌐 Access the application from other devices on the same Wi-Fi:")
    print(f"   http://{local_ip}:{port}")
    print(f"\n🔧 To enable network access and QR codes:")
    print(f"\n   1. Open the .env file")
    print(f"   2. Set: FLASK_HOST=0.0.0.0")
    print(f"   3. Set: APPLICATION_BASE_URL=http://{local_ip}:{port}")
    print(f"   4. Save the file and restart the Flask application")
    print(f"\n✅ QR codes in PDFs will then contain: http://{local_ip}:{port}/...")
    print(f"\n⚠️  Note: This IP may change if you reconnect to Wi-Fi or restart your router.")
    print("=" * 70)
