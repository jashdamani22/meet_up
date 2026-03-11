import httpx
from os import getenv
from datetime import datetime, timezone
import json
import heapq
from dotenv import load_dotenv


class TflRequest:
    def __init__(self):
        # Initialize cache dictionaries. These will help avoid unecessary API calls
        self._tube_status_cache = {}
        self._tube_closures_cache = {}
        self._station_coords_cache = {}
        self._journey_times_cache = {}
        with open("app/data/station_times.json", "r") as file:
            self._station_run_times = json.load(file)
        # Load environment variables from .env file
        load_dotenv()
        self._TFL_API_KEY = getenv("TFL_API_KEY")

    def _is_cached(self, cache_dict: dict, cache_name: str) -> bool:
        # Check that the cache exists. If it doesn't, the object has likely not been initialized.
        assert cache_dict is not None, f"No cache for {cache_name} has been initialized. Check that the TflRequest object has been instantiated properly."
        
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
        r = httpx.get(f"https://api.tfl.gov.uk/Line/Mode/tube/Status?app_key={self._TFL_API_KEY}")
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
        r = httpx.get(f"https://api.tfl.gov.uk/StopPoint/Mode/tube/Disruption?app_key={self._TFL_API_KEY}")
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
        r = httpx.get(f"https://api.tfl.gov.uk/StopPoint/{station_id}?app_key={self._TFL_API_KEY}")
        r.raise_for_status()

        station_info = r.json()
        if "exceptionType" in station_info:
            raise KeyError(f"Error when retrieving station info for {station_id}. Response code: {station_info["exceptionType"]}. Status: {station_info["httpStatusCode"]} {station_info["httpStatus"]}. URI: {station_info["relativeUri"]}. {station_info["message"]}")
        
        coordinates = (station_info["lat"], station_info["lon"])
        self._station_coords_cache[station_id]= coordinates
        return coordinates
    
    def get_run_time(self, station_from: str, station_to: str):
        # Find the run time in the station times data
        for entry in self._station_run_times:
            if entry["station_from_naptan"] == station_from and entry["station_to_naptan"] == station_to:
                return entry["run_time"]
        
        raise KeyError(f"No run time found for stations {station_from} to {station_to}")
    
    def _build_graph(self):
        if hasattr(self, '_graph'):
            return self._graph
        graph = {}  # station -> list of (to_station, run_time, line)
        for entry in self._station_run_times:
            from_s = entry['station_from_naptan']
            to_s = entry['station_to_naptan']
            rt = entry['run_time']
            line = entry['line']
            if from_s not in graph:
                graph[from_s] = []
            graph[from_s].append((to_s, rt, line))
        self._graph = graph
        return graph
    
    def get_all_stations(self):
        graph = self._build_graph()
        return list(graph.keys())
    
    def get_journey_time_with_penalty(self, from_station, to_station):
        graph = self._build_graph()
        # Dijkstra with line change penalty baked into the cost
        # State: (station, current_line) where current_line is the line we arrived on
        dist = {(from_station, None): 0}
        prev = {(from_station, None): None}
        prev_line = {(from_station, None): None}
        pq = [(0, from_station, None)]  # (cost, station, line_we_came_on)
        
        while pq:
            d, u, current_line = heapq.heappop(pq)
            state = (u, current_line)
            
            if u == to_station:
                # Reconstruct path
                path = []
                edges = []
                s = state
                while s is not None:
                    path.append(s[0])
                    if prev_line[s] is not None:
                        edges.append(prev_line[s])
                    s = prev[s]
                path.reverse()
                edges.reverse()
                return d, path
            
            if d > dist.get(state, float('inf')):
                continue
            
            for v, rt, line in graph.get(u, []):
                # Cost is travel time + penalty if we're changing lines
                cost_add = rt
                if current_line is not None and line != current_line:
                    cost_add += 5  # penalty for line change
                
                alt = d + cost_add
                next_state = (v, line)
                
                if alt < dist.get(next_state, float('inf')):
                    dist[next_state] = alt
                    prev[next_state] = state
                    prev_line[next_state] = line
                    heapq.heappush(pq, (alt, v, line))
        
        raise KeyError(f"No path from {from_station} to {to_station}")


if __name__ == "__main__":
    x = TflRequest()
    print(x.get_line_status())
    print(x.get_line_status())

    print(x.get_tube_closures())
    print(x.get_tube_closures())

    print(x.get_station_coords("940GZZLUUXB"))
    print(x.get_station_coords("940GZZLUUXB"))

    print(x.get_run_time("940GZZLUHAW", "940GZZLUKEN"))
    print(x.get_run_time("940GZZLUHAW", "940GZZLUKEN"))