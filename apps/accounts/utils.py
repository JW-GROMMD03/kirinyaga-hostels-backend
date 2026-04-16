import googlemaps
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Initialize Google Maps client
gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)

# apps/accounts/utils.py

def geocode_address(address):
    """Geocode an address to latitude/longitude"""
    try:
        import googlemaps
        from django.conf import settings
        
        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
        if not api_key:
            print("⚠️ GOOGLE_MAPS_API_KEY not configured")
            return None, None
        
        gmaps = googlemaps.Client(key=api_key)
        result = gmaps.geocode(address)
        
        if result and len(result) > 0:
            location = result[0]['geometry']['location']
            return location['lat'], location['lng']
        
        return None, None
    except ImportError:
        print("⚠️ googlemaps module not installed - geocoding disabled")
        return None, None
    except Exception as e:
        print(f"⚠️ Geocoding error: {e}")
        return None, None

def calculate_distance(origin_lat, origin_lng, dest_lat, dest_lng):
    """Calculate distance between two points in km"""
    if not settings.GOOGLE_MAPS_API_KEY or settings.GOOGLE_MAPS_API_KEY == 'your-google-maps-api-key':
        logger.warning("Google Maps API key not configured")
        return None
    
    try:
        result = gmaps.distance_matrix(
            (origin_lat, origin_lng),
            (dest_lat, dest_lng),
            mode='driving'
        )
        if result['rows'][0]['elements'][0]['status'] == 'OK':
            distance = result['rows'][0]['elements'][0]['distance']['value'] / 1000  # Convert to km
            return round(distance, 2)
    except Exception as e:
        logger.error(f"Distance calculation error: {e}")
    return None