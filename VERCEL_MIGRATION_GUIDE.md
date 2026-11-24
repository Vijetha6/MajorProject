# Vercel Deployment Migration Guide

## Overview
This guide covers migrating the MedInfo Flask application from local development to Vercel serverless deployment, including database and file storage migrations.

---

## Current Architecture vs Vercel Requirements

### 🚫 Current Blockers

| Component | Current State | Vercel Requirement | Migration Needed |
|-----------|--------------|-------------------|------------------|
| **Database** | SQLite (local file) | Hosted database | ✅ Yes - PostgreSQL/MongoDB |
| **File Storage** | `generated/` folder | Cloud storage | ✅ Yes - S3/Cloudinary/Blob |
| **Runtime** | Long-running Flask server | Serverless functions | ✅ Yes - WSGI adapter |
| **Environment** | `.env` file | Environment variables | ✅ Yes - Vercel dashboard |

---

## Migration Strategy Overview

### Phase 1: Database Migration
- [ ] Choose database provider (PostgreSQL recommended)
- [ ] Create database schema in new system
- [ ] Migrate existing SQLite data
- [ ] Update connection code
- [ ] Test all CRUD operations

### Phase 2: File Storage Migration
- [ ] Choose storage provider (Vercel Blob recommended)
- [ ] Set up storage bucket/container
- [ ] Update PDF generation to upload to cloud
- [ ] Update file serving routes
- [ ] Migrate existing PDFs (optional)

### Phase 3: Vercel Configuration
- [ ] Create `vercel.json` configuration
- [ ] Set up environment variables
- [ ] Configure build settings
- [ ] Deploy to staging
- [ ] Test all functionality

### Phase 4: Production Cutover
- [ ] Update DNS/domain settings
- [ ] Update Twilio webhooks
- [ ] Monitor and verify
- [ ] Backup rollback plan

---

## Phase 1: Database Migration

### Option A: PostgreSQL (Recommended)

**Why PostgreSQL?**
- ✅ Free tier available (Vercel Postgres, Supabase, Neon)
- ✅ Excellent Python support (psycopg2)
- ✅ ACID compliant and reliable
- ✅ Easy migration from SQLite
- ✅ Scalable for production

**Providers:**

1. **Vercel Postgres** (Easiest Integration)
   - Free tier: 256 MB storage, 60 compute hours/month
   - Integrated with Vercel dashboard
   - Auto-configuration of environment variables
   - Pricing: https://vercel.com/docs/storage/vercel-postgres/usage-and-pricing

2. **Supabase** (Most Features)
   - Free tier: 500 MB database, unlimited API requests
   - Includes auth, realtime, storage
   - PostgreSQL with admin dashboard
   - Pricing: https://supabase.com/pricing

3. **Neon** (Best Performance)
   - Free tier: 0.5 GB storage, autoscaling
   - Serverless PostgreSQL with branching
   - Fast cold starts
   - Pricing: https://neon.tech/pricing

**Setup Steps (Vercel Postgres Example):**

1. **Install in Vercel Dashboard:**
   ```
   Project Settings → Storage → Create Database → Postgres
   ```

2. **Get Connection String:**
   ```
   postgresql://user:password@host:5432/database?sslmode=require
   ```

3. **Update Python Dependencies:**
   ```bash
   pip install psycopg2-binary
   pip freeze > requirements.txt
   ```

4. **Update `database.py`:**

```python
# OLD (SQLite)
import sqlite3

def get_db_connection():
    conn = sqlite3.connect('doctor_records.db')
    conn.row_factory = sqlite3.Row
    return conn

# NEW (PostgreSQL)
import psycopg2
import psycopg2.extras
import os

def get_db_connection():
    conn = psycopg2.connect(
        os.getenv('POSTGRES_URL'),
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    return conn
```

5. **Update Schema (SQLite → PostgreSQL):**

Create `migrations/postgres_schema.sql`:

```sql
-- Patients table
CREATE TABLE IF NOT EXISTS patients (
    patient_id VARCHAR(50) PRIMARY KEY,
    patient_name VARCHAR(255) NOT NULL,
    age INTEGER,
    gender VARCHAR(20),
    mobile_number VARCHAR(20),
    address TEXT,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Visits table
CREATE TABLE IF NOT EXISTS visits (
    visit_id VARCHAR(50) PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    doctor_id VARCHAR(50) NOT NULL,
    diagnosis TEXT,
    notes TEXT,
    prescription_filename VARCHAR(255),
    medicines JSONB,  -- Store as JSON instead of TEXT
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
);

-- Medicines inventory table
CREATE TABLE IF NOT EXISTS medicines (
    medicine_id SERIAL PRIMARY KEY,  -- Auto-increment instead of INTEGER PRIMARY KEY
    name VARCHAR(255) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL DEFAULT 0,
    unit VARCHAR(50),
    expiry_date DATE,
    price DECIMAL(10, 2),
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_visits_patient_id ON visits(patient_id);
CREATE INDEX idx_visits_created_at ON visits(created_at DESC);
CREATE INDEX idx_patients_mobile ON patients(mobile_number);
```

6. **Run Migration:**

```bash
psql $POSTGRES_URL -f migrations/postgres_schema.sql
```

7. **Data Migration Script:**

Create `migrations/migrate_sqlite_to_postgres.py`:

```python
import sqlite3
import psycopg2
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Connect to both databases
sqlite_conn = sqlite3.connect('doctor_records.db')
sqlite_conn.row_factory = sqlite3.Row

postgres_conn = psycopg2.connect(os.getenv('POSTGRES_URL'))
postgres_cur = postgres_conn.cursor()

# Migrate patients
print("Migrating patients...")
sqlite_cur = sqlite_conn.cursor()
sqlite_cur.execute("SELECT * FROM patients")
patients = sqlite_cur.fetchall()

for patient in patients:
    postgres_cur.execute("""
        INSERT INTO patients (patient_id, patient_name, age, gender, mobile_number, address, registered_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (patient_id) DO NOTHING
    """, (patient['patient_id'], patient['patient_name'], patient['age'], 
          patient['gender'], patient['mobile_number'], patient['address'], 
          patient['registered_at']))

postgres_conn.commit()
print(f"✅ Migrated {len(patients)} patients")

# Migrate visits
print("Migrating visits...")
sqlite_cur.execute("SELECT * FROM visits")
visits = sqlite_cur.fetchall()

for visit in visits:
    # Parse medicines JSON
    medicines = json.loads(visit['medicines']) if visit['medicines'] else []
    
    postgres_cur.execute("""
        INSERT INTO visits (visit_id, patient_id, doctor_id, diagnosis, notes, 
                          prescription_filename, medicines, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (visit_id) DO NOTHING
    """, (visit['visit_id'], visit['patient_id'], visit['doctor_id'], 
          visit['diagnosis'], visit['notes'], visit['prescription_filename'],
          json.dumps(medicines), visit['created_at']))

postgres_conn.commit()
print(f"✅ Migrated {len(visits)} visits")

# Migrate medicines inventory
print("Migrating medicines inventory...")
sqlite_med_conn = sqlite3.connect('medicine_inventory.db')
sqlite_med_conn.row_factory = sqlite3.Row
sqlite_med_cur = sqlite_med_conn.cursor()
sqlite_med_cur.execute("SELECT * FROM medicines")
medicines = sqlite_med_cur.fetchall()

for medicine in medicines:
    postgres_cur.execute("""
        INSERT INTO medicines (name, quantity, unit, expiry_date, price, added_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (name) DO NOTHING
    """, (medicine['name'], medicine['quantity'], medicine['unit'],
          medicine['expiry_date'], medicine['price'], medicine.get('added_at')))

postgres_conn.commit()
print(f"✅ Migrated {len(medicines)} medicines")

# Close connections
sqlite_conn.close()
sqlite_med_conn.close()
postgres_cur.close()
postgres_conn.close()

print("\n🎉 Migration completed successfully!")
```

Run:
```bash
python migrations/migrate_sqlite_to_postgres.py
```

### Option B: MongoDB Atlas (Alternative)

**Why MongoDB?**
- ✅ Free tier: 512 MB storage
- ✅ Flexible schema (JSON documents)
- ✅ Easy horizontal scaling
- ❌ Different query syntax from SQL

**Setup:**
1. Create account at https://www.mongodb.com/cloud/atlas/register
2. Create free cluster
3. Get connection string: `mongodb+srv://user:pass@cluster.mongodb.net/medinfo`
4. Install: `pip install pymongo`
5. Update code to use MongoDB queries instead of SQL

---

## Phase 2: File Storage Migration

### Option A: Vercel Blob (Recommended for Vercel)

**Why Vercel Blob?**
- ✅ Native Vercel integration
- ✅ Free tier: 1 GB storage
- ✅ Fast edge delivery
- ✅ Simple API
- ✅ No additional accounts needed

**Setup:**

1. **Install Vercel Blob package:**
```bash
pip install vercel-blob-storage
pip freeze > requirements.txt
```

2. **Enable in Vercel Dashboard:**
```
Project Settings → Storage → Blob → Enable
```

3. **Create storage utility `storage_manager.py`:**

```python
import os
from vercel_blob import put, get

def upload_pdf(file_path, filename):
    """Upload PDF to Vercel Blob storage"""
    with open(file_path, 'rb') as f:
        blob = put(
            filename,
            f.read(),
            {
                'access': 'public',
                'content_type': 'application/pdf',
                'folder': 'prescriptions'
            }
        )
    return blob['url']  # Returns public URL

def get_pdf_url(filename):
    """Get public URL for PDF"""
    return f"{os.getenv('BLOB_READ_WRITE_TOKEN_URL')}/prescriptions/{filename}"

def delete_pdf(filename):
    """Delete PDF from storage (optional)"""
    from vercel_blob import delete
    delete(f"prescriptions/{filename}")
```

4. **Update PDF generation in `app.py`:**

```python
# OLD
filepath = os.path.join(GENERATED_FOLDER, filename)
generate_prescription_pdf(data, qr_code_url, filepath)

# NEW
from storage_manager import upload_pdf
import tempfile

# Generate PDF in temporary location
with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
    tmp_path = tmp.name
    generate_prescription_pdf(data, qr_code_url, tmp_path)
    
    # Upload to Vercel Blob
    public_url = upload_pdf(tmp_path, filename)
    
    # Clean up temp file
    os.remove(tmp_path)

# Use public_url for QR code and WhatsApp
qr_code_url = public_url
```

5. **Update prescription viewing route:**

```python
# OLD
@app.route('/prescription/<visit_id>')
def view_prescription_by_visit_id(visit_id):
    visit = doctor_db.get_visit_by_id(visit_id)
    if not visit:
        return render_template('prescription_not_found.html'), 404
    
    filename = visit['prescription_filename']
    return send_from_directory(
        GENERATED_FOLDER,
        filename,
        mimetype='application/pdf',
        as_attachment=False
    )

# NEW
@app.route('/prescription/<visit_id>')
def view_prescription_by_visit_id(visit_id):
    visit = doctor_db.get_visit_by_id(visit_id)
    if not visit:
        return render_template('prescription_not_found.html'), 404
    
    # Redirect to Vercel Blob URL
    from storage_manager import get_pdf_url
    pdf_url = get_pdf_url(visit['prescription_filename'])
    return redirect(pdf_url)
```

### Option B: AWS S3 (Most Common)

**Why S3?**
- ✅ Industry standard
- ✅ 5 GB free tier (12 months)
- ✅ 99.999999999% durability
- ✅ CDN integration (CloudFront)
- ❌ Requires AWS account setup

**Setup:**

1. **Create S3 bucket:**
   - Go to AWS S3 Console
   - Create bucket: `medinfo-prescriptions`
   - Enable public access for objects
   - Set CORS policy for web access

2. **Install boto3:**
```bash
pip install boto3
pip freeze > requirements.txt
```

3. **Create `s3_storage.py`:**

```python
import boto3
import os
from botocore.exceptions import ClientError

s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION', 'us-east-1')
)

BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'medinfo-prescriptions')

def upload_pdf_to_s3(file_path, filename):
    """Upload PDF to S3 and return public URL"""
    try:
        s3_client.upload_file(
            file_path,
            BUCKET_NAME,
            f'prescriptions/{filename}',
            ExtraArgs={
                'ContentType': 'application/pdf',
                'ACL': 'public-read'
            }
        )
        url = f"https://{BUCKET_NAME}.s3.amazonaws.com/prescriptions/{filename}"
        return url
    except ClientError as e:
        print(f"S3 upload failed: {e}")
        return None

def get_pdf_url_from_s3(filename):
    """Get public URL for PDF"""
    return f"https://{BUCKET_NAME}.s3.amazonaws.com/prescriptions/{filename}"
```

4. **Environment variables needed:**
```env
AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXXXXXXXX
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_REGION=us-east-1
S3_BUCKET_NAME=medinfo-prescriptions
```

### Option C: Cloudinary (Easiest for Media)

**Why Cloudinary?**
- ✅ 25 GB free storage
- ✅ PDF transformations and optimization
- ✅ Global CDN
- ✅ Simple API

**Setup:**

1. Sign up at https://cloudinary.com
2. Install: `pip install cloudinary`
3. Get credentials from dashboard
4. Update code:

```python
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

def upload_pdf_to_cloudinary(file_path, filename):
    result = cloudinary.uploader.upload(
        file_path,
        resource_type='raw',
        public_id=f'prescriptions/{filename}',
        folder='medinfo'
    )
    return result['secure_url']
```

---

## Phase 3: Vercel Configuration

### 1. Create `vercel.json`

```json
{
  "version": 2,
  "builds": [
    {
      "src": "app.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/static/(.*)",
      "dest": "/static/$1"
    },
    {
      "src": "/(.*)",
      "dest": "app.py"
    }
  ],
  "env": {
    "FLASK_ENV": "production"
  },
  "regions": ["iad1"]
}
```

### 2. Create `requirements.txt`

Ensure all dependencies are listed:
```bash
pip freeze > requirements.txt
```

Should include:
```
Flask==3.0.0
psycopg2-binary==2.9.9
python-dotenv==1.0.0
twilio==8.10.0
Pillow==10.1.0
fpdf==1.7.2
qrcode==7.4.2
google-generativeai==0.3.0
vercel-blob-storage==1.0.0  # If using Vercel Blob
# OR
boto3==1.34.0  # If using S3
# OR
cloudinary==1.36.0  # If using Cloudinary
```

### 3. Update `app.py` for Serverless

**Add at the top:**
```python
# Vercel serverless compatibility
import sys
import os

# Ensure templates and static folders are found
template_dir = os.path.join(os.path.dirname(__file__), 'templates')
static_dir = os.path.join(os.path.dirname(__file__), 'static')

app = Flask(__name__, 
           template_folder=template_dir,
           static_folder=static_dir)

# For Vercel, expose app object
# This is what Vercel will import
if __name__ != '__main__':
    # Running on Vercel
    application = app
else:
    # Running locally
    if __name__ == '__main__':
        app.run(
            host=os.getenv('FLASK_HOST', '127.0.0.1'),
            port=int(os.getenv('FLASK_PORT', 5000)),
            debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
        )
```

### 4. Set Environment Variables in Vercel

Go to: **Project Settings → Environment Variables**

Add all variables from `.env`:
```
ENCRYPTION_KEY=...
POSTGRES_URL=postgresql://...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
GEMINI_API_KEY=...
BLOB_READ_WRITE_TOKEN=...  # Auto-set if using Vercel Blob
APPLICATION_BASE_URL=https://your-app.vercel.app
DOCTOR_ID=DOC001
DOCTOR_PASSWORD=DOCTOR@123
STAFF_ID=STA001
STAFF_PASSWORD=STAFF@123
```

### 5. Deploy to Vercel

**Method 1: GitHub Integration (Recommended)**

1. Push code to GitHub
2. Go to Vercel dashboard
3. Click "New Project"
4. Import your GitHub repository
5. Vercel auto-detects Python and deploys
6. Wait for deployment (2-3 minutes)

**Method 2: Vercel CLI**

```bash
# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy
vercel --prod
```

### 6. Verify Deployment

1. Check deployment logs in Vercel dashboard
2. Visit your app URL: `https://your-app.vercel.app`
3. Test login
4. Generate a test prescription
5. Verify WhatsApp sending works
6. Scan QR code to test public access

---

## Phase 4: Post-Deployment Tasks

### 1. Update Twilio Webhooks

If you have any Twilio webhooks configured, update them to use your Vercel URL:
```
Old: http://10.158.88.1:5000/twilio/status
New: https://your-app.vercel.app/twilio/status
```

### 2. Custom Domain (Optional)

1. Go to: **Project Settings → Domains**
2. Add your domain: `medinfo.yourdomain.com`
3. Configure DNS records as shown
4. Update environment variables:
   ```
   APPLICATION_BASE_URL=https://medinfo.yourdomain.com
   ```

### 3. Monitoring

**Vercel Analytics:**
- Automatically enabled
- View at: **Project → Analytics**
- Shows request volume, errors, and performance

**Error Tracking:**
Consider adding Sentry for error monitoring:
```bash
pip install sentry-sdk[flask]
```

```python
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn=os.getenv('SENTRY_DSN'),
    integrations=[FlaskIntegration()],
    environment='production'
)
```

### 4. Backups

**Database:**
- Vercel Postgres: Auto-backups included
- Supabase: Point-in-time recovery available
- Manual: Set up daily pg_dump to S3

**File Storage:**
- S3: Enable versioning for rollback
- Vercel Blob: Files are immutable (safe)
- Cloudinary: Backups not needed (redundant storage)

---

## Cost Estimation

### Free Tier Limits

| Service | Free Tier | When You'll Need to Pay |
|---------|-----------|------------------------|
| **Vercel Hosting** | 100 GB bandwidth/mo | >100 GB or team features |
| **Vercel Postgres** | 256 MB storage | >256 MB or need more compute |
| **Vercel Blob** | 1 GB storage | >1 GB |
| **Supabase** | 500 MB database | >500 MB or 2+ projects |
| **AWS S3** | 5 GB storage | >5 GB (after 12 months) |
| **Cloudinary** | 25 GB storage | >25 GB or transformations |
| **Twilio WhatsApp** | $15 trial credit | After credit used (~3000 messages) |

### Monthly Cost Estimates (After Free Tier)

**Small Clinic (100 prescriptions/day):**
- Vercel: $0 (within free tier)
- Database: $0 (within free tier)
- Storage: $0 (3 GB used)
- Twilio WhatsApp: $15/month
- **Total: ~$15/month**

**Medium Clinic (500 prescriptions/day):**
- Vercel: $0 (within free tier)
- Database: $10/month (Vercel Postgres Pro)
- Storage: $5/month (50 GB S3)
- Twilio WhatsApp: $75/month
- **Total: ~$90/month**

**Large Clinic (2000 prescriptions/day):**
- Vercel: $20/month (Pro plan)
- Database: $25/month (larger instance)
- Storage: $15/month (200 GB S3)
- Twilio WhatsApp: $300/month
- **Total: ~$360/month**

---

## Rollback Plan

If something goes wrong after deployment:

### 1. Immediate Rollback (Vercel)
```bash
vercel rollback
```
Or in dashboard: **Deployments → Previous Deployment → Promote to Production**

### 2. Database Rollback
- Restore from backup:
  ```bash
  pg_restore -d $POSTGRES_URL backup.dump
  ```

### 3. Keep Local Version Running
- Don't shut down local Flask server until Vercel is fully verified
- Can switch back to local by updating any external links

### 4. Emergency Fallback
If everything fails:
1. Point domain back to local server
2. Use ngrok temporarily for public access
3. Debug and redeploy when ready

---

## Testing Checklist

### Before Going Live:

- [ ] Database connection works (test all CRUD operations)
- [ ] PDF generation works and saves to cloud storage
- [ ] PDF viewing works via public URL
- [ ] QR code scanning works and opens correct PDF
- [ ] WhatsApp PDF sending works with cloud URLs
- [ ] Doctor login/logout works
- [ ] Patient registration works
- [ ] Prescription history loads correctly
- [ ] Medicine inventory CRUD works
- [ ] All static assets (CSS/JS/images) load
- [ ] HTTPS is enforced (no mixed content warnings)
- [ ] Environment variables are all set correctly
- [ ] Error pages display properly (404, 500)
- [ ] Mobile responsiveness works
- [ ] Load testing (generate 10 prescriptions rapidly)

---

## Common Issues and Solutions

### Issue: "Module not found" error on Vercel

**Solution:**
- Ensure all dependencies in `requirements.txt`
- Run `pip freeze > requirements.txt` locally
- Redeploy

### Issue: Database connection timeout

**Solution:**
- Check connection string has `?sslmode=require`
- Ensure database allows connections from 0.0.0.0/0
- Check Vercel region matches database region

### Issue: PDFs not loading (404 error)

**Solution:**
- Verify cloud storage credentials are set
- Check upload function returns valid URL
- Test URL directly in browser
- Ensure blob/bucket is public-readable

### Issue: WhatsApp sends but no PDF attachment

**Solution:**
- Verify PDF URL is publicly accessible (not localhost)
- Check Twilio logs for specific error
- Ensure URL uses HTTPS (required for media)
- Test URL in curl: `curl -I https://your-url/prescription/xxx`

### Issue: "Internal Server Error" on routes

**Solution:**
- Check Vercel function logs
- Look for Python exceptions
- Add more error logging:
  ```python
  import traceback
  try:
      # your code
  except Exception as e:
      print(traceback.format_exc())
      raise
  ```

---

## Summary

**What You Need to Migrate:**
1. ✅ SQLite → PostgreSQL (Vercel Postgres or Supabase)
2. ✅ Local files → Cloud storage (Vercel Blob, S3, or Cloudinary)
3. ✅ Long-running server → Serverless functions (Vercel handles this)
4. ✅ .env file → Environment variables (Vercel dashboard)

**Estimated Timeline:**
- Database migration: 4-6 hours
- Storage migration: 3-4 hours
- Vercel configuration: 2-3 hours
- Testing and fixes: 4-6 hours
- **Total: 13-19 hours**

**Recommended Approach:**
1. Start with database migration (test locally first)
2. Then migrate file storage (test locally first)
3. Deploy to Vercel staging
4. Test thoroughly
5. Deploy to production

Good luck with your migration! 🚀
