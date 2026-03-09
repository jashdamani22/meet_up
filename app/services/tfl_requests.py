import httpx
from os import getenv
from datetime import datetime, timezone

class TfL_Request:
    def __init__(self):
        # Initialize cache dictionaries. These will help avoid unecessary API calls
        self._tube_status_cache = {}
        self._tube_closures_cache = {}
        self._station_coords_cache = {}
        self._journey_times_cache = {}

    def _is_cached(self, cache_dict: dict, cache_name: str) -> bool:
        # Check that the cache exists. If it doesn't, the object has likely not been initialized.
        assert cache_dict is not None, f"No cache for {cache_name} has been initialized. Check that the TfL_Request object has been instantiated properly."
        
        # If a cached copy of the desired dict exists and is less than 60 seconds old, 
        if "timestamp" in cache_dict:
            if cache_dict["timestamp"].timestamp() - datetime.now(timezone.utc).timestamp() < 60.0:
                print(f"Cache hit for {cache_name}!")
                return True
            
        print(f"Cache miss for {cache_name}!")
        return False

    def get_line_status(self):

        # Check cache for result of request, only request fresh data if cache is empty or older than 60 seconds
        if self._is_cached(self._tube_status_cache, "tube status"):
            return self._tube_status_cache

        # Make GET request to TfL API for all status information for tube lines
        r = httpx.get(f"https://api.tfl.gov.uk/Line/Mode/tube/Status?app_key={getenv("TFL_API_KEY")}")
        r.raise_for_status()

        # Present the data more neatly
        line_status = {}
        for line in r.json():
            line_status[line["id"]] = {
                "name": line["name"],
                "status_codes":[
                    line_status_code["statusSeverityDescription"] for line_status_code in line["lineStatuses"]
                ]
            }
        line_status["timestamp"] = datetime.now(timezone.utc)

        # Cache result for future calls
        self._tube_status_cache = line_status.copy()
        return line_status
    
    def get_tube_closures(self):

        # Check cache for result of request, only request fresh data if cache is empty or older than 60 seconds
        if self._is_cached(self._tube_closures_cache, "tube closures"):
            return self._tube_closures_cache
        
         # Make GET request to TfL API for all tube closures
        r = httpx.get(f"https://api.tfl.gov.uk/StopPoint/Mode/tube/Disruption?app_key={getenv("TFL_API_KEY")}")
        r.raise_for_status()

        tube_closures = {}
        current_time = datetime.now(timezone.utc)
        for closure in r.json():
            if closure["type"] != "Closure":
                # Skip anything that isn't a station closure
                continue

            # Check that the closure is currently in effect, and not planned in the future
            start_time = datetime.fromisoformat(closure["fromDate"])
            end_time = datetime.fromisoformat(closure["toDate"])
            if start_time.timestamp() > current_time.timestamp() or end_time.timestamp() < current_time.timestamp():
                continue

           # Present the data more neatly
            tube_closures[closure["atcoCode"]] = {
                "station_id": closure["atcoCode"],
                "station_name": closure["commonName"],
                "description": closure["description"],
                "start_date": start_time,
                "end_date": end_time
            }
        
        tube_closures["timestamp"] = current_time

        # Cache results for future calls
        self._tube_closures_cache = tube_closures.copy()
        return tube_closures
    
    def get_station_coords(self, station_id: str):

        # Simplified caching mechanism without time here because this information
        # does not have an expiration date that is meaningful to this proejct
        if station_id in self._station_coords_cache:
            print(f"Cache hit for station {station_id}!")
            return self._station_coords_cache[station_id]
        print(f"Cache miss for station {station_id}!")
        
        # Make GET request to TfL API for tube station details
        r = httpx.get(f"https://api.tfl.gov.uk/StopPoint/{station_id}?app_key={getenv("TFL_API_KEY")}")
        r.raise_for_status()

        station_info = r.json()
        if "exceptionType" in station_info:
            raise KeyError(f"Error when retrieving station info for {station_id}. Response code: {station_info["exceptionType"]}. Status: {station_info["httpStatusCode"]} {station_info["httpStatus"]}. URI: {station_info["relativeUri"]}. {station_info["message"]}")
        
        coordinates = (station_info["lat"], station_info["lon"])
        self._station_coords_cache[station_id]= coordinates
        return coordinates


if __name__ == "__main__":
    x = TfL_Request()
    print(x.get_line_status())
    print(x.get_line_status())

    print(x.get_tube_closures())
    print(x.get_tube_closures())

    print(x.get_station_coords("940GZZLUUXB"))
    print(x.get_station_coords("940GZZLUUXB"))