/*
=============================================================================
  preview.js — AJAX Row Validation
=============================================================================

  WHAT THIS FILE DOES:
  --------------------
  When the reviewer clicks "Re-check" on any row, this JavaScript:
    1. Reads that row's data (asset_code, day_no, etc.)
    2. Sends it to our Django AJAX endpoint via POST
    3. Gets back a JSON response with the validation result
    4. Shows the result below the button — WITHOUT reloading the page

  WHY POST AND NOT GET?
  ----------------------
  GET requests are for FETCHING data — they should not change anything.
  POST requests are for SENDING data to be processed.
  Since we're sending a row of data to be validated, we use POST.

  CSRF TOKEN:
  -----------
  Django requires a CSRF token on every POST request (even AJAX).
  This prevents malicious websites from making POST requests on your behalf.
  We read the token from the browser cookie named 'csrftoken'
  and send it in the request header 'X-CSRFToken'.
=============================================================================
*/


/**
 * Reads the Django CSRF token from the browser's cookies.
 * Django sets a cookie named 'csrftoken' automatically.
 *
 * @returns {string} The CSRF token value
 */
function getCsrfToken() {
  const cookies = document.cookie.split(';');
  for (let cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === 'csrftoken') {
      return decodeURIComponent(value);
    }
  }
  return '';
}


/**
 * Called when a reviewer clicks "Re-check" on a table row.
 * Reads row data, sends AJAX POST, displays result.
 *
 * @param {HTMLElement} button - The button that was clicked
 */
function validateRow(button) {
  // ── Step 1: Find the parent <tr> row ──
  const row = button.closest('tr');

  // ── Step 2: Read data attributes set by Django template ──
  const rowData = {
    asset_code: row.dataset.assetCode  || '',
    day_no:     row.dataset.dayNo      || '',
    asset_type: row.dataset.assetType  || '',
    filename:   row.dataset.filename   || '',
  };

  // ── Step 3: Find the result div for this row ──
  const resultDiv = row.querySelector('.ajax-result');

  // Show loading state
  button.textContent  = 'Checking...';
  button.disabled     = true;
  resultDiv.className = 'ajax-result';
  resultDiv.textContent = '';

  // ── Step 4: Get the AJAX URL from the hidden div Django put in the page ──
  const djangoData = document.getElementById('django-data');
  const ajaxUrl    = djangoData ? djangoData.dataset.ajaxUrl : '/ajax/validate-row/';

  // ── Step 5: Send POST request with CSRF token ──
  fetch(ajaxUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken':  getCsrfToken(),    // Required! Django checks this.
    },
    body: JSON.stringify(rowData),        // Send row as JSON
  })

  // ── Step 6: Parse JSON response from Django ──
  .then(function(response) {
    if (!response.ok) {
      throw new Error('Server error: ' + response.status);
    }
    return response.json();
  })

  // ── Step 7: Display the result ──
  .then(function(data) {
    // Update the result div with status-coloured message
    resultDiv.className   = 'ajax-result ' + data.status;
    resultDiv.textContent = data.message;

    // Reset button
    button.textContent = 'Re-check';
    button.disabled    = false;
  })

  // ── Step 8: Handle errors gracefully ──
  .catch(function(error) {
    resultDiv.className   = 'ajax-result rejected';
    resultDiv.textContent = 'Error: ' + error.message;

    button.textContent = 'Re-check';
    button.disabled    = false;
  });
}
