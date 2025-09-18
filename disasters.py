import requests
from cache import ttl_cache
import math
import time
from datetime import datetime, timedelta
from threading import Lock
import os
try:
    import pycountry
except Exception:
    pycountry = None

# Optional Redis support
_REDIS = None
if os.environ.get('REDIS_URL'):
    try:
        import redis
        _REDIS = redis.Redis.from_url(os.environ.get('REDIS_URL'))
    except Exception:
        _REDIS = None

# Simple in-memory TTL cache for GET requests / expensive computations
_CACHE = {}
_CACHE_LOCK = Lock()


def _cached_get(url, ttl=300):
    """GET with simple TTL cache keyed by URL."""
    # If Redis is configured, use it as a cache backend
    if _REDIS:
        try:
            key = 'disasters:cache:' + url
            v = _REDIS.get(key)
            if v:
                return requests.utils.json.loads(v)
            r = requests.get(url, timeout=8)
            if r.status_code != 200:
                return None
            data = r.json()
            _REDIS.setex(key, ttl, requests.utils.json.dumps(data))
            return data
        except Exception:
            pass

    now = time.time()
    with _CACHE_LOCK:
        rec = _CACHE.get(url)
        if rec and rec[0] > now:
            return rec[1]
    try:
        r = requests.get(url, timeout=8)
        if r.status_code != 200:
            return None
        data = r.json()
        with _CACHE_LOCK:
            _CACHE[url] = (now + ttl, data)
        return data
    except Exception:
        return None


def _country_to_iso(country_name):
    """Return (alpha2, alpha3) for a country name, or (None, None)."""
    if not country_name or not pycountry:
        return (None, None)
    try:
        # Try lookup by common name or official name
        c = pycountry.countries.get(name=country_name)
        if not c:
            c = pycountry.countries.get(common_name=country_name)
        if not c:
            # fallback: search by fuzzy name
            for candidate in pycountry.countries:
                if country_name.lower() in (candidate.name or '').lower() or (getattr(candidate, 'common_name', '') or '').lower().find(country_name.lower()) >= 0:
                    c = candidate
                    break
        if not c:
            return (None, None)
        return (getattr(c, 'alpha_2', None), getattr(c, 'alpha_3', None))
    except Exception:
        return (None, None)


def _query_usgs_earthquakes(lat, lon, maxradiuskm=200, days=30, limit=10):
    """Query USGS for earthquakes near a point in the last `days` days.

    Returns a list of dicts with keys: type='earthquake', title, mag, place, time (iso), lat, lon, url
    """
    starttime = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
    url = (
        'https://earthquake.usgs.gov/fdsnws/event/1/query'
        f'?format=geojson&latitude={lat}&longitude={lon}&maxradiuskm={maxradiuskm}&starttime={starttime}&limit={limit}'
    )
    try:
        data = _cached_get(url, ttl=300)
        if not data:
            return []
        out = []
        for feat in data.get('features', [])[:limit]:
            props = feat.get('properties', {})
            geom = feat.get('geometry', {})
            coords = geom.get('coordinates', [None, None])
            mag = props.get('mag')
            place = props.get('place')
            time_ms = props.get('time')
            time_iso = None
            if time_ms:
                time_iso = datetime.utcfromtimestamp(time_ms / 1000.0).isoformat() + 'Z'
            out.append({
                'type': 'earthquake',
                'title': f"M {mag} - {place}" if mag and place else place or 'Earthquake',
                'mag': mag,
                'place': place,
                'time': time_iso,
                'lat': coords[1] if len(coords) > 1 else None,
                'lon': coords[0] if coords else None,
                'url': props.get('url')
            })
        return out
    except Exception:
        return []


def _query_weather_alerts(lat, lon):
    """Query weather.gov active alerts for a point. Returns list of alert dicts."""
    url = f'https://api.weather.gov/alerts/active?point={lat},{lon}'
    try:
        data = _cached_get(url, ttl=300)
        if not data:
            return []
        out = []
        for feat in data.get('features', [])[:10]:
            props = feat.get('properties', {})
            event = props.get('event')
            severity = props.get('severity')
            headline = props.get('headline') or event
            onset = props.get('onset')
            expires = props.get('expires')
            out.append({
                'type': 'weather',
                'title': headline,
                'severity': severity,
                'onset': onset,
                'expires': expires,
                'areas': props.get('areaDesc')
            })
        return out
    except Exception:
        return []


def _query_reliefweb_by_country(country, limit=5):
    """Query ReliefWeb disasters for a given country name. Returns list of events."""
    try:
        if not country:
            return []
        out = []
        # Try multiple filters: country field, ISO3, then general query
        alpha2, alpha3 = _country_to_iso(country)
        attempts = []
        # filter by country field
        attempts.append(('filter[field]=country&filter[value]=' + requests.utils.quote(country), 3600))
        # try ISO3 code filter
        if alpha3:
            attempts.append(('filter[field]=country_iso3&filter[value]=' + requests.utils.quote(alpha3), 3600))
        # fallback: query text search
        attempts.append(('query=' + requests.utils.quote(country), 3600))

        for q, ttl in attempts:
            url = 'https://api.reliefweb.int/v1/disasters?appname=apidoc&' + q + f'&limit={limit}'
            data = _cached_get(url, ttl=ttl)
            if not data:
                continue
            for item in data.get('data', [])[:limit]:
                fields = item.get('fields', {})
                name = fields.get('name') or item.get('title')
                date = fields.get('date')
                out.append({
                    'source': 'reliefweb',
                    'type': 'declared_disaster',
                    'title': name,
                    'description': fields.get('description') or fields.get('summary'),
                    'time': date,
                    'lat': None,
                    'lon': None,
                    'url': item.get('href') or item.get('url') or None,
                    'raw': item
                })
            if out:
                break
        # If no disasters results, try ReliefWeb reports (broader) and pick ones mentioning the country
        if not out:
            try:
                url = 'https://api.reliefweb.int/v1/reports?appname=apidoc&query=' + requests.utils.quote(country) + f'&limit={limit}'
                data = _cached_get(url, ttl=3600)
                if data:
                    for item in data.get('data', [])[:limit]:
                        fields = item.get('fields', {})
                        title = item.get('title') or fields.get('title') or fields.get('name')
                        date = fields.get('date') or item.get('date')
                        # attempt to check if country appears in fields
                        text = ' '.join([str(v) for v in (fields.get('country') or [])]) if isinstance(fields.get('country'), list) else str(fields.get('country') or '')
                        text += ' ' + (fields.get('name') or '') + ' ' + (fields.get('summary') or '')
                        if country.lower() in text.lower() or len(out) < 3:
                            out.append({
                                'source': 'reliefweb',
                                'type': 'report',
                                'title': title,
                                'description': fields.get('summary') or fields.get('description'),
                                'time': date,
                                'lat': None,
                                'lon': None,
                                'url': item.get('href') or item.get('url') or None,
                                'raw': item
                            })
            except Exception:
                pass
        return out
    except Exception:
        return []


def _normalize_event(e):
    """Normalize different feed event shapes into a common dict."""
    # If already normalized, return a shallow copy
    out = {
        'id': None,
        # prefer explicit source field; fall back to type
        'source': e.get('source') or e.get('type') or 'unknown',
        'type': e.get('type') or e.get('source') or 'event',
        'title': e.get('title') or e.get('place') or e.get('headline') or 'Event',
        'description': e.get('description') or e.get('headline') or '',
        'time': e.get('time') or e.get('onset') or e.get('date') or None,
        'lat': e.get('lat'),
        'lon': e.get('lon'),
        'url': e.get('url') or (e.get('raw') and e.get('raw').get('url')),
        'mag': e.get('mag') or e.get('magnitude'),
        'raw': e.get('raw') if e.get('raw') else e
    }
    # id preference: url else title+time
    if out['url']:
        out['id'] = out['url']
    else:
        out['id'] = (out['title'] or '') + '|' + (out['time'] or '')
    return out


@ttl_cache(ttl_seconds=300)
def get_nearby_disasters(lat=None, lon=None, radius_km=20, days=180, country=None, max_results=50):
    """Return deduplicated, normalized list of nearby disasters.

    - Uses a small TTL cache for external requests
    - Deduplicates by URL or title+time
    - Keeps ReliefWeb items (may lack lat/lon)
    """
    results = []
    if lat is None or lon is None:
        return results

    try:
        radius_km = float(radius_km) if radius_km is not None else 20.0
    except Exception:
        radius_km = 20.0
    try:
        days = int(days) if days is not None else 180
    except Exception:
        days = 180

    # Earthquakes
    eqs = _query_usgs_earthquakes(lat, lon, maxradiuskm=radius_km, days=days, limit=50)
    # Weather alerts
    alerts = _query_weather_alerts(lat, lon)

    combined = []
    combined.extend(eqs)
    combined.extend(alerts)

    # Query ReliefWeb by country when available to capture declared disasters
    if country:
        rw = _query_reliefweb_by_country(country, limit=25)
        combined.extend(rw)

    # Normalize and deduplicate
    seen = set()
    normalized = []
    for ev in combined:
        ne = _normalize_event(ev)
        if ne['id'] in seen:
            continue
        seen.add(ne['id'])
        normalized.append(ne)

    # Sort by time (most recent first) when possible
    def _time_key(x):
        t = x.get('time')
        if not t:
            return 0
        try:
            # Try to parse ISO-ish strings
            return datetime.fromisoformat(t.replace('Z', '+00:00')).timestamp()
        except Exception:
            return 0

    normalized.sort(key=_time_key, reverse=True)

    # If some events lack lat/lon, attempt to geocode a small number of them
    # using Nominatim (OpenStreetMap). We limit the number of geocoding
    # calls to avoid rate limits and cache results via _cached_get.
    to_geocode = [e for e in normalized if not e.get('lat') or not e.get('lon')]
    geocode_budget = 8
    for e in to_geocode:
        if geocode_budget <= 0:
            break
        # Try to build a reasonable query: prefer place, then title, then description
        q_parts = []
        if e.get('place'):
            q_parts.append(e.get('place'))
        if e.get('title'):
            q_parts.append(e.get('title'))
        if e.get('description'):
            q_parts.append(e.get('description')[:200])
        if country:
            # include country to bias the result
            q_parts.append(country)
        query = ', '.join([p for p in q_parts if p])
        if not query:
            continue
        # build nominatim url (use format=json, limit=1)
        url = 'https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + requests.utils.quote(query)
        try:
            data = _cached_get(url, ttl=24*3600)
            if data and isinstance(data, list) and len(data) > 0:
                item = data[0]
                lat_s = item.get('lat')
                lon_s = item.get('lon')
                try:
                    e['lat'] = float(lat_s) if lat_s else e.get('lat')
                    e['lon'] = float(lon_s) if lon_s else e.get('lon')
                    geocode_budget -= 1
                except Exception:
                    pass
        except Exception:
            # ignore geocoding errors
            pass

    # compute distance (km) for entries that have coordinates and filter by radius_km
    def haversine_km(a_lat, a_lon, b_lat, b_lon):
        R = 6371.0
        phi1 = math.radians(a_lat)
        phi2 = math.radians(b_lat)
        dphi = math.radians(b_lat - a_lat)
        dlambda = math.radians(b_lon - a_lon)
        x = math.sin(dphi/2.0)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2.0)**2
        return 2 * R * math.asin(min(1, math.sqrt(x)))

    with_coords = []
    without_coords = []
    for ev in normalized:
        if ev.get('lat') is not None and ev.get('lon') is not None:
            try:
                dkm = haversine_km(float(lat), float(lon), float(ev['lat']), float(ev['lon']))
                ev['_distance_km'] = round(dkm, 2)
            except Exception:
                ev['_distance_km'] = None
            # only keep if within radius_km
            if ev.get('_distance_km') is not None and ev['_distance_km'] <= radius_km:
                with_coords.append(ev)
        else:
            without_coords.append(ev)

    # prefer geo-located events, then append some reliefweb/report items without coords
    results = sorted(with_coords, key=lambda x: (x.get('_distance_km') if x.get('_distance_km') is not None else 9999))
    # include up to max_results total
    remaining = max_results - len(results)
    if remaining > 0:
        results.extend(without_coords[:remaining])

    return results
    

