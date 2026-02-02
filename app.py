from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
import qrcode, io, base64
from datetime import datetime
import math, uuid, os

app = Flask(__name__)
CORS(app)

# ---------------- DATABASE (SAFE) ----------------
MONGO_URL = os.getenv("MONGO_URL")

db = None
sessions = None
attendance = None

if MONGO_URL:
    try:
        client = MongoClient(MONGO_URL)
        db = client["attendify"]
        sessions = db["sessions"]
        attendance = db["attendance"]
        print("✅ MongoDB connected")
    except Exception as e:
        print("❌ MongoDB error:", e)
else:
    print("⚠️ MONGO_URL not set")

# ---------------- UTILITY ----------------
def distance_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ---------------- HOME ----------------
@app.route("/")
def home():
    return jsonify({"status": "Attendify running on Railway 🚄"})

# ---------------- MARK PAGE ----------------
@app.route("/mark.html")
def mark_page():
    return render_template("mark.html")

# ---------------- GENERATE QR ----------------
@app.route("/generate-qr", methods=["POST"])
def generate_qr():
    if not sessions:
        return jsonify({"error": "Database not connected"}), 500

    payload = request.json.get("payload")
    token = str(uuid.uuid4())
    payload["token"] = token

    sessions.insert_one({
        "token": token,
        "payload": payload
    })

    base_url = request.host_url.rstrip("/")
    qr_url = f"{base_url}/mark.html?token={token}"

    qr = qrcode.make(qr_url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)

    img = base64.b64encode(buf.read()).decode()
    return jsonify({"qr": f"data:image/png;base64,{img}"})

# ---------------- MARK ATTENDANCE ----------------
@app.route("/api/attendance/mark", methods=["POST"])
def mark_attendance():
    if not attendance:
        return jsonify({"error": "Database not connected"}), 500

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

    if datetime.utcnow() > datetime.fromisoformat(payload["expiry"]):
        return jsonify({"status": "expired"}), 403

    if attendance.find_one({"token": token, "device_id": device_id}):
        return jsonify({"status": "already_marked"}), 403

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

    return jsonify({"status": "success", "distance": round(dist, 2)})

if __name__ == "__main__":
    app.run()
