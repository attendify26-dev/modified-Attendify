from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
import qrcode, io, base64
from datetime import datetime
import uuid, math, os

# =====================================================
# FLASK APP
# HTML files ROOT me hain → template_folder="."
# =====================================================
app = Flask(__name__, template_folder=".")
CORS(app)

# =====================================================
# DATABASE (SAFE INIT – RAILWAY STABLE)
# =====================================================
MONGO_URL = os.getenv("MONGO_URL")

db = None
sessions = None
attendance = None

if MONGO_URL:
    try:
        client = MongoClient(
            MONGO_URL,
            serverSelectionTimeoutMS=3000
        )
        client.admin.command("ping")
        db = client["attendify"]
        sessions = db["sessions"]
        attendance = db["attendance"]
        print("MongoDB connected")
    except Exception as e:
        print("MongoDB error:", e)
else:
    print("MONGO_URL not set")

# =====================================================
# UTILS
# =====================================================
def distance_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# =====================================================
# PAGES (RAILWAY ROUTES)
# =====================================================
@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/mark")
def mark():
    return render_template("mark.html")

# =====================================================
# GENERATE QR (AUTO DOMAIN, NO 127.0.0.1)
# =====================================================
@app.route("/generate-qr", methods=["POST"])
def generate_qr():
    if not sessions:
        return jsonify({"error": "DB not connected"}), 500

    payload = request.json.get("payload")
    token = str(uuid.uuid4())
    payload["token"] = token

    sessions.insert_one({
        "token": token,
        "payload": payload
    })

    base_url = request.host_url.rstrip("/")
    qr_url = f"{base_url}/mark?token={token}"

    qr = qrcode.make(qr_url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)

    img = base64.b64encode(buf.read()).decode()

    return jsonify({
        "success": True,
        "qr": f"data:image/png;base64,{img}"
    })

# =====================================================
# MARK ATTENDANCE
# =====================================================
@app.route("/api/attendance/mark", methods=["POST"])
def mark_attendance():
    if not attendance:
        return jsonify({"error": "DB not connected"}), 500

    data = request.json
    token = data.get("token")
    device_id = data.get("device_id")
    name = data.get("name")
    roll = data.get("roll")
    student = data.get("studentLocation")

    session = sessions.find_one({"token": token})
    if not session:
        return jsonify({"status": "invalid_qr"}), 403

    payload = session["payload"]

    # Time check
    if datetime.utcnow() > datetime.fromisoformat(payload["expiry"]):
        return jsonify({"status": "expired"}), 403

    # One device → one attendance
    if attendance.find_one({"token": token, "device_id": device_id}):
        return jsonify({"status": "already_marked"}), 403

    # Radius check
    faculty = payload["facultyLocation"]
    dist = distance_m(
        faculty["lat"], faculty["lng"],
        student["lat"], student["lng"]
    )

    if dist > payload["radius"]:
        return jsonify({"status": "outside_radius"}), 403

    attendance.insert_one({
        "token": token,
        "device_id": device_id,
        "name": name,
        "roll": roll,
        "distance": round(dist, 2),
        "time": datetime.utcnow()
    })

    return jsonify({
        "status": "success",
        "distance": round(dist, 2)
    })
