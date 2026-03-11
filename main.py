import streamlit as st
import sys
import os
import json
from typing import Dict, List, Tuple

# Add workspace to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.services.tfl_requests import TflRequest
from app.logic.optimize_route import OptimizeRoute

# Configure Streamlit page
st.set_page_config(
    page_title="Meetup Optimizer",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for light mode
st.markdown("""
<style>
    :root {
        --primary-color: #0066cc;
        --background-color: #ffffff;
        --text-color: #333333;
    }
    body {
        background-color: var(--background-color);
        color: var(--text-color);
    }
    .result-container {
        background-color: #f0f8ff;
        padding: 20px;
        border-radius: 8px;
        border-left: 4px solid #0066cc;
        margin: 10px 0;
    }
    .journey-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        margin: 10px 0;
    }
    .line-badge {
        display: inline-block;
        background-color: #0066cc;
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        margin: 0 4px;
        font-size: 12px;
        font-weight: bold;
    }
    .status-warning {
        background-color: #fff3cd;
        padding: 10px;
        border-radius: 4px;
        border-left: 4px solid #ffc107;
        margin: 10px 0;
    }
    .line-segment {
        margin-left: 20px;
        padding: 8px;
        border-left: 3px solid #0066cc;
        margin: 5px 0;
    }
    .journey-person {
        font-weight: bold;
        margin-top: 10px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Title and description
st.title("🚇 London Tube Meeting Point Optimizer")
st.markdown("Find the optimal tube station for your group to meet!")

# Initialize session state
@st.cache_resource
def load_clients():
    """Load TfL and optimization clients."""
    tfl = TflRequest()
    optimizer = OptimizeRoute()
    return tfl, optimizer

@st.cache_data
def get_line_id_mapping() -> Dict[str, str]:
    """Map line names from JSON to TfL API line IDs."""
    return {
        "Bakerloo": "bakerloo",
        "Central": "central",
        "Circle": "circle",
        "District": "district",
        "Hammersmith & City": "hammersmith-city",
        "Jubilee": "jubilee",
        "Metropolitan": "metropolitan",
        "Northern": "northern",
        "Piccadilly": "piccadilly",
        "Victoria": "victoria",
        "Waterloo & City": "waterloo-city",
        "DLR": "dlr",
        "Tram": "tram"
    }

@st.cache_data
def get_station_names() -> Dict[str, str]:
    """Load station names from station_times.json - Maps station_id -> station_name."""
    with open("app/data/station_times.json", "r") as f:
        station_times = json.load(f)
    
    # Extract unique station names from the data
    name_mapping = {}
    seen_ids = set()
    
    for entry in station_times:
        # Process 'from' stations
        from_id = entry.get("station_from_naptan")
        if from_id and from_id not in seen_ids:
            from_name = entry.get("station_from")
            if from_name:
                name_mapping[from_id] = from_name
                seen_ids.add(from_id)
        
        # Process 'to' stations
        to_id = entry.get("station_to_naptan")
        if to_id and to_id not in seen_ids:
            to_name = entry.get("station_to")
            if to_name:
                name_mapping[to_id] = to_name
                seen_ids.add(to_id)
    
    return name_mapping

def main():
    tfl, optimizer = load_clients()
    station_names = get_station_names()
    line_id_mapping = get_line_id_mapping()
    
    # Create a list of station options for dropdown (sorted by name)
    station_options = sorted(
        [(name, sid) for sid, name in station_names.items()],
        key=lambda x: x[0]
    )
    station_display = [f"{name}" for name, _ in station_options]
    station_ids = [sid for _, sid in station_options]
    
    st.markdown("---")
    
    # Section: Starting Stations
    st.header("📍 Starting Stations")
    st.markdown("Select the tube stations where your group members are starting from.")
    
    # Initialize session state for starting stations
    if 'num_starting_stations' not in st.session_state:
        st.session_state.num_starting_stations = 2
    
    # Display station selection dropdowns
    cols = st.columns([3, 0.5])
    with cols[0]:
        selected_stations = []
        
        for idx in range(st.session_state.num_starting_stations):
            col1, col2 = st.columns([20, 1])
            
            with col1:
                selected_display = st.selectbox(
                    f"Starting Station {idx + 1}",
                    options=station_display,
                    key=f"station_{idx}",
                    label_visibility="collapsed"
                )
                if selected_display:
                    selected_id = station_ids[station_display.index(selected_display)]
                    selected_stations.append(selected_id)
            
            # Delete button (only show if more than 2 stations)
            with col2:
                if st.session_state.num_starting_stations > 2 and st.button("🗑️", key=f"delete_{idx}", help="Remove this station"):
                    st.session_state.num_starting_stations -= 1
                    st.rerun()
    
    # Add station button
    if st.button("➕ Add another starting station", use_container_width=True):
        st.session_state.num_starting_stations += 1
        st.rerun()
    
    st.markdown("---")
    
    # Section: Maps Constraint (Optional)
    st.header("🎯 Choose an Activity")
    st.markdown("(Optional) Find a location with nearby places of interest")
    
    # Initialize maps constraint session state
    if 'enable_poi_constraint' not in st.session_state:
        st.session_state.enable_poi_constraint = False
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        constraint_enabled = st.checkbox(
            "Enable Places of Interest Constraint",
            value=st.session_state.enable_poi_constraint,
            key="poi_checkbox"
        )
        st.session_state.enable_poi_constraint = constraint_enabled
    
    poi_constraint = None
    if constraint_enabled:
        with col2:
            poi_type = st.selectbox(
                "Type of Place",
                options=["restaurant", "pub", "park", "cafe", "bar", "museum", "library", "gym", "shopping_mall"],
                index=0,
                key="poi_type"
            )
        
        with st.expander("⚙️ Advanced Settings"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                min_count = st.number_input(
                    "Minimum Count",
                    min_value=1,
                    max_value=20,
                    value=5,
                    step=1,
                    key="poi_min_count"
                )
            
            with col2:
                min_rating = st.selectbox(
                    "Minimum Rating",
                    options=[1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
                    index=4,  # Default to 3.0
                    key="poi_min_rating"
                )
            
            with col3:
                max_distance = st.number_input(
                    "Max Distance (m)",
                    min_value=100,
                    max_value=2000,
                    value=500,
                    step=50,
                    key="poi_max_distance"
                )
        
        poi_constraint = {
            'type': poi_type,
            'min_count': min_count,
            'min_rating': min_rating,
            'max_distance': max_distance
        }
    
    st.markdown("---")
    
    # Section: Run Optimization
    st.header("🚀 Run Optimization")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("Click the button below to find the optimal meeting station for your group.")
    
    with col2:
        run_button = st.button("Find Optimal Station", use_container_width=True, type="primary")
    
    # Run optimization
    if run_button:
        # Validate inputs
        if not all(selected_stations):
            st.error("❌ Please select all starting stations")
        else:
            with st.spinner("🔄 Optimizing... This may take a moment..."):
                try:
                    # Run both optimizations
                    result_total_time = optimizer.optimize(
                        selected_stations,
                        objective='total_time',
                        poi_constraint=poi_constraint
                    )
                    
                    result_variance = optimizer.optimize(
                        selected_stations,
                        objective='variance',
                        poi_constraint=poi_constraint
                    )
                    
                    # Store results in session state
                    st.session_state.result_total_time = result_total_time
                    st.session_state.result_variance = result_variance
                    st.session_state.selected_stations = selected_stations
                    st.session_state.station_names = station_names
                    
                except ValueError as e:
                    st.error(f"❌ Optimization failed: {str(e)}")
                except Exception as e:
                    st.error(f"❌ An error occurred: {str(e)}")
    
    st.markdown("---")
    
    # Display Results
    if 'result_total_time' in st.session_state:
        st.header("✅ Results")
        
        result_total = st.session_state.result_total_time
        result_var = st.session_state.result_variance
        station_names = st.session_state.station_names
        selected_stn = st.session_state.selected_stations
        
        dest_total = result_total['destination']
        dest_variance = result_var['destination']
        
        # Display optimal stations
        st.markdown("### 🎯 Optimal Meeting Stations")
        
        if dest_total == dest_variance:
            # Same station for both objectives
            st.markdown(f"""
            <div class="result-container">
                <h3 style="margin: 0;">Overall Optimal Station</h3>
                <h2 style="color: #0066cc; margin: 10px 0;">{station_names.get(dest_total, dest_total)}</h2>
                <p style="margin: 0;">✓ Optimal for both minimum total travel time and fairness (minimum variance)</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            # Different stations for each objective
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"""
                <div class="result-container">
                    <h3 style="margin: 0;">⚡ Fastest Option</h3>
                    <h2 style="color: #0066cc; margin: 10px 0;">{station_names.get(dest_total, dest_total)}</h2>
                    <p style="margin: 0;">Minimizes total travel time</p>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.markdown(f"""
                <div class="result-container">
                    <h3 style="margin: 0;">⚖️ Fairest Option</h3>
                    <h2 style="color: #0066cc; margin: 10px 0;">{station_names.get(dest_variance, dest_variance)}</h2>
                    <p style="margin: 0;">Minimizes travel time variance</p>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Display journey details for both options (if different)
        results_to_show = {
            "Fastest": result_total
        }
        if dest_total != dest_variance:
            results_to_show["Fairest"] = result_var
        
        for option_name, result in results_to_show.items():
            st.markdown(f"### {option_name} Option - Journey Details")
            
            destination = result['destination']
            routes = result['routes']
            
            # Calculate journey times and get line segments
            journey_info = []
            for start_idx, start_station in enumerate(selected_stn):
                path = routes[start_station]
                
                # Calculate total time correctly (sum all legs)
                total_time = 0
                for i in range(len(path) - 1):
                    try:
                        leg_time, _ = tfl.get_journey_time_with_penalty(path[i], path[i+1])
                        total_time += leg_time
                    except:
                        pass
                
                # Get line segments
                segments = tfl.get_line_segments(path)
                
                journey_info.append({
                    'start': start_station,
                    'path': path,
                    'segments': segments,
                    'time': total_time,
                    'idx': start_idx
                })
            
            # Get all unique lines used in this option's journeys
            all_lines_set = set()
            for j_info in journey_info:
                for segment in j_info['segments']:
                    all_lines_set.add(segment['line'])
            
            # Get line status information
            line_status_map = {}
            try:
                line_status = tfl.get_line_status()
                for line_id, line_data in line_status.items():
                    if line_id != 'timestamp':
                        line_status_map[line_id] = line_data
            except:
                pass
            
            # Display each journey
            for j_info in sorted(journey_info, key=lambda x: x['idx']):
                start_name = station_names.get(j_info['start'], j_info['start'])
                end_name = station_names.get(destination, destination)
                
                st.markdown(f"""
                <div class="journey-card">
                    <strong>Person {j_info['idx'] + 1}: {start_name} → {end_name}</strong><br>
                    <strong>Estimated time: {j_info['time']:.1f} minutes</strong>
                </div>
                """, unsafe_allow_html=True)
                
                # Display line segments
                if j_info['segments']:
                    for seg in j_info['segments']:
                        line_name = seg['line']
                        from_name = station_names.get(seg['from_station'], seg['from_station'])
                        to_name = station_names.get(seg['to_station'], seg['to_station'])
                        
                        # Get line status - convert line name to TfL line ID first
                        tfl_line_id = line_id_mapping.get(line_name, line_name.lower())
                        line_status_info = line_status_map.get(tfl_line_id, {})
                        status_codes = line_status_info.get('status_codes', ['Unknown'])
                        status_display = ', '.join(status_codes)
                        
                        # Color code based on status
                        if 'Good Service' in status_display:
                            status_color = '#28a745'  # Green
                            status_emoji = '✅'
                        else:
                            status_color = '#ffc107'  # Yellow/Orange
                            status_emoji = '⚠️'
                        
                        st.markdown(f"""
                        <div style="margin-left: 20px; padding: 8px; border-left: 3px solid {status_color};">
                            📍 {from_name} <span style="color: #0066cc; font-weight: bold;">→ {line_name} → </span> {to_name}<br>
                            <span style="font-size: 12px; color: #666;">{status_emoji} {status_display}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='margin-left: 20px; color: #666;'><em>Direct journey</em></div>", unsafe_allow_html=True)
            
            st.markdown("---")

if __name__ == "__main__":
    main()
