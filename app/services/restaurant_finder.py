import httpx
from os import getenv
from typing import Optional, List, Dict
from dotenv import load_dotenv


class RestaurantFinder:
    """
    Find places of interest (restaurants, pubs, parks, etc.) near tube stations.
    
    Uses Google Maps API with intelligent caching to minimize API requests.
    Results are cached for the entire runtime since restaurant listings don't change significantly during a day.
    """
    
    def __init__(self, tfl_request_client):
        """
        Initialize the RestaurantFinder with a TfL request client.
        
        Args:
            tfl_request_client: An instance of TflRequest to get station coordinates
        """
        # Load environment variables from .env file
        load_dotenv()
        
        self.tfl_client = tfl_request_client
        self.google_maps_api_key = getenv("GOOGLE_MAPS_API_KEY")
        
        if not self.google_maps_api_key:
            raise ValueError("GOOGLE_MAPS_API_KEY environment variable not set")
        
        # Cache for POI count results: (station_id, poi_type, max_distance, min_rating) -> count
        self._poi_count_cache = {}
        
        # Cache for nearby places API results: (lat, lon, poi_type, radius) -> [places]
        self._places_cache = {}
    
    def _get_poi_count_cache_key(self, station_id: str, poi_type: str, max_distance: float, min_rating: float) -> str:
        """Generate a cache key for a POI count."""
        return f"{station_id}|{poi_type}|{max_distance}|{min_rating}"
    
    def _get_places_cache_key(self, lat: float, lon: float, poi_type: str, radius: float) -> str:
        """Generate a cache key for nearby places."""
        # Round coordinates to 4 decimal places (approx 11 meters) to allow some flexibility
        lat_rounded = round(lat, 4)
        lon_rounded = round(lon, 4)
        return f"{lat_rounded}|{lon_rounded}|{poi_type}|{radius}"
    
    def find_poi(
        self,
        poi_type: str,
        station_id: str,
        max_distance: float = 500.0,
        min_rating: float = 3.0
    ) -> int:
        """
        Find the number of places of interest around a tube station that meet specified criteria.
        
        Args:
            poi_type: Type of POI (e.g., 'restaurant', 'pub', 'park', 'cafe', 'bar')
            station_id: The tube station ID (naptan code)
            max_distance: Maximum walking distance in meters (default 500m)
            min_rating: Minimum rating filter (default 3.0 stars)
        
        Returns:
            The number of places of interest matching all criteria
            
        Raises:
            KeyError: If station coordinates cannot be retrieved
            ValueError: If poi_type is not supported or Google Maps returns an error
        """
        # Check cache first
        cache_key = self._get_poi_count_cache_key(station_id, poi_type, max_distance, min_rating)
        if cache_key in self._poi_count_cache:
            print(f"Cache hit for POI count: {poi_type} near {station_id}")
            return self._poi_count_cache[cache_key]
        
        print(f"Cache miss for POI count: {poi_type} near {station_id}")
        
        # Get station coordinates from TfL client
        try:
            lat, lon = self.tfl_client.get_station_coords(station_id)
        except KeyError as e:
            raise KeyError(f"Could not retrieve coordinates for station {station_id}: {e}")
        
        # Search for places around the station
        places = self._search_nearby_places(lat, lon, poi_type, max_distance)
        
        # Filter by minimum rating and count
        filtered_count = sum(1 for place in places if place.get("rating", 0) >= min_rating)
        
        # Cache the result
        self._poi_count_cache[cache_key] = filtered_count
        
        return filtered_count
    
    def _search_nearby_places(self, lat: float, lon: float, poi_type: str, radius: float = 500.0) -> List[Dict]:
        """
        Search for places near a location using Google Maps Nearby Search API.
        
        Retrieves up to 20 results (single page). Results are cached by location, type, and radius.
        
        Args:
            lat: Latitude of the center point
            lon: Longitude of the center point
            poi_type: Type of place to search for
            radius: Search radius in meters
        
        Returns:
            A list of place data dictionaries containing place information (max 20)
            
        Raises:
            ValueError: If poi_type is not supported or API returns an error
            RuntimeError: If HTTP request fails
        """
        # Check if we have cached results for this location and type
        places_cache_key = self._get_places_cache_key(lat, lon, poi_type, radius)
        if places_cache_key in self._places_cache:
            print(f"Cache hit for nearby places: {poi_type} at ({lat}, {lon})")
            return self._places_cache[places_cache_key]
        
        print(f"Cache miss for nearby places: {poi_type} at ({lat}, {lon})")
        
        # Map poi_type to Google Maps type
        google_type = self._map_poi_type_to_google_type(poi_type)
        
        # Make API request to Google Maps Nearby Search
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "location": f"{lat},{lon}",
            "radius": int(radius),
            "type": google_type,
            "key": self.google_maps_api_key
        }
        
        try:
            response = httpx.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Check for API errors
            status = data.get("status")
            if status != "OK":
                error_msg = data.get("error_message", "Unknown error")
                raise ValueError(f"Google Maps API error: {status} - {error_msg}")
            
            places = data.get("results", [])
            
            # Cache the results
            self._places_cache[places_cache_key] = places
            
            print(f"Retrieved {len(places)} places from Google Maps API")
            
            return places
        
        except httpx.HTTPError as e:
            raise RuntimeError(f"HTTP error when querying Google Maps API: {e}")
    
    def _map_poi_type_to_google_type(self, poi_type: str) -> str:
        """
        Map POI type names to Google Maps API type values.
        
        Args:
            poi_type: The POI type (e.g., 'restaurant', 'pub', 'park')
        
        Returns:
            The corresponding Google Maps type string
            
        Raises:
            ValueError: If poi_type is not supported
        """
        type_mapping = {
            "restaurant": "restaurant",
            "pub": "bar",
            "bar": "bar",
            "park": "park",
            "cafe": "cafe",
            "coffee": "cafe",
            "museum": "museum",
            "library": "library",
            "gym": "gym",
            "shopping_mall": "shopping_mall",
        }
        
        poi_type_lower = poi_type.lower()
        mapped_type = type_mapping.get(poi_type_lower)
        
        if not mapped_type:
            supported = ", ".join(sorted(set(type_mapping.values())))
            raise ValueError(
                f"Unsupported POI type: '{poi_type}'. "
                f"Supported types: {supported}"
            )
        
        return mapped_type
    
    def clear_cache(self):
        """Clear all cached data. Useful for testing or refreshing data."""
        self._poi_count_cache.clear()
        self._places_cache.clear()
        print("Cache cleared")


if __name__ == "__main__":
    # Import TflRequest for testing
    from tfl_requests import TflRequest
    
    # Initialize clients
    tfl_client = TflRequest()
    finder = RestaurantFinder(tfl_client)
    
    # Test 1: Find restaurants near King's Cross St Pancras
    print("Test 1: Finding restaurants near King's Cross St Pancras")
    try:
        station_id = "940GZZLUKSX"  # King's Cross St Pancras
        count = finder.find_poi("restaurant", station_id)
        print(f"Found {count} restaurants with rating >= 3.0 within 500m")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 2: Same search again to test caching
    print("\nTest 2: Same search (should use cache)")
    try:
        count = finder.find_poi("restaurant", station_id)
        print(f"Found {count} restaurants with rating >= 3.0 within 500m")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 3: Find pubs with different parameters
    print("\nTest 3: Finding pubs with higher rating threshold")
    try:
        count = finder.find_poi("pub", station_id, max_distance=1000, min_rating=4.0)
        print(f"Found {count} pubs with rating >= 4.0 within 1000m")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 4: Test caching again
    print("\nTest 4: Same pub search (should use cache)")
    try:
        count = finder.find_poi("pub", station_id, max_distance=1000, min_rating=4.0)
        print(f"Found {count} pubs with rating >= 4.0 within 1000m")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 5: Find parks with default parameters
    print("\nTest 5: Finding parks with default parameters")
    try:
        count = finder.find_poi("park", station_id)
        print(f"Found {count} parks with rating >= 3.0 within 500m")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 6: Same park search (cache)
    print("\nTest 6: Same park search (should use cache)")
    try:
        count = finder.find_poi("park", station_id)
        print(f"Found {count} parks with rating >= 3.0 within 500m")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 7: Invalid POI type
    print("\nTest 7: Invalid POI type (should raise error)")
    try:
        count = finder.find_poi("invalid_type", station_id)
    except ValueError as e:
        print(f"Expected error: {e}")
