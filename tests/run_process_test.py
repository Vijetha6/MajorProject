def main():
    import json
    import os
    import sys
    import types

    # Ensure project root is on sys.path so 'app' can be imported.
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

    os.environ.setdefault('GEMINI_API_KEY', 'DUMMY_KEY')

    fake_google = types.ModuleType('google')
    genai_mod = types.ModuleType('google.genai')

    class FakeModels:
        def generate_content(self, **kwargs):
            class Response:
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
                "other_drug_options": [],
            })
            return Response(sample)

    class FakeClient:
        def __init__(self, api_key=None):
            self.models = FakeModels()

    genai_mod.Client = FakeClient
    fake_google.genai = genai_mod
    sys.modules['google'] = fake_google
    sys.modules['google.genai'] = genai_mod

    from app import app

    image_candidates = [
        'uploads/glyciphage_3a87aec4.jpg',
        'uploads/Hemodell_XT_b260a081.jpg',
    ]
    image_path = next((path for path in image_candidates if os.path.exists(path)), None)
    if not image_path:
        raise SystemExit('No sample image found')

    with open(image_path, 'rb') as image_file:
        data = {
            'language': 'en',
            'images': (image_file, os.path.basename(image_path)),
        }
        response = app.test_client().post(
            '/process',
            data=data,
            content_type='multipart/form-data',
        )
        print('Status:', response.status_code)
        print(response.get_data(as_text=True))


if __name__ == "__main__":
    main()
