from flask import Flask, request, jsonify, render_template
import json
import random
from flask_cors import CORS

app = Flask(__name__, template_folder='templates')
CORS(app)

# Load intents for a lightweight fallback responder when the ML backend is unavailable
try:
    INTENTS_JSON = json.load(open('intents.json'))
except Exception:
    INTENTS_JSON = {'intents': []}

# Simple keyword rules for fallback (keeps server responsive if model import fails)
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
    # Find intent in INTENTS_JSON
    for it in INTENTS_JSON.get('intents', []):
        if it.get('tag') == tag:
            responses = it.get('responses', [])
            if responses:
                # choose up to 3 responses to present
                pick = random.sample(responses, min(len(responses), 3))
                return '\n'.join(pick)
    # generic fallback
    return "I'm sorry — I couldn't access the model right now. I can provide general preparedness tips or latest updates."

# Lazy import of heavy backend modules occurs inside routes to keep startup fast
def _get_main():
    import importlib
    return importlib.import_module('main')

import updates
import location


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/handle_message', methods=['POST'])
def handle_message():
    message = request.json.get('message', '')

    # Attempt to import the ML backend lazily. If importing or running the
    # model fails (for example, NLTK not installed in this interpreter),
    # return a helpful fallback with latest updates so the frontend can still
    # provide value to the user.
    try:
        main = _get_main()
    except Exception as e:
        # Instead of immediately returning 503, attempt a lightweight keyword
        # fallback so the chat remains responsive.
        tag = _fallback_intent_for_message(message)
        if tag:
            resp_text = _build_fallback_response(tag)
            # also append a couple of latest updates
            try:
                tips = updates.fetch_latest_disaster_updates(tag or 'general')
                if tips:
                    resp_text += "\n\nLATEST UPDATES:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(tips[:3]))
            except Exception:
                pass
            return jsonify({'response': resp_text})

        # No rule matched — return general tips instead of 503 so frontend can show something useful
        tips = updates.fetch_latest_disaster_updates('general')
        fall_text = "I couldn't access the model right now, but here are some important tips and latest updates:\n\n"
        fall_text += "\n".join(f"{i+1}. {t}" for i, t in enumerate(tips))
        return jsonify({'response': fall_text}), 503

    try:
        intents_list = main.predict_class(message)
        response = main.get_response(intents_list, main.intents)
        return jsonify({'response': response})
    except Exception as e:
        # If runtime error occurs while predicting, return updates instead of 500 stack
        tips = updates.fetch_latest_disaster_updates('general')
        fall_text = "An error occurred while generating a response. Here are some important tips and latest updates:\n\n"
        fall_text += "\n".join(f"{i+1}. {t}" for i, t in enumerate(tips))
        return jsonify({'response': fall_text}), 500


@app.route('/latest_updates', methods=['POST'])
def latest_updates():
    data = request.json or {}
    tag = data.get('tag', 'general')
    tips = updates.fetch_latest_disaster_updates(tag)
    return jsonify({'updates': tips})


@app.route('/detect_location', methods=['GET'])
def detect_location_route():
    # Use server-side IP-based location detection as a fallback to browser geolocation
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
    # Provide defaults in get_nearby_disasters if None
    res = get_nearby_disasters(lat=lat, lon=lon, radius_km=radius or None, days=days or None, country=country)
    return jsonify({'disasters': res})


@app.route('/map_pois', methods=['POST'])
def map_pois_route():
    """Return POIs near a lat/lon using the Overpass programmatic helper.

    Expected JSON body: { lat: float, lon: float, radius_m: int, kind: str, limit: int }
    """
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
        # Lazy import so server startup stays fast
        import importlib
        overpass = importlib.import_module('overpass')
        pois = overpass.search_pois(lat=lat, lon=lon, radius_m=radius, kind=kind, limit=limit)
        return jsonify({'pois': pois})
    except Exception as e:
        # Don't leak internals to clients; return a friendly error
        return jsonify({'error': 'Could not fetch POIs', 'details': str(e)}), 500


# curl -X POST http://127.0.0.1:5000/handle_message -d '{"message":"what is coding"}' -H "Content-Type: application/json"


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)