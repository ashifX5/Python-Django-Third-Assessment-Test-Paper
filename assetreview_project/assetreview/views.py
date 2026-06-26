"""
views.py — All Views for the Asset Review Panel
"""

import csv
import io
import json
import os
import re
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View
from django.views.decorators.http import require_POST

from .forms import CSVUploadForm

VALID_ASSET_TYPES  = {'image', 'video', 'css', 'js', 'csv'}
ASSET_CODE_PATTERN = re.compile(r'^A-\d{3}$')
VALID_FILTERS      = ['all', 'valid', 'warning', 'rejected']
COOKIE_NAME        = 'asset_filter'


def validate_asset_row(row):
    reasons    = []
    has_error  = False
    has_warning = False

    asset_code = str(row.get('asset_code', '')).strip()
    day_no     = str(row.get('day_no', '')).strip()
    asset_type = str(row.get('asset_type', '')).strip()
    filename   = str(row.get('filename', '')).strip()

    if not ASSET_CODE_PATTERN.match(asset_code):
        reasons.append(f"Invalid asset_code '{asset_code}' (must be A-XXX)")
        has_error = True

    if asset_type not in VALID_ASSET_TYPES:
        reasons.append(f"Invalid asset_type '{asset_type}'")
        has_error = True

    try:
        day = int(day_no)
        if not (1 <= day <= 40):
            reasons.append(f"day_no={day} out of range (1-40)")
            has_error = True
        elif day > 30:
            reasons.append(f"Day {day} exceeds syllabus boundary (Day 30)")
            has_warning = True
    except ValueError:
        reasons.append(f"day_no '{day_no}' is not a number")
        has_error = True

    if not filename:
        reasons.append("filename is empty")
        has_error = True

    if has_error:
        status = 'rejected'
    elif has_warning:
        status = 'warning'
    else:
        status = 'valid'

    return status, reasons


def parse_csv_file(file_obj):
    """
    FIX: Read raw bytes first, decode manually, then parse with io.StringIO.
    This avoids TextIOWrapper taking ownership of the file and closing it,
    which would cause 'I/O operation on closed file' in the view.
    """
    rows = []
    try:
        file_obj.seek(0)
        raw_bytes = file_obj.read()          # read all bytes into memory
        text      = raw_bytes.decode('utf-8')  # decode to string
        reader    = csv.DictReader(io.StringIO(text))  # parse from string

        for i, row in enumerate(reader, start=2):
            try:
                clean_row = {k.strip(): v.strip() for k, v in row.items() if k}
                status, reasons = validate_asset_row(clean_row)
                rows.append({
                    'row_number': i,
                    'asset_code': clean_row.get('asset_code', ''),
                    'day_no':     clean_row.get('day_no', ''),
                    'asset_type': clean_row.get('asset_type', ''),
                    'filename':   clean_row.get('filename', ''),
                    'status':     status,
                    'reasons':    reasons,
                })
            except Exception:
                rows.append({
                    'row_number': i, 'asset_code': '', 'day_no': '',
                    'asset_type': '', 'filename': '',
                    'status': 'rejected',
                    'reasons': ['Malformed row — could not be parsed'],
                })
    except Exception:
        pass
    return rows


class UploadView(View):
    template_name = 'assetreview/upload.html'

    def get(self, request):
        return render(request, self.template_name, {'form': CSVUploadForm()})

    def post(self, request):
        form = CSVUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        uploaded_file = form.cleaned_data['csv_file']

        # Save CSV to media/
        safe_name = f"{uuid.uuid4().hex}_{uploaded_file.name}"
        save_path = os.path.join(settings.MEDIA_ROOT, 'asset_manifests', safe_name)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # Read content once into memory, then write to disk AND parse from memory
        uploaded_file.seek(0)
        file_content = uploaded_file.read()   # read once into memory bytes

        with open(save_path, 'wb') as f:
            f.write(file_content)             # write to disk from memory

        # Parse from the in-memory bytes (file on disk is already saved)
        rows = parse_csv_file(io.BytesIO(file_content))  # use BytesIO, not the original file

        # Save parsed rows as JSON (no database!)
        preview_id   = uuid.uuid4().hex
        preview_file = os.path.join(settings.TEMP_PREVIEW_DIR, f"{preview_id}.json")
        os.makedirs(settings.TEMP_PREVIEW_DIR, exist_ok=True)

        with open(preview_file, 'w') as f:
            json.dump({'filename': uploaded_file.name, 'rows': rows}, f, indent=2)

        return redirect(reverse('assetreview:review', args=[preview_id]))


def review_view(request, preview_id):
    preview_file = os.path.join(settings.TEMP_PREVIEW_DIR, f"{preview_id}.json")

    if not os.path.exists(preview_file):
        return render(request, 'assetreview/upload.html', {
            'form': CSVUploadForm(),
            'error': 'Preview session expired. Please upload again.'
        })

    with open(preview_file, 'r') as f:
        preview_data = json.load(f)

    all_rows     = preview_data.get('rows', [])
    csv_filename = preview_data.get('filename', 'unknown.csv')

    current_filter = request.COOKIES.get(COOKIE_NAME, 'all')
    if current_filter not in VALID_FILTERS:
        current_filter = 'all'

    filtered_rows = all_rows if current_filter == 'all' else [
        r for r in all_rows if r['status'] == current_filter
    ]

    counts = {
        'all':      len(all_rows),
        'valid':    sum(1 for r in all_rows if r['status'] == 'valid'),
        'warning':  sum(1 for r in all_rows if r['status'] == 'warning'),
        'rejected': sum(1 for r in all_rows if r['status'] == 'rejected'),
    }

    context = {
        'rows': filtered_rows,
        'csv_filename': csv_filename,
        'current_filter': current_filter,
        'preview_id': preview_id,
        'counts': counts,
        'valid_filters': VALID_FILTERS,
    }

    response = render(request, 'assetreview/review.html', context)
    response.set_cookie(COOKIE_NAME, current_filter, max_age=7 * 24 * 3600)
    return response


@require_POST
def set_filter_view(request, preview_id):
    selected_filter = request.POST.get('filter', 'all')
    if selected_filter not in VALID_FILTERS:
        selected_filter = 'all'
    response = redirect(reverse('assetreview:review', args=[preview_id]))
    response.set_cookie(COOKIE_NAME, selected_filter, max_age=7 * 24 * 3600)
    return response


def ajax_validate_row(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    status, reasons = validate_asset_row(body)
    return JsonResponse({
        'asset_code': body.get('asset_code', ''),
        'status':     status,
        'reasons':    reasons,
        'message':    'Row is valid.' if status == 'valid'
                      else f"Issues: {'; '.join(reasons)}"
    })
