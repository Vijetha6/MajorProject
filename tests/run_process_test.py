import os
import sys
import json

# Ensure project root is on sys.path so 'app' can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import types

# Provide a dummy GEMINI_API_KEY so app.py doesn't raise
os.environ.setdefault('GEMINI_API_KEY', 'DUMMY_KEY')

# Inject a fake google.genai module to avoid external dependency during tests
fake_google = types.ModuleType('google')
genai_mod = types.ModuleType('google.genai')

class FakeModels:
    def generate_content(self, **kwargs):
        # Return a simple valid JSON response matching expected schema
        class R:
            def __init__(self, text):
                self.text = text
        sample = json.dumps({
            "generic_name": "Information not available",
            "brand_name": "Information not available",
            "strength": "Information not available",
            "dosage_form": "Information not available",
            "expiry_date": "Information not available",
            "uses": ["Information not available"],
            "side_effects": ["Information not available"],
            "same_ingredient_alternatives": [],
            "other_drug_options": []
        })
        return R(sample)

class FakeClient:
    def __init__(self, api_key=None):
        self.models = FakeModels()

genai_mod.Client = FakeClient
fake_google.genai = genai_mod
import sys as _sys
_sys.modules['google'] = fake_google
_sys.modules['google.genai'] = genai_mod

from app import app

client = app.test_client()

img_candidates = [
    'uploads/glyciphage_3a87aec4.jpg',
    'uploads/Hemodell_XT_b260a081.jpg',
]
img_path = None
for p in img_candidates:
    if os.path.exists(p):
        img_path = p
        break

if not img_path:
    print('No sample image found')
    exit(1)

with open(img_path, 'rb') as f:
    # Flask test client expects file tuples as (fileobj, filename)
    data = {
        'language': 'en',
        'images': (f, os.path.basename(img_path))
    }
    resp = client.post('/process', data=data, content_type='multipart/form-data')
    print('Status:', resp.status_code)
    print(resp.get_data(as_text=True))
