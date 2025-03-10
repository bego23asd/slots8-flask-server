from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import secrets
import string
from datetime import datetime, timedelta
import os
import logging
from zoneinfo import ZoneInfo

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Setup logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Configuration setup (add your production URI if deploying in production)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///licenses.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Timezone for conversion (Asia/Manila)
ph_tz = ZoneInfo("Asia/Manila")

# License model for SQLite
class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_key = db.Column(db.String(16), unique=True, nullable=False)
    expiration = db.Column(db.DateTime, nullable=False)
    assigned_device = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f'<License {self.license_key}>'

# Initialize the database (run this once to create the schema)
@app.before_first_request
def create_tables():
    db.create_all()

def generate_random_key(length=16, group_size=4):
    """
    Generates a random license key in the format: ABCD-EFGH-IJKL-MNOP
    """
    alphabet = string.ascii_uppercase + string.digits
    raw_key = ''.join(secrets.choice(alphabet) for _ in range(length))
    return '-'.join(raw_key[i:i+group_size] for i in range(0, length, group_size))

def parse_duration(duration_str):
    """ Helper function to parse the duration string into a timedelta object. """
    if duration_str == "debug":
        return timedelta(minutes=2)
    try:
        days = int(duration_str)
        return timedelta(days=days)
    except ValueError:
        return timedelta(days=1)  # Default to 1 day if invalid input

@app.route('/owner/generate_license', methods=['POST'])
def owner_generate_license():
    """
    Generates a new license key with expiration.
    Expects JSON payload like: { "duration": "1" } or { "duration": "debug" }
    """
    payload = request.get_json(silent=True) or {}
    duration = payload.get("duration", "1")  # Default to 1 day if no duration provided
    
    expiration_utc = datetime.utcnow() + parse_duration(duration)

    new_key = generate_random_key()

    # Store the license in the database
    new_license = License(
        license_key=new_key,
        expiration=expiration_utc,
        assigned_device=None
    )
    db.session.add(new_license)
    db.session.commit()

    # Convert the UTC expiration to Philippine Time (Asia/Manila)
    expiration_ph = expiration_utc.astimezone(ph_tz)

    logger.debug(f"Generated new license: {new_key}, expires at {expiration_ph.isoformat()}")

    return jsonify({
        "license_key": new_key,
        "expires_at": expiration_ph.isoformat()
    })

@app.route('/client/verify_license', methods=['GET'])
def verify_license():
    """
    Verifies a license key with device ID.
    Example request: GET /client/verify_license?license_key=ABCD-EFGH&device_id=XXXX
    """
    license_key = request.args.get('license_key')
    device_id = request.args.get('device_id')

    if not license_key or not device_id:
        error_message = "No license key or device ID provided"
        logger.error(error_message)
        return jsonify({"valid": False, "error": error_message}), 400

    # Retrieve the license from the database
    license_data = License.query.filter_by(license_key=license_key).first()

    if not license_data:
        logger.warning(f"License key {license_key} not found.")
        return jsonify({"valid": False, "error": "License key not found"})

    # Check if expired
    if datetime.utcnow() >= license_data.expiration:
        db.session.delete(license_data)  # Remove expired license from database
        db.session.commit()
        logger.info(f"License key {license_key} expired.")
        return jsonify({"valid": False, "error": "License key expired"})

    # Check if assigned device matches
    if license_data.assigned_device is None:
        license_data.assigned_device = device_id
        db.session.commit()  # Save the device assignment in the database
        logger.info(f"License key {license_key} assigned to device {device_id}.")
        return jsonify({"valid": True})

    if license_data.assigned_device == device_id:
        logger.info(f"License key {license_key} validated for device {device_id}.")
        return jsonify({"valid": True})

    logger.warning(f"License key {license_key} used on different device {license_data.assigned_device}.")
    return jsonify({"valid": False, "error": "License already used on another device"})

if __name__ == '__main__':
    # Use the PORT environment variable if available, otherwise default to 5000.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
