import os
import csv
import uuid
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_file, Response
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "vnf_mahila_adhiveshan_2026_secret")

# ── Config ────────────────────────────────────────────────────────────────────
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ranjan123")
ALLOWED_EXT    = {"png", "jpg", "jpeg", "gif", "webp", "pdf"}

# ── Detect mode: Supabase (production) vs Local CSV (development) ─────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

if USE_SUPABASE:
    from supabase import create_client
    _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("[INFO] Running in Supabase mode")
else:
    print("[INFO] Running in local CSV mode")

# ── Local file paths (only used when Supabase is NOT configured) ──────────────
_base        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(_base, "admin")
DATA_FILE    = os.path.join(DATA_DIR, "data.csv")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
CSV_HEADERS  = [
    "Sr No", "Registration No", "Name", "Mobile", "City",
    "Payment (100\u20b9)", "Payment Method", "Transaction ID",
    "Screenshot", "Submitted At"
]

# ── Helpers: Local CSV ────────────────────────────────────────────────────────
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

# ── Helpers: Supabase ─────────────────────────────────────────────────────────
def _sb_rows_to_dicts(data):
    """Normalise Supabase row list to the same dict keys as our CSV headers."""
    result = []
    for r in data:
        result.append({
            "Sr No":           str(r.get("sr_no", "")),
            "Registration No": r.get("registration_no", ""),
            "Name":            r.get("name", ""),
            "Mobile":          r.get("mobile", ""),
            "City":            r.get("city", ""),
            "Payment (100\u20b9)": r.get("payment", ""),
            "Payment Method":  r.get("payment_method", ""),
            "Transaction ID":  r.get("transaction_id", ""),
            "Screenshot":      r.get("screenshot_url", ""),
            "Submitted At":    r.get("submitted_at", ""),
        })
    return result

# ── Unified DB operations ─────────────────────────────────────────────────────
def db_next_sr():
    if USE_SUPABASE:
        res = _sb.table("registrations").select("sr_no").order("sr_no", desc=True).limit(1).execute()
        return (res.data[0]["sr_no"] + 1) if res.data else 1
    return len(local_read_all()) + 1

def db_read_all():
    if USE_SUPABASE:
        res = _sb.table("registrations").select("*").order("sr_no").execute()
        return _sb_rows_to_dicts(res.data)
    return local_read_all()

def db_insert(sr_no, reg_no, name, mobile, city, payment, pay_method, txn_id, screenshot, submitted_at):
    if USE_SUPABASE:
        _sb.table("registrations").insert({
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
        }).execute()
    else:
        ensure_local_files()
        with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([sr_no, reg_no, name, mobile, city,
                                    payment, pay_method, txn_id, screenshot, submitted_at])

def upload_screenshot(file_obj, filename):
    """Upload screenshot; returns a URL (Supabase) or local filename."""
    if USE_SUPABASE:
        data = file_obj.read()
        ext  = filename.rsplit(".", 1)[-1].lower()
        mime = "application/pdf" if ext == "pdf" else f"image/{ext}"
        _sb.storage.from_("screenshots").upload(
            filename, data, {"content-type": mime, "x-upsert": "true"}
        )
        return _sb.storage.from_("screenshots").get_public_url(filename)
    else:
        ensure_local_files()
        file_obj.seek(0)
        file_obj.save(os.path.join(SCREENSHOT_DIR, filename))
        return filename   # local filename; served via /admin/screenshot/<fn>

# ── Auth decorator ────────────────────────────────────────────────────────────
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
            errors.append("Screenshot must be an image file (JPG, PNG, etc.).")

        if errors:
            return render_template("form.html", errors=errors, form_data={
                "name": name, "mobile": mobile, "city": city,
                "payment": payment, "pay_method": pay_methods,
                "transaction_id": transaction_id,
            })

        reg_no       = generate_reg_no()
        sr_no        = db_next_sr()
        now          = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        screenshot_ref = ""

        if is_online and screenshot and screenshot.filename:
            ext = screenshot.filename.rsplit(".", 1)[1].lower()
            fname = f"{reg_no}_{secure_filename(screenshot.filename)}"
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


# ── Admin ─────────────────────────────────────────────────────────────────────
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_panel"))
        error = "Incorrect password. Please try again."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_panel():
    rows    = db_read_all()
    search  = request.args.get("q", "").lower()
    if search:
        rows = [r for r in rows if any(search in v.lower() for v in r.values())]
    total   = len(rows)
    paid    = sum(1 for r in rows if r.get("Payment (100\u20b9)") == "Yes")
    unpaid  = total - paid
    online  = sum(1 for r in rows if "Online" in r.get("Payment Method", ""))
    offline = sum(1 for r in rows if "Offline" in r.get("Payment Method", ""))
    return render_template("admin.html", rows=rows, search=request.args.get("q", ""),
                           total=total, paid=paid, unpaid=unpaid,
                           online=online, offline=offline)


@app.route("/admin/download")
@login_required
def admin_download():
    rows = db_read_all()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    csv_bytes = output.getvalue().encode("utf-8-sig")  # utf-8-sig = Excel-friendly BOM
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=VNF_Mahila_Adhiveshan_2026.csv"}
    )


@app.route("/admin/screenshot/<filename>")
@login_required
def view_screenshot(filename):
    """Only used in local mode. In Supabase mode, URL is direct."""
    safe = secure_filename(filename)
    path = os.path.join(SCREENSHOT_DIR, safe)
    if os.path.exists(path):
        return send_file(path)
    return "Screenshot not found", 404


if __name__ == "__main__":
    if not USE_SUPABASE:
        ensure_local_files()
    import webbrowser, threading
    def open_browser():
        import time; time.sleep(1.2)
        webbrowser.open("http://localhost:5000")
    threading.Thread(target=open_browser).start()
    app.run(debug=False, port=5000)
