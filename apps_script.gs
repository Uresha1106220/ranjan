// ═══════════════════════════════════════════════════════════════════════════
//  VNF Mahila Adhiveshan 2026 — Google Apps Script
//
//  HOW TO DEPLOY:
//  1. Open your Google Sheet
//  2. Click Extensions → Apps Script
//  3. Delete existing code, paste this entire file
//  4. Click Save (💾)
//  5. Click Deploy → New deployment
//     → Type: Web app
//     → Execute as: Me
//     → Who has access: Anyone
//  6. Click Deploy → Copy the Web App URL
//  7. Paste that URL into static/config.js → APPS_SCRIPT_URL
// ═══════════════════════════════════════════════════════════════════════════

const SHEET_NAME = 'Registrations';

function doPost(e) {
  try {
    const sheet = getOrCreateSheet();
    const p     = e.parameter;

    // Save screenshot to Google Drive and get shareable link
    let screenshotUrl = '';
    if (p.screenshot_data && p.screenshot_data.length > 10) {
      try {
        const bytes = Utilities.base64Decode(p.screenshot_data);
        const blob  = Utilities.newBlob(
          bytes,
          p.screenshot_mime || 'image/jpeg',
          p.screenshot_name || 'payment_screenshot.jpg'
        );
        const file = DriveApp.createFile(blob);
        file.setSharing(DriveApp.Access.ANYONE, DriveApp.Permission.VIEW);
        screenshotUrl = file.getUrl();
      } catch (imgErr) {
        screenshotUrl = 'Upload error: ' + imgErr.message;
      }
    }

    // Row number = data rows so far (header = row 1)
    const srNo = Math.max(sheet.getLastRow(), 1);

    sheet.appendRow([
      srNo,
      p.reg_no        || '',
      p.name          || '',
      p.mobile        || '',
      p.city          || '',
      p.payment       || '',
      p.pay_method    || '',
      p.transaction_id|| '',
      screenshotUrl,
      p.submitted_at  || new Date().toLocaleString('en-IN', {timeZone:'Asia/Kolkata'})
    ]);

    return ContentService
      .createTextOutput(JSON.stringify({ status: 'ok', reg: p.reg_no }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: 'error', msg: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// GET request — just for testing the script is alive
function doGet() {
  return ContentService
    .createTextOutput('✅ VNF Apps Script is running!')
    .setMimeType(ContentService.MimeType.TEXT);
}

function getOrCreateSheet() {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  let sheet   = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);

    // Header row
    const headers = [
      'Sr No', 'Registration No', 'Name', 'Mobile', 'City',
      'Payment (100₹)', 'Payment Method', 'Transaction ID',
      'Screenshot Link', 'Submitted At'
    ];
    sheet.appendRow(headers);

    // Style header
    const hdr = sheet.getRange(1, 1, 1, headers.length);
    hdr.setBackground('#7B1F2E');
    hdr.setFontColor('white');
    hdr.setFontWeight('bold');
    hdr.setFontSize(11);
    sheet.setFrozenRows(1);

    // Column widths
    sheet.setColumnWidth(1, 60);   // Sr No
    sheet.setColumnWidth(2, 160);  // Reg No
    sheet.setColumnWidth(3, 180);  // Name
    sheet.setColumnWidth(4, 120);  // Mobile
    sheet.setColumnWidth(5, 140);  // City
    sheet.setColumnWidth(6, 110);  // Payment
    sheet.setColumnWidth(7, 110);  // Method
    sheet.setColumnWidth(8, 160);  // Txn ID
    sheet.setColumnWidth(9, 200);  // Screenshot
    sheet.setColumnWidth(10, 160); // Submitted At
  }
  return sheet;
}
