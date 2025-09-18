import random
import json
import pickle
import numpy as np
import nltk
from nltk.stem import WordNetLemmatizer
# TensorFlow model is loaded lazily below; avoid importing at module import time

# For web scraping
import requests
from bs4 import BeautifulSoup
import updates

lemmatizer = WordNetLemmatizer()
intents = json.load(open('intents.json'))
words = pickle.load(open('model/words.pkl', 'rb'))
classes = pickle.load(open('model/classes.pkl', 'rb'))
# Load the Keras model lazily to avoid import-time failures / heavy memory usage.
model = None
_model_load_attempted = False
_model_load_failed = False

# Lightweight keyword-based intent fallback (used if model can't be loaded).
_RULES = {
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

# Generic preparedness tips used to ensure at least 5 points are returned
DEFAULT_PREPAREDNESS_TIPS = [
    "Keep a 72-hour emergency kit with water, non-perishable food, flashlight, batteries, and first-aid supplies",
    "Know and practice your family evacuation and communication plan",
    "Secure heavy furniture and appliances to walls to prevent tipping",
    "Keep important documents in a waterproof container and have digital backups",
    "Have charged power banks and a battery-powered radio available",
    "Learn basic first aid and CPR",
    "Store extra prescription medications and necessary medical supplies",
    "Keep local emergency numbers saved and accessible"
]

def fetch_latest_disaster_updates(intent_tag):
    # API endpoints for disaster updates
    sources = {
        'earthquake': ['https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson',
                      'https://api.reliefweb.int/v1/disasters?appname=apidoc&filter[type]=earthquake'],
        'flood': ['https://api.reliefweb.int/v1/disasters?appname=apidoc&filter[type]=flood',
                 'https://api.weather.gov/alerts/active?event=Flood'],
        'hurricane_cyclone_typhoon': ['https://api.weather.gov/alerts/active?event=Hurricane',
                                    'https://rss.weather.gov.hk/rss/SeveralWeather.xml'],
        'wildfire': ['https://api.reliefweb.int/v1/disasters?appname=apidoc&filter[type]=wildfire',
                    'https://api.weather.gov/alerts/active?event=Fire'],
        'tsunami': ['https://api.weather.gov/alerts/active?event=Tsunami',
                   'https://api.reliefweb.int/v1/disasters?appname=apidoc&filter[type]=tsunami'],
        'general': ['https://api.reliefweb.int/v1/disasters?appname=apidoc&limit=5']
    }
    
    urls = sources.get(intent_tag, sources['general'])
    tips = []
    
    try:
        for url in urls:
            try:
                resp = requests.get(url, timeout=6)
            except Exception:
                # skip unreachable sources
                continue

            if resp.status_code != 200:
                continue

            content_type = resp.headers.get('content-type', '').lower()

            # If the endpoint returns JSON, try to parse and extract known fields
            if 'application/json' in content_type or resp.text.lstrip().startswith('{'):
                try:
                    data = resp.json()
                except Exception:
                    data = None

                if isinstance(data, dict):
                    # USGS GeoJSON
                    if 'features' in data and isinstance(data['features'], list):
                        for feature in data['features'][:3]:
                            props = feature.get('properties', {})
                            mag = props.get('mag')
                            place = props.get('place')
                            tips.append(f"Alert: Magnitude {mag} earthquake near {place}" if mag or place else "Earthquake alert")

                    # ReliefWeb style
                    elif 'data' in data and isinstance(data['data'], list):
                        for item in data['data'][:3]:
                            fields = item.get('fields', {}) if isinstance(item, dict) else {}
                            title = fields.get('name') or fields.get('title') or item.get('title')
                            status = fields.get('status') or 'Active'
                            tips.append(f"Update: {title} - {status}")

                    # Generic list or dict with entries
                    elif 'entry' in data and isinstance(data['entry'], list):
                        for entry in data['entry'][:3]:
                            title = entry.get('title') or entry.get('title', 'Update available')
                            tips.append(f"Update: {title}")

            # Otherwise try parsing as XML / RSS / HTML and extract item/title tags
            else:
                try:
                    soup = BeautifulSoup(resp.content, 'xml')
                    # RSS / Atom: look for item or entry tags
                    items = soup.find_all(['item', 'entry'])
                    if items:
                        for it in items[:3]:
                            title = it.find('title')
                            title_text = title.get_text(strip=True) if title else it.get_text(strip=True)
                            if title_text:
                                tips.append(f"Update: {title_text}")
                        # if we found items, move to next source
                        if tips:
                            continue

                    # Fallback: search for obvious title elements in HTML
                    if not tips:
                        # Try parsing as HTML and pull links/headlines
                        soup_html = BeautifulSoup(resp.content, 'html.parser')
                        headlines = []
                        for tag in ['h1', 'h2', 'h3', 'a']:
                            for node in soup_html.find_all(tag)[:5]:
                                text = node.get_text(strip=True)
                                if text:
                                    headlines.append(text)
                        for h in headlines[:3]:
                            tips.append(f"Update: {h}")
                except Exception:
                    # ignore parse errors and continue
                    pass
                
        # Add generic tips if no updates found
        if not tips:
            tips = [
                "Remember to stay informed through local news and weather services",
                "Keep emergency contacts handy",
                "Have an emergency kit ready with essentials"
            ]
            
    except Exception as e:
        # In case of any unexpected failure, return sensible generic guidance
        tips = [
            "Stay tuned to local authorities for updates",
            "Follow official evacuation orders if given",
            "Keep emergency supplies ready"
        ]
        
    # Deduplicate while preserving order and limit to 5
    seen = set()
    out = []
    for t in tips:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= 5:
            break
    return out

def clean_up_sentence(sentence):
    """Tokenize and lemmatize input sentence."""
    # Tokenize and normalize to lowercase before lemmatization so tokens
    # match the lowercase vocabulary stored in `words.pkl`.
    sentence_words = nltk.word_tokenize(sentence)
    sentence_words = [lemmatizer.lemmatize(word.lower()) for word in sentence_words]
    return sentence_words

def bag_of_words(sentence):
    """Convert sentence to bag-of-words array."""
    sentence_words = clean_up_sentence(sentence)
    bag = [0] * len(words)
    for w in sentence_words:
        for i, word in enumerate(words):
            if word == w:
                bag[i] = 1
    return np.array(bag)

def predict_class(sentence):
    """Predict intent class for input sentence."""
    global model, _model_load_attempted, _model_load_failed
    # Ensure model is loaded (attempt lazily).
    if model is None and not _model_load_attempted:
        try:
            _model_load_attempted = True
            from tensorflow.keras.models import load_model as _load_model
            model = _load_model('model/chatbot_model.keras')
        except Exception:
            _model_load_failed = True

    # If model failed to load, use a simple keyword-based fallback
    text = sentence.lower() if isinstance(sentence, str) else ''
    if model is None:
        matches = []
        for intent_tag, keywords in _RULES.items():
            for kw in keywords:
                if kw in text:
                    matches.append({'intent': intent_tag, 'probability': '0.9'})
                    break
        # If we found matches, return them sorted (simple deterministic order)
        if matches:
            return matches
        # No rule matched — return empty so the caller can fallback
        return []

    bow = bag_of_words(sentence)
    res = model.predict(np.array([bow]))[0]
    ERROR_THRESHOLD = 0.25
    results = [[i, r] for i, r in enumerate(res) if r > ERROR_THRESHOLD]
    results.sort(key=lambda x: x[1], reverse=True)
    return_list = []
    for r in results:
        return_list.append({'intent': classes[r[0]], 'probability': str(r[1])})
    return return_list

def markdown_bulletify(text):
    """
    Convert a paragraph or checklist into Markdown bullet points or numbered list.
    """
    # Split by sentence or line
    lines = [l.strip() for l in text.replace('\n', '. ').split('. ') if l.strip()]
    if len(lines) == 1:
        # If only one line, return as is
        return f"- {lines[0]}"
    return '\n'.join([f"{idx+1}. {l}" for idx, l in enumerate(lines)])

def get_response(intents_list, intents_json):
    """
    Get chatbot response for predicted intents, merging static and web tips.
    Returns formatted response with preparedness tips and latest updates.
    """
    if not intents_list:
        # Fallback: fetch general tips from web
        web_tips = fetch_latest_disaster_updates("general")
        final_text = "I couldn't find a specific answer, but here are some important tips:\n\n" + \
            "\n".join(f"{i+1}. {t}" for i, t in enumerate(web_tips))
        return final_text

    tag = intents_list[0]['intent']
    list_of_intents = intents_json['intents']
    
    for i in list_of_intents:
        if i['tag'] == tag:
            # Select 4-5 distinct responses (phrases) from the intent's responses
            base_responses = i.get('responses', [])
            num_to_pick = min(5, max(4, len(base_responses))) if base_responses else 5
            try:
                # If there are enough unique responses, sample without replacement
                if len(base_responses) >= num_to_pick:
                    chosen = random.sample(base_responses, num_to_pick)
                else:
                    # Otherwise take all and we'll pad later
                    chosen = list(base_responses)
            except Exception:
                chosen = [random.choice(base_responses)] if base_responses else []

            # Normalize chosen responses into single-line tips
            chosen_tips = []
            for resp in chosen:
                # If a response has multiple sentences, keep it as one concise tip by taking first 2 sentences
                parts = [p.strip() for p in resp.replace('\n', '. ').split('. ') if p.strip()]
                if not parts:
                    continue
                tip_text = '. '.join(parts[:2]) if len(parts) > 1 else parts[0]
                if tip_text not in chosen_tips:
                    chosen_tips.append(tip_text)

            # Pad with defaults to ensure at least 5 tips
            for tip in DEFAULT_PREPAREDNESS_TIPS:
                if len(chosen_tips) >= 5:
                    break
                if tip not in chosen_tips:
                    chosen_tips.append(tip)

            # Truncate to exactly 5 tips
            chosen_tips = chosen_tips[:5]

            # Get latest updates
            web_tips = fetch_latest_disaster_updates(tag)

            # Build final output: numbered list of the selected tips
            final_text = "PREPAREDNESS TIPS:\n"
            for idx, tip in enumerate(chosen_tips, 1):
                final_text += f"{idx}. {tip}\n"

            if web_tips:
                final_text += "\nLATEST UPDATES:\n"
                for idx, tip in enumerate(web_tips, 1):
                    final_text += f"{idx}. {tip}\n"

            return final_text

    # If no intent matched, fallback
    web_tips = fetch_latest_disaster_updates("general")
    return "I couldn't find a specific answer, but here are some important tips:\n\n" + \
           "\n".join(f"{i+1}. {t}" for i, t in enumerate(web_tips))

def main():
    """
    Main loop for chatbot interaction.
    """
    print('Welcome to the Disaster Preparedness Assistant!')
    print('How can I help you today?')
    print('(Type "exit", "quit", or "bye" to end the conversation)\n')
    
    while True:
        message = input('You: ')
        if message.lower() in ['exit', 'quit', 'bye']:
            print('\nGoodbye! Stay safe and prepared.')
            break
        
        ints = predict_class(message)
        res = get_response(ints, intents)
        print('\nAssistant:', res, '\n')

if __name__ == "__main__":
    main()