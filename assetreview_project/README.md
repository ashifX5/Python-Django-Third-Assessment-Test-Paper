# Asset Review Panel — Django Project

## What This Project Does
A Django web panel where a reviewer can:
1. **Upload** a CSV manifest of course assets
2. **Preview** all rows in a table with validation status
3. **Re-check** any row instantly using AJAX (no page reload)
4. **Filter** rows by status (all / valid / warning / rejected)
5. Have their **last filter remembered** via a browser cookie

---

## Folder Structure
```
assetreview_project/
├── manage.py
├── sample_manifest.csv          ← Use this to test the upload
│
├── assetreview_project/         ← Django project settings
│   ├── settings.py
│   └── urls.py
│
├── assetreview/                 ← Our Django app
│   ├── middleware.py            ← Blocks uploads > 1MB before view runs
│   ├── forms.py                 ← CSV upload form with header validation
│   ├── views.py                 ← All views (CBV upload + function views)
│   ├── urls.py                  ← URL routes
│   ├── templates/assetreview/
│   │   ├── upload.html          ← Upload page
│   │   └── review.html          ← Preview/review table page
│   └── static/assetreview/
│       └── preview.js           ← AJAX validation JavaScript
│
├── media/asset_manifests/       ← Uploaded CSV files stored here
└── temp_previews/               ← Parsed JSON preview files (no database!)
```

---

## How to Run

### Step 1 — Install Django
```
pip install django
```

### Step 2 — Go into the project folder
```
cd assetreview_project
```

### Step 3 — Run the server
```
python manage.py runserver
```

### Step 4 — Open in browser
```
http://127.0.0.1:8000/
```

### Step 5 — Upload the sample CSV
Use `sample_manifest.csv` (in the root folder) to test.

---

## Key Behaviors Explained

### CSV Upload Validation (forms.py)
- Rejects empty files
- Rejects non-.csv files
- Rejects files with wrong/missing headers
- All validation is in `forms.py`, NOT in the template

### AJAX Preview (preview.js + views.py)
- Reviewer clicks "Re-check" on any row
- JavaScript sends POST to `/ajax/validate-row/`
- Django returns JSON: `{ status, reasons, message }`
- Result shown instantly below the button

### CSRF Protection
- All POST requests (form + AJAX) include a CSRF token
- AJAX reads token from `csrftoken` cookie
- Sends it as `X-CSRFToken` header

### Cookie Filter (asset_filter)
- Reviewer selects a filter: all / valid / warning / rejected
- Filter saved in cookie named `asset_filter` (lasts 7 days)
- On next visit, the same filter is automatically applied

### Upload Size Middleware (middleware.py)
- Runs BEFORE the view
- Checks `CONTENT_LENGTH` header
- If file > 1MB → returns 413 error immediately
- Change limit in `settings.py`: `MAX_UPLOAD_SIZE_BYTES`

### No Database Used
- Uploaded CSV saved to `media/asset_manifests/`
- Parsed rows saved as JSON in `temp_previews/`
- No models, no ORM, no sessions, no DRF
