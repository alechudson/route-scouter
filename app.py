"""Route Scout - Search for places along your route."""

import os
import streamlit as st
from streamlit_folium import st_folium
import pandas as pd
from dotenv import load_dotenv

from utils import parse_route, encode_polyline, search_along_route, generate_map

# Load environment variables
load_dotenv()

# Page config
st.set_page_config(
    page_title="Route Scouter",
    page_icon="🗺️",
    layout="wide"
)

st.title("Route Scouter")
st.caption("Search for places along your routes")

# Sidebar inputs
with st.sidebar:
    st.header("Settings")

    uploaded_file = st.file_uploader(
        "Upload Route File",
        type=['kml', 'gpx'],
        help="Upload a KML or GPX file containing your route"
    )

    query = st.text_input(
        "Search for...",
        placeholder="bars, coffee shops, restaurants...",
        help="What kind of places are you looking for?"
    )

    # API key from environment
    api_key = os.getenv("GOOGLE_API_KEY", "")

    max_results = st.slider(
        "Max Results",
        min_value=5,
        max_value=50,
        value=20,
        help="Maximum number of places to return"
    )

    search_btn = st.button("Search", type="primary", use_container_width=True)

    st.divider()
    st.subheader("Filters")

    min_rating = st.slider(
        "Min Rating",
        min_value=0.0,
        max_value=5.0,
        value=0.0,
        step=0.5,
        help="Only show places with this rating or higher"
    )

    price_filter = st.multiselect(
        "Price Level",
        options=["$", "$$", "$$$", "$$$$"],
        default=[],
        help="Filter by price (leave empty for all)"
    )

    open_now_only = st.checkbox(
        "Open Now",
        value=False,
        help="Only show places that are currently open"
    )

    max_distance_mi = st.slider(
        "Max Distance from Route",
        min_value=0.0,
        max_value=5.0,
        value=5.0,
        step=0.1,
        format="%.1f mi",
        help="Maximum distance from route in miles"
    )

    st.divider()

    if api_key:
        st.success("API key loaded")
    else:
        st.warning("Set GOOGLE_API_KEY in .env")

    st.markdown("""
    **How to use:**
    1. Upload a KML or GPX route file
    2. Enter what you're searching for
    3. Click Search!
    """)

# Initialize session state
if "results" not in st.session_state:
    st.session_state.results = None
if "route_points" not in st.session_state:
    st.session_state.route_points = None
if "filtered_results" not in st.session_state:
    st.session_state.filtered_results = None

# Parse route when file is uploaded
if uploaded_file:
    try:
        file_type = uploaded_file.name.split('.')[-1].lower()
        points = parse_route(uploaded_file.getvalue(), file_type)
        st.session_state.route_points = points

        if len(points) < 2:
            st.error("Route must have at least 2 points")
            st.session_state.route_points = None
        else:
            st.sidebar.success(f"Route loaded: {len(points)} points")
    except Exception as e:
        st.error(f"Error parsing route file: {str(e)}")
        st.session_state.route_points = None

# Handle search
if search_btn:
    if not st.session_state.route_points:
        st.warning("Please upload a route file first")
    elif not query:
        st.warning("Please enter a search query")
    elif not api_key:
        st.warning("Missing API key. Add GOOGLE_API_KEY=your_key to .env file")
    else:
        try:
            with st.spinner("Encoding route..."):
                encoded = encode_polyline(st.session_state.route_points)

            with st.spinner(f"Searching for '{query}' along your route..."):
                results = search_along_route(encoded, query, api_key, max_results, st.session_state.route_points)
                st.session_state.results = results
                st.session_state.results_unfiltered_count = len(results)

            if not results:
                st.info("No results found. Try a different search query.")
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "403" in error_msg:
                st.error("API key error. Please check your Google API key is valid and has Places API enabled.")
            elif "400" in error_msg:
                st.error("Invalid request. The route may be too complex or the query invalid.")
            else:
                st.error(f"Search error: {error_msg}")

# Display results
if st.session_state.results:
    results = st.session_state.results

    # Apply filters
    filtered_results = []
    for place in results:
        # Rating filter
        if place.get("rating") and place["rating"] < min_rating:
            continue
        if min_rating > 0 and not place.get("rating"):
            continue

        # Price filter
        if price_filter and place.get("price_level") not in price_filter:
            if place.get("price_level"):  # Skip if has price but not in filter
                continue

        # Open now filter
        if open_now_only and place.get("open_now") is not True:
            continue

        # Distance filter (convert to miles)
        if place.get("distance_mi") and place["distance_mi"] > max_distance_mi:
            continue

        filtered_results.append(place)

    total_count = st.session_state.get("results_unfiltered_count", len(results))
    if len(filtered_results) < total_count:
        st.subheader(f"Showing {len(filtered_results)} of {total_count} places")
    else:
        st.subheader(f"Found {len(filtered_results)} places")

    if not filtered_results:
        st.info("No places match your filters. Try adjusting them.")
    else:
        # Results table
        df = pd.DataFrame(filtered_results)

        # Format the dataframe for display
        display_cols = ["name", "rating", "rating_count", "distance_display", "price_level", "open_now", "address", "maps_url"]
        available_cols = [c for c in display_cols if c in df.columns]

        st.dataframe(
            df[available_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "name": "Name",
                "rating": st.column_config.NumberColumn("Rating", format="%.1f"),
                "rating_count": st.column_config.NumberColumn("Reviews", format="%d"),
                "distance_display": "Distance",
                "price_level": "Price",
                "open_now": st.column_config.CheckboxColumn("Open", default=False),
                "address": "Address",
                "maps_url": st.column_config.LinkColumn("Map", display_text="Open")
            }
        )

        # Update session state with filtered results for map
        st.session_state.filtered_results = filtered_results

# Display map
if st.session_state.route_points:
    st.subheader("Map")
    # Use filtered results if available, otherwise all results
    map_results = st.session_state.get("filtered_results", st.session_state.results)
    m = generate_map(st.session_state.route_points, map_results)
    st_folium(m, width=None, height=600, use_container_width=True)
elif not uploaded_file:
    # Show placeholder map centered on Austin
    st.subheader("Map")
    st.info("Upload a route file to see it on the map")
    import folium
    m = folium.Map(location=[30.2672, -97.7431], zoom_start=11)
    st_folium(m, width=None, height=400, use_container_width=True)
