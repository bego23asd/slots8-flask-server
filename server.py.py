from flask import Flask, request, jsonify
from flask_cors import CORS
import secrets
import string
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# We store license data in a dict:
#   valid_keys[license_key] = {
#       "expiration": <datetime>,
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
        expiration = datetime.utcnow() + timedelta(minutes=2)
    else:
        try:
            days = int(duration)
            expiration = datetime.utcnow() + timedelta(days=days)
        except ValueError:
            # Fallback if invalid input
            expiration = datetime.utcnow() + timedelta(days=1)

    new_key = generate_random_key()
    valid_keys[new_key] = {
        "expiration": expiration,
        "assigned_device": None  # not assigned to any device yet
    }
    return jsonify({
        "license_key": new_key,
        "expires_at": expiration.isoformat() + "Z"
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

    # Check if expired
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
    app.run(port=5000, debug=True)
