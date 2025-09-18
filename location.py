import requests


def _get_client_ip(flask_request):
    # Respect X-Forwarded-For if present (behind proxies/load balancers)
    xff = flask_request.headers.get('X-Forwarded-For', '')
    if xff:
        # X-Forwarded-For may contain multiple IPs, the left-most is the client
        return xff.split(',')[0].strip()
    # Fallback to remote_addr
    return flask_request.remote_addr


def detect_location(flask_request):
    """Return a dict with latitude, longitude and a human-readable name.

    Uses an external IP geolocation service (ip-api.com) as a fallback when
    browser geolocation isn't available. Returns None if detection fails.
    """
    ip = _get_client_ip(flask_request)

    # Use ip-api.com (HTTP) which returns JSON like {lat, lon, city, country, ...}
    # If IP is local/loopback, call without IP to let the service detect caller IP
    if ip in ('127.0.0.1', '::1', None):
        url = 'http://ip-api.com/json'
    else:
        url = f'http://ip-api.com/json/{ip}'

    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get('status') != 'success':
            return None
        lat = data.get('lat')
        lon = data.get('lon')
        city = data.get('city')
        region = data.get('regionName')
        country = data.get('country')
        display = ', '.join([p for p in (city, region, country) if p])
        return {'lat': lat, 'lon': lon, 'display_name': display or data.get('query')}
    except Exception:
        return None
