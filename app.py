from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
import qrcode, io, base64
from datetime import datetime
import math, uuid, os

# ---------------- APP ----------------
app = Flask(__name__)
CORS(app)

# ---------------- DATABASE ----------------
MONGO_URL = os.getenv("MONGO_URL")   # Railway Variable
client = MongoClient(MONGO_URL)
db = client["attendify"]

sessions = db["sessions"]
attendance = db["attendance"]

# ---------------- UTILITY ----------------
def distance_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ---------------- HOME ----------------
@app.route("/")
def home():
    return jsonify({"status": "Attendify backend running"})

# ---------------- MARK PAGE (QR OPENS THIS) ----------------
@app.route("/mark.html")
def mark_page():
    return render_template("mark.html")

# ---------------- GENERATE QR ----------------
@app.route("/generate-qr", methods=["POST"])
def generate_qr():
    payload = request.json.get("payload")

    token = str(uuid.uuid4())
    payload["token"] = token

    sessions.insert_one({
        "token": token,
        "payload": payload
    })

    # 🔥 NO 127.0.0.1 — auto-detect domain (Railway / Local)
    base_url = request.host_url.rstrip("/")
    qr_url = f"{base_url}/mark.html?token={token}"

    qr = qrcode.make(qr_url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)

    img = base64.b64encode(buf.read()).decode()

    return jsonify({
        "success": True,
        "qr": f"data:image/png;base64,{img}"
    })

# ---------------- MARK ATTENDANCE ----------------
@app.route("/api/attendance/mark", methods=["POST"])
def mark_attendance():
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

    # ⏱ TIME CHECK
    if datetime.utcnow() > datetime.fromisoformat(payload["expiry"]):
        return jsonify({"status": "expired"}), 403

    # 🔐 ONE DEVICE = ONE ATTENDANCE
    if attendance.find_one({"token": token, "device_id": device_id}):
        return jsonify({"status": "already_marked"}), 403

    # 📍 RADIUS CHECK
    faculty = payload["facultyLocation"]
    dist = distance_m(
        faculty["lat"], faculty["lng"],
        student["lat"], student["lng"]
    )

    if dist > payload["radius"]:
        return jsonify({
            "status": "outside_radius",
            "distance": round(dist, 2)
        }), 403

    # ✅ SAVE ATTENDANCE
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

# ---------------- RUN (RAILWAY) ----------------
if __name__ == "__main__":
    app.run()
