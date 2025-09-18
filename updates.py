import requests
from bs4 import BeautifulSoup


def fetch_latest_disaster_updates(intent_tag):
    """Fetch latest disaster updates from a set of public endpoints.

    This module is lightweight and does not depend on NLTK or the ML model,
    so the frontend can call it without importing heavy dependencies.
    Returns a list of up to 5 human-readable update strings.
    """
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

    for url in urls:
        try:
            resp = requests.get(url, timeout=6)
        except Exception:
            continue

        if resp.status_code != 200:
            continue

        content_type = resp.headers.get('content-type', '').lower()

        # JSON endpoints
        if 'application/json' in content_type or resp.text.lstrip().startswith('{'):
            try:
                data = resp.json()
            except Exception:
                data = None

            if isinstance(data, dict):
                if 'features' in data and isinstance(data['features'], list):
                    for feature in data['features'][:3]:
                        props = feature.get('properties', {})
                        mag = props.get('mag')
                        place = props.get('place')
                        tips.append(f"Alert: Magnitude {mag} earthquake near {place}" if mag or place else "Earthquake alert")
                elif 'data' in data and isinstance(data['data'], list):
                    for item in data['data'][:3]:
                        fields = item.get('fields', {}) if isinstance(item, dict) else {}
                        title = fields.get('name') or fields.get('title') or item.get('title')
                        status = fields.get('status') or 'Active'
                        tips.append(f"Update: {title} - {status}")
                elif 'entry' in data and isinstance(data['entry'], list):
                    for entry in data['entry'][:3]:
                        title = entry.get('title') or 'Update available'
                        tips.append(f"Update: {title}")

        else:
            # Try XML / RSS / HTML
            try:
                soup = BeautifulSoup(resp.content, 'xml')
                items = soup.find_all(['item', 'entry'])
                if items:
                    for it in items[:3]:
                        title = it.find('title')
                        title_text = title.get_text(strip=True) if title else it.get_text(strip=True)
                        if title_text:
                            tips.append(f"Update: {title_text}")
                    if tips:
                        continue

                # Fallback: parse HTML and take headlines
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
                continue

    # Deduplicate while preserving order and limit to 5
    seen = set()
    out = []
    for t in tips:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= 5:
            break

    if not out:
        out = [
            "Remember to stay informed through local news and weather services",
            "Keep emergency contacts handy",
            "Have an emergency kit ready with essentials"
        ]

    return out
