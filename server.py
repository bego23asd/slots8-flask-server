from flask import Flask, request, jsonify
from flask_cors import CORS
import secrets
import string
from datetime import datetime, timedelta
import os

# If you're on Python 3.9+, zoneinfo is in the standard library.
# For older Python versions, install backports.zoneinfo and import from backports.zoneinfo instead.
from zoneinfo import ZoneInfo

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# We store license data in a dict:
#   valid_keys[license_key] = {
#       "expiration": <datetime (UTC)>,
#       "assigned_device": <string or None>
#   }
valid_keys = {}

def generate_random_key(length=16, group_size=4):
    """
    Generates a random license key in the format: ABCD-EFGH-IJKL-MNOP
    """
    alphabet = string.ascii_uppercase + string.digits
    raw_key = ''.join(secrets.choice(alphabet) for _ in range(length))
    return '-'.join(raw_key[i:i+group_size] for i in range(0, length, group_size))

@app.route('/owner/generate_license', methods=['POST'])
def owner_generate_license():
    """
    Owner endpoint: Generates a new license key with expiration.
    Expects JSON payload:
      { "duration": "1" }   for 1 day
      { "duration": "2" }   for 2 days
      { "duration": "3" }   for 3 days
      { "duration": "debug"} for 2 minutes
    """
    payload = request.get_json(silent=True) or {}
    duration = payload.get("duration", "1")  # default: 1 day

    if duration == "debug":
        expiration_utc = datetime.utcnow() + timedelta(minutes=2)
    else:
        try:
            days = int(duration)
            expiration_utc = datetime.utcnow() + timedelta(days=days)
        except ValueError:
            # Fallback if invalid input
            expiration_utc = datetime.utcnow() + timedelta(days=1)

    new_key = generate_random_key()

    # Store the expiration in UTC internally
    valid_keys[new_key] = {
        "expiration": expiration_utc,
        "assigned_device": None  # not assigned to any device yet
    }

    # Convert the UTC expiration to Philippine Time (Asia/Manila)
    ph_tz = ZoneInfo("Asia/Manila")
    expiration_ph = expiration_utc.astimezone(ph_tz)

    return jsonify({
        "license_key": new_key,
        # Return the local time in ISO format (e.g., 2025-03-10T14:53:36.207138+08:00)
        "expires_at": expiration_ph.isoformat()
    })

@app.route('/client/verify_license', methods=['GET'])
def verify_license():
    """
    Client endpoint: Verifies a license key with device ID.
    Example request:
      GET /client/verify_license?license_key=ABCD-EFGH&device_id=XXXX
    """
    license_key = request.args.get('license_key')
    device_id = request.args.get('device_id')

    if not license_key:
        return jsonify({"valid": False, "error": "No license key provided"}), 400
    if not device_id:
        return jsonify({"valid": False, "error": "No device ID provided"}), 400

    license_data = valid_keys.get(license_key)
    if not license_data:
        return jsonify({"valid": False})

    # Check if expired (compare with current UTC time)
    if datetime.utcnow() >= license_data["expiration"]:
        # Optionally remove it from the dict
        valid_keys.pop(license_key, None)
        return jsonify({"valid": False, "error": "License key expired"})

    # Check if assigned device is None or the same device
    if license_data["assigned_device"] is None:
        # First time use: assign to this device
        license_data["assigned_device"] = device_id
        return jsonify({"valid": True})
    else:
        # If already assigned, it must match the requesting device
        if license_data["assigned_device"] == device_id:
            return jsonify({"valid": True})
        else:
            return jsonify({"valid": False, "error": "License already used on another device"})

if __name__ == '__main__':
    # Use the PORT environment variable if available, otherwise default to 5000.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
