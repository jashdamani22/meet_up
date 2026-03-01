import httpx
from os import getenv
from time import time

class TfL_Request:
    def __init__(self):
        # Initialize cache dictionaries. These will help avoid unecessary API calls
        self.tube_status_cache = {}
        self.tube_closures_cache = {}
        self.station_coords_cache = {}
        self.journey_times_cache = {}

    def get_line_status(self):

        # Check cache for result of request, only request fresh data if cache is empty or older than 60 seconds
        if "timestamp" in self.tube_status_cache:
            if self.tube_status_cache["timestamp"] - time() < 60.0:
                print("Line status cache hit!")
                return self.tube_status_cache
        print("Line status cache miss!")


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
        line_status["timestamp"] = time()

        # Cache result for future calls
        self.tube_status_cache = line_status.copy()
        return line_status

if __name__ == "__main__":
    x = TfL_Request()
    print(x.get_line_status())
    print(x.get_line_status())