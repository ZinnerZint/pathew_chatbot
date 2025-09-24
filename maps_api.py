import requests
from config import MAPS_API_KEY

def get_directions(origin_lat, origin_lng, dest_lat, dest_lng):
    url = f"https://maps.googleapis.com/maps/api/directions/json?origin={origin_lat},{origin_lng}&destination={dest_lat},{dest_lng}&key={MAPS_API_KEY}"
    response = requests.get(url)
    return response.json()