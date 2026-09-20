import os
import csv
import uuid
import io
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_file, Response
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "vnf_mahila_adhiveshan_2026_secret")

# ── Config ────────────────────────────────────────────────────────────────────
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ranjan123")
ALLOWED_EXT    = {"png", "jpg", "jpeg", "gif", "webp", "pdf"}

# ── Supabase config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

# ── Local file paths (development only) ──────────────────────────────────────
_base          = os.path.dirname(os.path.abspath(__file__))
DATA_DIR       = os.path.join(_base, "admin")
DATA_FILE      = os.path.join(DATA_DIR, "data.csv")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
CSV_HEADERS    = [
    "Sr No", "Registration No", "Name", "Mobile", "City",
    "Payment (100\u20b9)", "Payment Method", "Transaction ID",
    "Screenshot", "Submitted At"
]

# ── Supabase REST helpers (no supabase package needed) ────────────────────────
def _sb_headers(content_type="application/json"):
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  content_type,
        "Prefer":        "return=minimal",
    }

def _sb_get(path, params=""):
    import urllib.request
    url = f"{SUPABASE_URL}/rest/v1/{path}?{params}"
    req = urllib.request.Request(url, headers={
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

def _sb_post(path, data: dict):
    import urllib.request
    url  = f"{SUPABASE_URL}/rest/v1/{path}"
    body = json.dumps(data).encode()
    req  = urllib.request.Request(url, data=body, headers={
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }, method="POST")
    with urllib.request.urlopen(req) as r:
        return r.status

def _sb_upload(filename, file_bytes, mime):
    """Upload file to Supabase Storage via REST."""
    import urllib.request
    url = f"{SUPABASE_URL}/storage/v1/object/screenshots/{filename}"
    req = urllib.request.Request(url, data=file_bytes, headers={
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  mime,
        "x-upsert":      "true",
    }, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            pass
        return f"{SUPABASE_URL}/storage/v1/object/public/screenshots/{filename}"
    except Exception as e:
        print(f"[Screenshot upload error] {e}")
        return ""

# ── Local CSV helpers ─────────────────────────────────────────────────────────
def ensure_local_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADERS)

def local_read_all():
    ensure_local_files()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

# ── Unified DB operations ─────────────────────────────────────────────────────
def db_next_sr():
    if USE_SUPABASE:
        try:
            rows = _sb_get("registrations", "select=sr_no&order=sr_no.desc&limit=1")
            return (rows[0]["sr_no"] + 1) if rows else 1
        except Exception:
            return 1
    return len(local_read_all()) + 1

def db_read_all():
    if USE_SUPABASE:
        try:
            rows = _sb_get("registrations", "order=sr_no.asc")
            result = []
            for r in rows:
                result.append({
                    "Sr No":              str(r.get("sr_no", "")),
                    "Registration No":    r.get("registration_no", ""),
                    "Name":               r.get("name", ""),
                    "Mobile":             r.get("mobile", ""),
                    "City":               r.get("city", ""),
                    "Payment (100\u20b9)":r.get("payment", ""),
                    "Payment Method":     r.get("payment_method", ""),
                    "Transaction ID":     r.get("transaction_id", ""),
                    "Screenshot":         r.get("screenshot_url", ""),
                    "Submitted At":       r.get("submitted_at", ""),
                })
            return result
        except Exception as e:
            print(f"[db_read_all error] {e}")
            return []
    return local_read_all()

def db_insert(sr_no, reg_no, name, mobile, city, payment, pay_method,
              txn_id, screenshot, submitted_at):
    if USE_SUPABASE:
        _sb_post("registrations", {
            "sr_no":           sr_no,
            "registration_no": reg_no,
            "name":            name,
            "mobile":          mobile,
            "city":            city,
            "payment":         payment,
            "payment_method":  pay_method,
            "transaction_id":  txn_id,
            "screenshot_url":  screenshot,
            "submitted_at":    submitted_at,
        })
    else:
        ensure_local_files()
        with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                sr_no, reg_no, name, mobile, city,
                payment, pay_method, txn_id, screenshot, submitted_at
            ])

def upload_screenshot(file_obj, filename):
    if USE_SUPABASE:
        ext  = filename.rsplit(".", 1)[-1].lower()
        mime = "application/pdf" if ext == "pdf" else f"image/{ext}"
        data = file_obj.read()
        return _sb_upload(filename, data, mime)
    else:
        ensure_local_files()
        file_obj.seek(0)
        file_obj.save(os.path.join(SCREENSHOT_DIR, filename))
        return filename

# ── Auth ──────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

def generate_reg_no():
    return f"VNF-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:5].upper()}"

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def form():
    if request.method == "POST":
        name           = request.form.get("name", "").strip()
        mobile         = request.form.get("mobile", "").strip()
        city           = request.form.get("city", "").strip()
        payment        = request.form.get("payment", "")
        pay_methods    = request.form.getlist("pay_method")
        transaction_id = request.form.get("transaction_id", "").strip()
        screenshot     = request.files.get("screenshot")
        is_online      = "Online" in pay_methods

        errors = []
        if not name:   errors.append("Name is required.")
        if not mobile or not mobile.isdigit() or len(mobile) != 10:
            errors.append("Valid 10-digit mobile number is required.")
        if not city:   errors.append("City / Village is required.")
        if not payment: errors.append("Please indicate payment status.")
        if not pay_methods: errors.append("Please select a payment method.")
        if is_online and not transaction_id:
            errors.append("Transaction ID is required for Online payment.")
        if is_online and (not screenshot or screenshot.filename == ""):
            errors.append("Payment screenshot is required for Online payment.")
        if is_online and screenshot and screenshot.filename and not allowed_file(screenshot.filename):
            errors.append("Screenshot must be an image (JPG, PNG, etc.).")

        if errors:
            return render_template("form.html", errors=errors, form_data={
                "name": name, "mobile": mobile, "city": city,
                "payment": payment, "pay_method": pay_methods,
                "transaction_id": transaction_id,
            })

        reg_no         = generate_reg_no()
        sr_no          = db_next_sr()
        now            = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        screenshot_ref = ""

        if is_online and screenshot and screenshot.filename:
            fname          = f"{reg_no}_{secure_filename(screenshot.filename)}"
            screenshot_ref = upload_screenshot(screenshot, fname)

        db_insert(sr_no, reg_no, name, mobile, city, payment,
                  ", ".join(pay_methods), transaction_id, screenshot_ref, now)

        return redirect(url_for("success", reg=reg_no, name=name))

    return render_template("form.html", errors=[], form_data={})


@app.route("/success")
def success():
    return render_template("success.html",
                           reg=request.args.get("reg", ""),
                           name=request.args.get("name", ""))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_panel"))
        error = "Incorrect password."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_panel():
    rows   = db_read_all()
    search = request.args.get("q", "").lower()
    if search:
        rows = [r for r in rows if any(search in str(v).lower() for v in r.values())]
    total   = len(rows)
    paid    = sum(1 for r in rows if r.get("Payment (100\u20b9)") == "Yes")
    unpaid  = total - paid
    online  = sum(1 for r in rows if "Online"  in r.get("Payment Method", ""))
    offline = sum(1 for r in rows if "Offline" in r.get("Payment Method", ""))
    return render_template("admin.html", rows=rows,
                           search=request.args.get("q", ""),
                           total=total, paid=paid, unpaid=unpaid,
                           online=online, offline=offline)


@app.route("/admin/download")
@login_required
def admin_download():
    rows   = db_read_all()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(csv_bytes, mimetype="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=VNF_Mahila_Adhiveshan_2026.csv"})


@app.route("/admin/screenshot/<filename>")
@login_required
def view_screenshot(filename):
    safe = secure_filename(filename)
    path = os.path.join(SCREENSHOT_DIR, safe)
    if os.path.exists(path):
        return send_file(path)
    return "Screenshot not found", 404


if __name__ == "__main__":
    if not USE_SUPABASE:
        ensure_local_files()
    import webbrowser, threading
    def _open():
        import time; time.sleep(1.2)
        webbrowser.open("http://localhost:5000")
    threading.Thread(target=_open).start()
    app.run(debug=False, port=5000)
