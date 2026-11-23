"""
Test script to verify Gemini API key is working correctly
"""
import os
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_gemini_api():
    """Test Gemini API key"""
    print("=" * 60)
    print("GEMINI API KEY TEST")
    print("=" * 60)
    
    # Get API key
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    print(f"\n1. Configuration:")
    print(f"   API Key: {api_key[:20]}... (hidden)")
    print(f"   Model: {model_name}")
    
    if not api_key:
        print("\n❌ ERROR: GEMINI_API_KEY not found in .env")
        return False
    
    # Configure Gemini client (google.genai)
    try:
        client = genai.Client(api_key=api_key)
        print("\n2. API Configuration: ✓")
    except Exception as e:
        print(f"\n❌ Configuration failed: {e}")
        return False
    
    # Test API with a simple query
    try:
        print("\n3. Testing API with simple query...")
        
        # Simple test prompt
        test_prompt = "What is the generic name of Paracetamol? Answer in one word."
        
        print(f"   Prompt: {test_prompt}")
        print("   Waiting for response...")
        
        response = client.models.generate_content(
            model=model_name,
            contents=test_prompt
        )
        
        if response and response.text:
            print(f"   Response: {response.text.strip()}")
            print("\n✓ Gemini API is working correctly!")
            return True
        else:
            print("\n⚠️  Got empty response from Gemini")
            return False
            
    except Exception as e:
        print(f"\n❌ API test failed: {e}")
        
        # Check for common errors
        error_str = str(e).lower()
        if "api_key" in error_str or "invalid" in error_str:
            print("\n   Possible issue: Invalid API key")
            print("   Please verify your GEMINI_API_KEY in .env")
        elif "quota" in error_str:
            print("\n   Possible issue: API quota exceeded")
            print("   Check your Gemini API usage limits")
        elif "permission" in error_str:
            print("\n   Possible issue: API key doesn't have required permissions")
        
        return False
    
    print("=" * 60)

if __name__ == "__main__":
    try:
        success = test_gemini_api()
        
        if success:
            print("\n" + "=" * 60)
            print("✓ GEMINI API KEY IS VALID AND WORKING")
            print("=" * 60)
            print("\nYour Flask app can now use Gemini for:")
            print("  • Generic name extraction from medicine images")
            print("  • Medicine uses and benefits")
            print("  • Side effects information")
            print("  • Alternative medicines suggestions")
            print("=" * 60)
            exit(0)
        else:
            print("\n" + "=" * 60)
            print("❌ GEMINI API KEY TEST FAILED")
            print("=" * 60)
            print("\nPlease check:")
            print("  1. API key is correct in .env")
            print("  2. API key has not expired")
            print("  3. You have internet connection")
            print("  4. Gemini API service is available")
            print("=" * 60)
            exit(1)
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
