"""
Gemini Configuration Diagnostic Tool
Safely checks configuration without exposing API keys
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

print("=" * 70)
print("GEMINI CONFIGURATION DIAGNOSTIC")
print("=" * 70)

# 1. Check working directory
print("\n1. Working Directory Check:")
print(f"   Current directory: {os.getcwd()}")
print(f"   Script location: {Path(__file__).parent.absolute()}")

# 2. Check .env file location
env_file = Path(__file__).parent / ".env"
print(f"\n2. .env File Check:")
print(f"   Expected path: {env_file}")
print(f"   File exists: {env_file.exists()}")
if env_file.exists():
    print(f"   File size: {env_file.stat().st_size} bytes")
    print(f"   Last modified: {env_file.stat().st_mtime}")

# 3. Load .env explicitly
print(f"\n3. Loading .env file...")
load_result = load_dotenv(dotenv_path=env_file, override=True)
print(f"   Load result: {load_result}")

# 4. Check environment variables (WITHOUT exposing values)
print(f"\n4. Environment Variable Check:")

# Check if GEMINI_API_KEY exists
gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    key_length = len(gemini_key)
    key_prefix = gemini_key[:6] if len(gemini_key) >= 6 else gemini_key[:2]
    
    print(f"   GEMINI_API_KEY: PRESENT")
    print(f"   Key length: {key_length} characters")
    print(f"   Key prefix: {key_prefix}... (rest hidden)")
    
    # Check key format
    if gemini_key.startswith("AIza"):
        print(f"   Key format: ✓ CORRECT (starts with AIza)")
    elif gemini_key.startswith("AQ."):
        print(f"   Key format: ✗ WRONG (starts with AQ. - OAuth token, not Gemini API key)")
    else:
        print(f"   Key format: ⚠ UNKNOWN (expected to start with AIza)")
        
    # Check for whitespace
    if gemini_key != gemini_key.strip():
        print(f"   ⚠ WARNING: Key has leading/trailing whitespace!")
    
    # Check if it's empty
    if not gemini_key.strip():
        print(f"   ✗ ERROR: Key is empty or only whitespace!")
        
else:
    print(f"   GEMINI_API_KEY: ✗ NOT FOUND")
    print(f"   This means the environment variable is not set")

# Check GEMINI_MODEL
gemini_model = os.getenv("GEMINI_MODEL")
if gemini_model:
    print(f"   GEMINI_MODEL: {gemini_model}")
else:
    print(f"   GEMINI_MODEL: Not set (will use default)")

# 5. Check Windows environment variables (might override .env)
print(f"\n5. Windows Environment Override Check:")
# Check if key exists in system environment (before load_dotenv)
import subprocess
try:
    result = subprocess.run(
        ['powershell', '-Command', '[System.Environment]::GetEnvironmentVariable("GEMINI_API_KEY", "User")'],
        capture_output=True,
        text=True,
        timeout=5
    )
    user_env = result.stdout.strip()
    if user_env:
        print(f"   ⚠ WARNING: GEMINI_API_KEY found in Windows USER environment")
        print(f"   This may override your .env file!")
        print(f"   Length: {len(user_env)} characters")
    else:
        print(f"   ✓ No USER-level override found")
        
    result = subprocess.run(
        ['powershell', '-Command', '[System.Environment]::GetEnvironmentVariable("GEMINI_API_KEY", "Machine")'],
        capture_output=True,
        text=True,
        timeout=5
    )
    machine_env = result.stdout.strip()
    if machine_env:
        print(f"   ⚠ WARNING: GEMINI_API_KEY found in Windows SYSTEM environment")
        print(f"   This may override your .env file!")
    else:
        print(f"   ✓ No SYSTEM-level override found")
except Exception as e:
    print(f"   Could not check Windows environment: {e}")

# 6. Test Gemini client initialization
print(f"\n6. Gemini Client Initialization:")
try:
    from google import genai as test_genai
    print(f"   ✓ google.genai module imported successfully")
    
    if gemini_key and gemini_key.strip():
        try:
            test_client = test_genai.Client(api_key=gemini_key.strip())
            print(f"   ✓ Client object created successfully")
            
            # Try to test the API
            print(f"\n7. API Connection Test:")
            try:
                model_name = gemini_model or "gemini-3.5-flash-lite"
                print(f"   Testing with model: {model_name}")
                print(f"   Sending test request...")
                
                response = test_client.models.generate_content(
                    model=model_name,
                    contents="Say 'OK' if you can read this."
                )
                
                if response and response.text:
                    print(f"   ✓ API WORKING! Response received.")
                    print(f"   Response preview: {response.text[:50]}...")
                else:
                    print(f"   ✗ Empty response from API")
                    
            except Exception as api_error:
                print(f"   ✗ API REQUEST FAILED")
                error_str = str(api_error)
                print(f"   Error type: {type(api_error).__name__}")
                
                # Parse error without exposing key
                if "401" in error_str or "UNAUTHENTICATED" in error_str:
                    print(f"   Error: 401 UNAUTHENTICATED")
                    if "ACCESS_TOKEN_TYPE_UNSUPPORTED" in error_str:
                        print(f"   Reason: ACCESS_TOKEN_TYPE_UNSUPPORTED")
                        print(f"   ✗ This means your API key is NOT a valid Gemini API key")
                        print(f"   ✗ It might be an OAuth token or wrong credential type")
                elif "403" in error_str or "PERMISSION_DENIED" in error_str:
                    print(f"   Error: 403 PERMISSION_DENIED")
                    print(f"   The API key exists but doesn't have required permissions")
                elif "429" in error_str:
                    print(f"   Error: 429 RATE_LIMITED")
                    print(f"   Too many requests - quota exceeded")
                else:
                    # Show error but redact any potential key exposure
                    safe_error = error_str.replace(gemini_key, "[REDACTED]") if gemini_key else error_str
                    print(f"   Error message: {safe_error[:200]}")
                    
        except Exception as client_error:
            print(f"   ✗ Client creation failed: {client_error}")
    else:
        print(f"   ✗ Cannot test client - no valid API key")
        
except ImportError as e:
    print(f"   ✗ Failed to import google.genai: {e}")

# 8. Summary and recommendations
print(f"\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

if gemini_key and gemini_key.strip():
    if gemini_key.startswith("AIza"):
        print("✓ API key is present and has correct format")
        print("\nIf you're still getting 401 errors:")
        print("  1. The Flask server might be using an old key (restart required)")
        print("  2. The API key might be expired or revoked")
        print("  3. Try generating a new key at: https://aistudio.google.com/app/apikey")
    elif gemini_key.startswith("AQ."):
        print("✗ PROBLEM IDENTIFIED: Wrong credential type")
        print("\nYour 'GEMINI_API_KEY' is an OAuth access token, not a Gemini API key!")
        print("\nTo fix:")
        print("  1. Go to: https://aistudio.google.com/app/apikey")
        print("  2. Click 'Create API key' or 'Get API key'")
        print("  3. Copy the key (should start with 'AIza')")
        print("  4. Update GEMINI_API_KEY in .env file")
        print("  5. Restart Flask server")
    else:
        print("⚠ WARNING: API key format is unusual")
        print(f"   Expected to start with 'AIza', but starts with '{key_prefix}'")
        print("\nRecommendation:")
        print("  Get a new Gemini API key from: https://aistudio.google.com/app/apikey")
else:
    print("✗ PROBLEM: No API key found")
    print("\nTo fix:")
    print("  1. Add GEMINI_API_KEY to your .env file")
    print("  2. Get key from: https://aistudio.google.com/app/apikey")

print("=" * 70)
