import requests
from geopy.geocoders import Nominatim


def get_restaurants_near_station(station_name, radius_km):
    geolocator = Nominatim(user_agent="meetup_app")

    location = geolocator.geocode(station_name + " London")

    if location is None:
        return []

    lat = location.latitude
    lon = location.longitude

    radius_m = radius_km * 1000

    overpass_url = "https://overpass-api.de/api/interpreter"

    query = f"""
    [out:json];
    (
      node["amenity"="restaurant"](around:{radius_m},{lat},{lon});
      way["amenity"="restaurant"](around:{radius_m},{lat},{lon});
      relation["amenity"="restaurant"](around:{radius_m},{lat},{lon});
    );
    out center;
    """

    response = requests.get(overpass_url, params={'data': query})
    data = response.json()

    restaurants = []

    for element in data["elements"]:

        name = element.get("tags", {}).get("name", "Unnamed Restaurant")

        if "lat" in element:
            lat = element["lat"]
            lon = element["lon"]
        else:
            lat = element["center"]["lat"]
            lon = element["center"]["lon"]

        restaurants.append({
            "name": name,
            "lat": lat,
            "lon": lon
        })

    return restaurants


if __name__ == "__main__":

    station = "Oxford Circus Station"
    radius = 1

    results = get_restaurants_near_station(station, radius)

    for r in results[:10]:
        print(r)