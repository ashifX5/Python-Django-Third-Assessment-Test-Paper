"""
forms.py — CSV Upload Form with Validation
"""

import csv
import io
from django import forms

REQUIRED_HEADERS = ['asset_code', 'day_no', 'asset_type', 'filename']


class CSVUploadForm(forms.Form):
    csv_file = forms.FileField(
        label="Upload CSV Manifest",
        help_text="Required columns: asset_code, day_no, asset_type, filename"
    )

    def clean_csv_file(self):
        uploaded_file = self.cleaned_data.get('csv_file')

        # Check 1: File must exist
        if not uploaded_file:
            raise forms.ValidationError("No file was uploaded.")

        # Check 2: Must be a .csv file
        if not uploaded_file.name.lower().endswith('.csv'):
            raise forms.ValidationError(
                f"Only .csv files are accepted. You uploaded: {uploaded_file.name}"
            )

        # Check 3: File must not be empty
        if uploaded_file.size == 0:
            raise forms.ValidationError("The uploaded file is empty.")

        # Check 4: Must have correct headers
        # FIX: Read raw bytes and decode manually — do NOT use TextIOWrapper
        # TextIOWrapper takes ownership and closes the underlying file when done,
        # which means views.py can no longer read the file afterwards.
        try:
            uploaded_file.seek(0)
            raw_bytes = uploaded_file.read()          # read all bytes
            text      = raw_bytes.decode('utf-8')     # decode to string
            reader    = csv.DictReader(io.StringIO(text))  # wrap string, not the file
            headers   = reader.fieldnames

            if not headers:
                raise forms.ValidationError("CSV file has no headers.")

            headers_clean = [h.strip().lower() for h in headers]
            missing = [h for h in REQUIRED_HEADERS if h not in headers_clean]

            if missing:
                raise forms.ValidationError(
                    f"CSV is missing required columns: {missing}. "
                    f"Found: {headers_clean}"
                )

        except UnicodeDecodeError:
            raise forms.ValidationError(
                "File could not be read as text. Make sure it is a valid UTF-8 CSV."
            )

        # IMPORTANT: reset pointer so views.py can read from the start again
        uploaded_file.seek(0)
        return uploaded_file
