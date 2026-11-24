# How to Get Your Gemini API Key

## ❌ Common Issue

If you see an error like this:
```
Error: 401 UNAUTHENTICATED
Error: ACCESS_TOKEN_TYPE_UNSUPPORTED
```

This means your API key format is incorrect.

**The correct Gemini API key should start with `AIza...`**

## ✅ How to Get the Correct API Key

### Step 1: Go to Google AI Studio

Open in your browser:
```
https://aistudio.google.com/app/apikey
```

### Step 2: Create API Key

1. Click **"Get API key"** or **"Create API key"**
2. Choose:
   - **"Create API key in new project"** (recommended for new users)
   - OR select an existing Google Cloud project
3. Click **"Create API key"**

### Step 3: Copy Your API Key

You'll see something like:
```
AIzaSyB1234567890abcdefghijklmnopqrstuvwxyz
```

**Important**: 
- ✅ Correct format: `AIzaSy...` (39 characters total)
- ❌ Wrong format: `AQ.` (this is a different Google API type)

### Step 4: Update Your .env File

Open `d:\Projects\MajorProject\.env` and replace the line:

**From:**
```env
GEMINI_API_KEY=your_old_key_here
```

**To:**
```env
GEMINI_API_KEY=AIzaSyYourActualKeyHere123456789
```

### Step 5: Restart Flask Server

After updating the .env file, restart Flask to load the new key:

```powershell
# Stop current server (Ctrl+C in the Flask terminal)
# Or if running in background, check process and kill it

# Start server again
python app.py
```

The server will show:
```
Gemini Loaded
```

## 🔍 Troubleshooting

### Where did you get the current API key?

The key format `AQ.` suggests it might be from:
- ❌ Google Cloud OAuth 2.0 credentials
- ❌ Google API Console (wrong API type)
- ❌ Firebase or other Google service

**You need specifically a Gemini API key from Google AI Studio.**

### Still getting errors?

If you get a new API key and still see errors:

1. **API not enabled**: Make sure "Generative Language API" is enabled
   - Go to: https://console.cloud.google.com/apis/library
   - Search for "Generative Language API"
   - Click "Enable"

2. **Quota exceeded**: Free tier has limits
   - Check usage: https://aistudio.google.com/app/apikey
   - Wait or upgrade to paid tier

3. **Region restrictions**: Some regions may have limited access
   - Try using a VPN if needed

## 📋 Quick Reference

### Correct API Key Format
```
✅ AIzaSyB1234567890abcdefghijklmnopqrstuvwxyz
   (starts with AIzaSy, about 39 characters)

❌ AQ.Ab8RN6J8P-euCshah...
   (starts with AQ., wrong type)
```

### Where to Get It
```
Direct link: https://aistudio.google.com/app/apikey
```

### Supported Models
Your app is configured to use:
```
Model: gemini-3.5-flash-lite
```

This model is available in the free tier.

## 🆓 Free Tier Limits

Google AI Studio free tier includes:
- **15 requests per minute**
- **1,500 requests per day**
- **1 million tokens per day**

This is sufficient for testing and development.

## 🔐 Security Notes

1. **Never commit API keys** to git repositories
2. **Keep .env file** in .gitignore
3. **Rotate keys periodically** for security
4. **Use separate keys** for development and production

## ✅ After Getting New Key

1. Update `.env` file with new `GEMINI_API_KEY=AIzaSy...`
2. Restart Flask server
3. Test with: `python test_gemini_key.py`
4. Should see: `✓ GEMINI API KEY IS VALID AND WORKING`

---

**Need Help?**
- Google AI Studio: https://aistudio.google.com
- API Documentation: https://ai.google.dev/docs
- Get API Key: https://aistudio.google.com/app/apikey
