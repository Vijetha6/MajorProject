"""
Verification script to check QR code configuration.
"""
import os
from dotenv import load_dotenv

load_dotenv()

def verify_configuration():
    """Verify all QR code network access configuration."""
    print("=" * 70)
    print("QR CODE NETWORK ACCESS - CONFIGURATION VERIFICATION")
    print("=" * 70)
    
    # Check FLASK_HOST
    flask_host = os.getenv("FLASK_HOST", "127.0.0.1")
    print(f"\n✓ FLASK_HOST: {flask_host}")
    if flask_host == "0.0.0.0":
        print("  ✅ Network access ENABLED (accessible from other devices)")
    else:
        print("  ⚠️  Network access DISABLED (only localhost)")
        print("  💡 To enable: Set FLASK_HOST=0.0.0.0 in .env file")
    
    # Check FLASK_PORT
    flask_port = os.getenv("FLASK_PORT", "5000")
    print(f"\n✓ FLASK_PORT: {flask_port}")
    
    # Check APPLICATION_BASE_URL
    base_url = os.getenv("APPLICATION_BASE_URL", "").strip()
    print(f"\n✓ APPLICATION_BASE_URL: {base_url if base_url else '(not set - will use auto-detection)'}")
    
    if base_url:
        if "127.0.0.1" in base_url or "localhost" in base_url:
            print("  ⚠️  QR codes will use localhost (won't work on mobile)")
            print("  💡 To fix: Update APPLICATION_BASE_URL with your network IP")
        else:
            print("  ✅ QR codes will use configured URL")
    else:
        print("  ⚠️  QR codes will use request host (may still be localhost)")
        print("  💡 Recommended: Set APPLICATION_BASE_URL in .env file")
    
    # Summary
    print("\n" + "=" * 70)
    print("CONFIGURATION SUMMARY")
    print("=" * 70)
    
    if flask_host == "0.0.0.0" and base_url and "127.0.0.1" not in base_url and "localhost" not in base_url:
        print("\n✅ Configuration is CORRECT for network access")
        print(f"\n📱 Mobile devices can access: {base_url}")
        print(f"🔗 QR codes will contain: {base_url}/doctor/patients/.../visits/.../pdf")
        print("\n🚀 Ready to test:")
        print(f"   1. Run: python app.py")
        print(f"   2. Access from laptop: http://localhost:{flask_port}")
        print(f"   3. Access from mobile: {base_url}")
        print(f"   4. Generate a prescription and scan the QR code")
    else:
        print("\n⚠️  Configuration needs adjustment for network access")
        print("\n📝 Required changes in .env file:")
        if flask_host != "0.0.0.0":
            print(f"   - Set FLASK_HOST=0.0.0.0")
        if not base_url or "127.0.0.1" in base_url or "localhost" in base_url:
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                print(f"   - Set APPLICATION_BASE_URL=http://{local_ip}:{flask_port}")
            except:
                print(f"   - Set APPLICATION_BASE_URL=http://YOUR_LOCAL_IP:{flask_port}")
        print("\n💡 Run 'python get_local_ip.py' to get your network IP")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    verify_configuration()
