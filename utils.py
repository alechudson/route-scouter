"""Utility functions for Route Scout - parsing, encoding, API calls, and map generation."""

import io
import math
from typing import Optional
import gpxpy
from pykml import parser as kml_parser
import polyline
import requests
import folium


def parse_gpx(file_content: bytes) -> list[tuple[float, float]]:
    """Parse GPX file and return list of (lat, lon) tuples."""
    gpx = gpxpy.parse(io.BytesIO(file_content))
    points = []

    # Extract points from tracks
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append((point.latitude, point.longitude))

    # Also check routes if no tracks found
    if not points:
        for route in gpx.routes:
            for point in route.points:
                points.append((point.latitude, point.longitude))

    # Also check waypoints
    if not points:
        for waypoint in gpx.waypoints:
            points.append((waypoint.latitude, waypoint.longitude))

    return points


def parse_kml(file_content: bytes) -> list[tuple[float, float]]:
    """Parse KML file and return list of (lat, lon) tuples.

    Note: KML stores coordinates as lon,lat,alt - we need to swap to lat,lon.
    """
    root = kml_parser.parse(io.BytesIO(file_content)).getroot()
    points = []

    # Helper to extract coordinates from a coordinates string
    def extract_coords(coord_text: str) -> list[tuple[float, float]]:
        coords = []
        for coord in coord_text.strip().split():
            parts = coord.split(',')
            if len(parts) >= 2:
                lon, lat = float(parts[0]), float(parts[1])
                coords.append((lat, lon))  # Swap to lat, lon
        return coords

    # Search for coordinates in various KML structures
    # Using namespace-agnostic iteration
    def find_coordinates(element):
        found = []
        # Check if this element has coordinates
        if hasattr(element, 'coordinates'):
            found.extend(extract_coords(str(element.coordinates)))
        # Recursively search children
        for child in element.iterchildren():
            found.extend(find_coordinates(child))
        return found

    points = find_coordinates(root)
    return points


def parse_route(file_content: bytes, file_type: str) -> list[tuple[float, float]]:
    """Dispatch to appropriate parser based on file type."""
    file_type = file_type.lower()
    if file_type == 'gpx':
        return parse_gpx(file_content)
    elif file_type == 'kml':
        return parse_kml(file_content)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters using Haversine formula."""
    R = 6371000  # Earth's radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def distance_from_route(place_lat: float, place_lon: float, route_points: list[tuple[float, float]]) -> float:
    """Calculate minimum distance from a place to the route in meters."""
    min_dist = float('inf')

    # Sample every 10th point for performance on long routes
    step = max(1, len(route_points) // 100)
    sampled_points = route_points[::step]

    for lat, lon in sampled_points:
        dist = haversine_distance(place_lat, place_lon, lat, lon)
        if dist < min_dist:
            min_dist = dist

    return min_dist


def downsample_points(points: list[tuple[float, float]], max_points: int = 500) -> list[tuple[float, float]]:
    """Downsample points to avoid API limits while preserving start/end."""
    if len(points) <= max_points:
        return points

    step = (len(points) - 1) / (max_points - 1)
    indices = [int(i * step) for i in range(max_points - 1)] + [len(points) - 1]
    return [points[i] for i in indices]


def encode_polyline(points: list[tuple[float, float]]) -> str:
    """Encode coordinates to Google polyline format.

    Downsamples if necessary to avoid API limits.
    """
    # Downsample if too many points
    points = downsample_points(points, max_points=500)

    # polyline library expects (lat, lon) tuples which we already have
    return polyline.encode(points)


def search_along_route(
    encoded_polyline: str,
    query: str,
    api_key: str,
    max_results: int = 20,
    route_points: Optional[list[tuple[float, float]]] = None
) -> list[dict]:
    """Search for places along route using Google Places API (New).

    Returns list of dicts with: name, address, rating, lat, lon, types, price_level, open_now, distance_from_route
    """
    url = "https://places.googleapis.com/v1/places:searchText"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.rating,places.location,places.types,places.userRatingCount,places.priceLevel,places.currentOpeningHours"
    }

    body = {
        "textQuery": query,
        "maxResultCount": max_results,
        "searchAlongRouteParameters": {
            "polyline": {
                "encodedPolyline": encoded_polyline
            }
        }
    }

    response = requests.post(url, json=body, headers=headers)
    response.raise_for_status()

    data = response.json()
    places = data.get("places", [])

    results = []
    for place in places:
        location = place.get("location", {})
        lat = location.get("latitude")
        lon = location.get("longitude")

        # Calculate distance from route
        dist_from_route = None
        if route_points and lat and lon:
            dist_from_route = distance_from_route(lat, lon, route_points)

        # Parse price level to number of $ signs
        price_raw = place.get("priceLevel", "")
        price_map = {
            "PRICE_LEVEL_FREE": "Free",
            "PRICE_LEVEL_INEXPENSIVE": "$",
            "PRICE_LEVEL_MODERATE": "$$",
            "PRICE_LEVEL_EXPENSIVE": "$$$",
            "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$"
        }
        price_display = price_map.get(price_raw, "")

        # Get open now status
        opening_hours = place.get("currentOpeningHours", {})
        open_now = opening_hours.get("openNow")

        # Google Maps URL - use Place ID for direct business listing
        place_id = place.get("id", "")
        if place_id:
            maps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        elif lat and lon:
            maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        else:
            maps_url = ""

        results.append({
            "name": place.get("displayName", {}).get("text", "Unknown"),
            "address": place.get("formattedAddress", ""),
            "rating": place.get("rating"),
            "rating_count": place.get("userRatingCount"),
            "lat": lat,
            "lon": lon,
            "types": ", ".join(place.get("types", [])[:3]),
            "price_level": price_display,
            "price_raw": price_raw,
            "open_now": open_now,
            "distance_m": dist_from_route,
            "distance_mi": dist_from_route / 1609.34 if dist_from_route else None,
            "distance_display": f"{dist_from_route / 1609.34:.1f} mi" if dist_from_route else "",
            "maps_url": maps_url
        })

    return results


def generate_map(
    route_points: list[tuple[float, float]],
    places: Optional[list[dict]] = None
) -> folium.Map:
    """Create folium map with route polyline and place markers."""
    if not route_points:
        # Default to Austin if no points
        center = [30.2672, -97.7431]
        zoom = 10
    else:
        # Center on route midpoint
        mid_idx = len(route_points) // 2
        center = list(route_points[mid_idx])
        zoom = 12

    m = folium.Map(location=center, zoom_start=zoom)

    # Add route polyline
    if route_points:
        folium.PolyLine(
            locations=route_points,
            color="blue",
            weight=4,
            opacity=0.8,
            tooltip="Your route"
        ).add_to(m)

        # Add start/end markers
        folium.Marker(
            location=route_points[0],
            icon=folium.Icon(color="green", icon="play"),
            tooltip="Start"
        ).add_to(m)

        folium.Marker(
            location=route_points[-1],
            icon=folium.Icon(color="red", icon="stop"),
            tooltip="End"
        ).add_to(m)

    # Add place markers
    if places:
        for place in places:
            if place.get("lat") and place.get("lon"):
                # Build popup content
                rating_str = f"{place['rating']:.1f}" if place.get('rating') else "N/A"
                price_str = f" · {place['price_level']}" if place.get('price_level') else ""
                distance_str = f"<br>{place['distance_display']} from route" if place.get('distance_display') else ""
                open_str = " · Open" if place.get('open_now') else ""

                # Google Maps link - use stored URL which has place ID
                maps_url = place.get("maps_url", f"https://www.google.com/maps/search/?api=1&query={place['lat']},{place['lon']}")

                popup_html = f"""
                <b>{place['name']}</b><br>
                Rating: {rating_str}{price_str}{open_str}{distance_str}<br>
                <small>{place.get('address', '')}</small><br>
                <a href="{maps_url}" target="_blank" style="color: #1a73e8;">Open in Google Maps</a>
                """

                folium.Marker(
                    location=[place["lat"], place["lon"]],
                    icon=folium.Icon(color="orange", icon="info-sign"),
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=f"{place['name']} ({rating_str})"
                ).add_to(m)

    # Fit map bounds to show all markers
    if route_points:
        all_points = list(route_points)
        if places:
            all_points.extend([(p["lat"], p["lon"]) for p in places if p.get("lat")])
        m.fit_bounds(all_points)

    return m
