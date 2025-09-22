from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import json
import random
import importlib

app = Flask(__name__, template_folder='templates')
CORS(app)

# -------------------------
# INTENTS.JSON SAFETY
# -------------------------
INTENTS_FILE = os.path.join(os.path.dirname(__file__), "intents.json")
if os.path.exists(INTENTS_FILE):
    with open(INTENTS_FILE, "r", encoding="utf-8") as f:
        INTENTS_JSON = json.load(f)
else:
    print("Warning: intents.json not found, using empty intents")
    INTENTS_JSON = {"intents": []}

# -------------------------
# FALLBACK RULES
# -------------------------
_FALLBACK_RULES = {
    'greeting': ['hello', 'hi', 'hey', 'good morning', 'good evening'],
    'goodbye': ['bye', 'goodbye', 'see you', 'take care'],
    'thanks': ['thanks', 'thank you', 'thx'],
    'earthquake': ['earthquake', 'tremor', 'shake', 'shaking'],
    'flood': ['flood', 'flooding', 'inundation', 'heavy rain', 'river overflow'],
    'hurricane_cyclone_typhoon': ['cyclone', 'hurricane', 'typhoon', 'storm surge'],
    'wildfire': ['fire', 'wildfire', 'bushfire', 'forest fire'],
    'tsunami': ['tsunami', 'sea wave', 'tidal wave'],
    'preparedness': ['prepare', 'preparation', 'kit', 'emergency kit', 'evacuate', 'evacuation']
}

def _fallback_intent_for_message(message):
    text = (message or '').lower()
    for tag, kws in _FALLBACK_RULES.items():
        for kw in kws:
            if kw in text:
                return tag
    return None

def _build_fallback_response(tag):
    for it in INTENTS_JSON.get('intents', []):
        if it.get('tag') == tag:
            responses = it.get('responses', [])
            if responses:
                pick = random.sample(responses, min(len(responses), 3))
                return '\n'.join(pick)
    return "I'm sorry — I couldn't access the model right now. I can provide general preparedness tips or latest updates."

# -------------------------
# LAZY LOAD ML BACKEND
# -------------------------
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model", "my_model.h5")
tf_model = None

def load_tf_model():
    global tf_model
    if tf_model is None:
        import tensorflow as tf
        if not os.path.exists(MODEL_PATH):
            print("Warning: TensorFlow model file missing")
            return None
        tf_model = tf.keras.models.load_model(MODEL_PATH)
    return tf_model

def _get_main():
    try:
        return importlib.import_module('main')
    except Exception as e:
        print("Warning: main.py import failed:", e)
        return None

import updates
import location

# -------------------------
# ROUTES
# -------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/model_status')
def model_status():
    model_exists = os.path.exists(MODEL_PATH)
    return jsonify({"model_found": model_exists})

@app.route('/handle_message', methods=['POST'])
def handle_message():
    message = request.json.get('message', '')

    main = _get_main()
    if main:
        try:
            intents_list = main.predict_class(message)
            response = main.get_response(intents_list, main.intents)
            return jsonify({'response': response})
        except Exception as e:
            print("Error in main.predict_class:", e)

    # Fallback keyword intent
    tag = _fallback_intent_for_message(message)
    if tag:
        resp_text = _build_fallback_response(tag)
        try:
            tips = updates.fetch_latest_disaster_updates(tag or 'general')
            if tips:
                resp_text += "\n\nLATEST UPDATES:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(tips[:3]))
        except Exception:
            pass
        return jsonify({'response': resp_text})

    # General fallback
    try:
        tips = updates.fetch_latest_disaster_updates('general')
    except Exception:
        tips = []
    fall_text = "I couldn't access the model right now, but here are some important tips and latest updates:\n\n"
    fall_text += "\n".join(f"{i+1}. {t}" for i, t in enumerate(tips))
    return jsonify({'response': fall_text}), 503

@app.route('/latest_updates', methods=['POST'])
def latest_updates():
    data = request.json or {}
    tag = data.get('tag', 'general')
    tips = updates.fetch_latest_disaster_updates(tag)
    return jsonify({'updates': tips})

@app.route('/detect_location', methods=['GET'])
def detect_location_route():
    loc = location.detect_location(request)
    if not loc:
        return jsonify({'error': 'Could not detect location'}), 404
    return jsonify({'location': loc})

@app.route('/nearby_disasters', methods=['POST'])
def nearby_disasters_route():
    data = request.json or {}
    lat = data.get('lat')
    lon = data.get('lon')
    radius = data.get('radius_km') or data.get('radius') or 20
    days = data.get('days')
    country = data.get('country')
    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return jsonify({'error': 'lat and lon required'}), 400
    from disasters import get_nearby_disasters
    res = get_nearby_disasters(lat=lat, lon=lon, radius_km=radius or None, days=days or None, country=country)
    return jsonify({'disasters': res})

@app.route('/map_pois', methods=['POST'])
def map_pois_route():
    data = request.json or {}
    lat = data.get('lat')
    lon = data.get('lon')
    radius = data.get('radius_m') or data.get('radius') or 20000
    kind = data.get('kind') or 'amenity'
    limit = data.get('limit') or 50

    try:
        lat = float(lat)
        lon = float(lon)
        radius = int(radius)
        limit = int(limit)
    except Exception:
        return jsonify({'error': 'lat, lon, radius_m and limit must be numeric'}), 400

    try:
        overpass = importlib.import_module('overpass')
        pois = overpass.search_pois(lat=lat, lon=lon, radius_m=radius, kind=kind, limit=limit)
        return jsonify({'pois': pois})
    except Exception as e:
        return jsonify({'error': 'Could not fetch POIs', 'details': str(e)}), 500

# -------------------------
# MAIN
# -------------------------
if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=PORT, debug=True)
