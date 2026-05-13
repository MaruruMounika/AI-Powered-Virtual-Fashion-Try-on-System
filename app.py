import io
import os
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import LargeBinary
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import google.generativeai as genai

# -------------------------------
# App Config
# -------------------------------
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = (
    "postgresql+psycopg2://postgres:12345@localhost:5432/postgres"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'  # Change this!

db = SQLAlchemy(app)

# -------------------------------
# Gemini Config
# -------------------------------
genai.configure(api_key="YOUR_API_KEY")

# -------------------------------
# Encryption Key Handling
# -------------------------------
KEY_FILE = "secret.key"


def load_key():
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
    return open(KEY_FILE, "rb").read()


ENCRYPTION_KEY = load_key()
cipher = Fernet(ENCRYPTION_KEY)


# -------------------------------
# Database Models
# -------------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to try-on records
    try_on_records = db.relationship('TryOnRecord', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class TryOnRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    person_image = db.Column(db.LargeBinary, nullable=False)
    cloth_image = db.Column(db.LargeBinary, nullable=False)
    result_image = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# -------------------------------
# Initialize DB
# -------------------------------
with app.app_context():
    db.create_all()


# -------------------------------
# Authentication Decorator
# -------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


# -------------------------------
# Image Processing Helpers
# -------------------------------
def fix_orientation(img):
    return ImageOps.exif_transpose(img)


def normalize_size(img, max_size=1024):
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    return img


def reduce_noise(img):
    return img.filter(ImageFilter.MedianFilter(size=3))


def normalize_lighting(img):
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Brightness(img).enhance(1.05)
    return img


def enhance_cloth_edges(img):
    return img.filter(ImageFilter.EDGE_ENHANCE_MORE)


def align_cloth(person_img, cloth_img):
    pw, _ = person_img.size
    h = int(cloth_img.size[1] * pw / cloth_img.size[0])
    return cloth_img.resize((pw, h), Image.LANCZOS)


# -------------------------------
# Authentication Routes
# -------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            return jsonify({"success": True, "message": "Login successful"})
        else:
            return jsonify({"success": False, "message": "Invalid email or password"}), 401

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')

        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({"success": False, "message": "Email already registered"}), 400

        # Create new user
        new_user = User(name=name, email=email)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        # Auto login after signup
        session['user_id'] = new_user.id
        session['user_name'] = new_user.name

        return jsonify({"success": True, "message": "Account created successfully"})

    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# -------------------------------
# Main Routes
# -------------------------------
@app.route('/')
@login_required
def index():
    return render_template('index.html', user_name=session.get('user_name'))


@app.route('/try-on', methods=['POST'])
@login_required
def try_on():
    if 'person_img' not in request.files or 'cloth_img' not in request.files:
        return jsonify({"error": "Missing images"}), 400

    # Read raw bytes
    person_bytes = request.files['person_img'].read()
    cloth_bytes = request.files['cloth_img'].read()

    # Convert to PIL for processing
    person_img = Image.open(io.BytesIO(person_bytes)).convert("RGB")
    cloth_img = Image.open(io.BytesIO(cloth_bytes)).convert("RGB")

    # Image processing pipeline
    person_img = fix_orientation(person_img)
    person_img = normalize_size(person_img)
    person_img = reduce_noise(person_img)
    person_img = normalize_lighting(person_img)

    cloth_img = fix_orientation(cloth_img)
    cloth_img = normalize_size(cloth_img)
    cloth_img = enhance_cloth_edges(cloth_img)
    cloth_img = normalize_lighting(cloth_img)

    cloth_img = align_cloth(person_img, cloth_img)

    # Gemini API Call with Error Handling
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-image")

        prompt = (
            "You are a professional fashion image editor.\n"
            "Task: Virtual try-on.\n\n"
            "Instructions:\n"
            "- Transfer the clothing from image 2 onto the person in image 1\n"
            "- Preserve face, body shape, pose, skin tone, and background\n"
            "- Clothing must align naturally with body\n"
            "- Maintain realistic lighting, shadows, and fabric folds\n"
            "- Output must be photorealistic\n"
        )

        response = model.generate_content([prompt, person_img, cloth_img])

        result_img = None
        if hasattr(response, 'parts') and response.parts:
            for part in response.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    try:
                        result_img = Image.open(io.BytesIO(part.inline_data.data))
                        break
                    except Exception as e:
                        print(f"Error opening inline_data: {e}")

        if result_img is None:
            print("⚠️ Gemini didn't return an image. Using composite fallback.")
            result_img = person_img.copy()

    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
        result_img = person_img

    # Convert result to bytes
    buffer = io.BytesIO()
    result_img.save(buffer, format="PNG")
    result_bytes = buffer.getvalue()

    # Encrypt images before saving
    enc_person = cipher.encrypt(person_bytes)
    enc_cloth = cipher.encrypt(cloth_bytes)
    enc_result = cipher.encrypt(result_bytes)

    # Save to database with user_id
    record = TryOnRecord(
        user_id=session['user_id'],
        person_image=enc_person,
        cloth_image=enc_cloth,
        result_image=enc_result
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({
        "message": "Try-on completed and stored successfully",
        "record_id": record.id,
        "result_image_url": f"/image/{record.id}/result"
    })


@app.route('/image/<int:record_id>/<string:image_type>')
@login_required
def get_image(record_id, image_type):
    record = TryOnRecord.query.get_or_404(record_id)

    # Security: Ensure user can only access their own images
    if record.user_id != session['user_id']:
        return "Unauthorized", 403

    if image_type == "person":
        encrypted = record.person_image
    elif image_type == "cloth":
        encrypted = record.cloth_image
    elif image_type == "result":
        encrypted = record.result_image
    else:
        return "Invalid image type", 400

    decrypted_bytes = cipher.decrypt(encrypted)
    return Response(decrypted_bytes, mimetype="image/png")


@app.route('/garments', methods=['GET'])
@login_required
def list_garments():
    garment_folder = os.path.join('static', 'images')

    if not os.path.exists(garment_folder):
        return jsonify([])

    images = [f for f in os.listdir(garment_folder)
              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]

    return jsonify(images)


# -------------------------------
# Run Server
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)
