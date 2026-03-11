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
def load_stations() -> Dict[str, str]:
    """Load all tube stations and their names. Maps station_name -> station_id."""
    tfl = TflRequest()
    all_station_ids = tfl.get_all_stations()
    
    stations = {}
    for station_id in all_station_ids:
        try:
            coords = tfl.get_station_coords(station_id)
            # The station_id from get_station_coords is cached, and we can use the TfL API
            # to fetch the station name. However, since get_station_coords is cached,
            # we need a way to get the name. Let's construct a readable version.
            stations[station_id] = station_id
        except Exception:
            stations[station_id] = station_id
    
    return stations

@st.cache_data
def get_station_names() -> Dict[str, str]:
    """Create a mapping of station ID to readable name by fetching from API."""
    tfl = TflRequest()
    all_station_ids = tfl.get_all_stations()
    
    name_mapping = {}
    for station_id in all_station_ids:
        try:
            # Fetch station info via API to get the name
            import httpx
            from os import getenv
            from dotenv import load_dotenv
            load_dotenv()
            api_key = getenv("TFL_API_KEY")
            response = httpx.get(
                f"https://api.tfl.gov.uk/StopPoint/{station_id}?app_key={api_key}"
            )
            if response.status_code == 200:
                data = response.json()
                name = data.get("commonName", station_id)
                name_mapping[station_id] = name
            else:
                name_mapping[station_id] = station_id
        except Exception:
            name_mapping[station_id] = station_id
    
    return name_mapping

def format_journey(start_station_id: str, end_station_id: str, path: List[str], station_names: Dict[str, str]) -> str:
    """Format a journey path as a readable string."""
    if not path or len(path) < 2:
        return f"{station_names.get(start_station_id, start_station_id)} → {station_names.get(end_station_id, end_station_id)}"
    
    # Build journey string
    journey_parts = []
    journey_parts.append(station_names.get(path[0], path[0]))
    
    for i, station in enumerate(path[1:], 1):
        journey_parts.append(station_names.get(station, station))
    
    return " → ".join(journey_parts)

def main():
    tfl, optimizer = load_clients()
    station_names = get_station_names()
    
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
        st.session_state.starting_stations = [None, None]
    
    # Display station selection dropdowns
    cols = st.columns([3, 0.5])
    with cols[0]:
        selected_stations = []
        
        for idx in range(st.session_state.num_starting_stations):
            col1, col2 = st.columns([20, 1])
            
            with col1:
                # Find the current selection index
                current_selection = st.session_state.starting_stations[idx] if idx < len(st.session_state.starting_stations) else None
                current_index = 0
                if current_selection and current_selection in station_ids:
                    current_index = station_ids.index(current_selection)
                
                selected_display = st.selectbox(
                    f"Starting Station {idx + 1}",
                    options=station_display,
                    index=current_index,
                    key=f"station_{idx}",
                    label_visibility="collapsed"
                )
                selected_id = station_ids[station_display.index(selected_display)]
                selected_stations.append(selected_id)
                
                # Update session state
                if idx < len(st.session_state.starting_stations):
                    st.session_state.starting_stations[idx] = selected_id
                else:
                    st.session_state.starting_stations.append(selected_id)
            
            # Delete button (only show if more than 2 stations)
            with col2:
                if st.session_state.num_starting_stations > 2 and st.button("🗑️", key=f"delete_{idx}", help="Remove this station"):
                    st.session_state.num_starting_stations -= 1
                    st.session_state.starting_stations.pop(idx)
                    st.rerun()
    
    # Add station button
    if st.button("➕ Add Another Starting Station", use_container_width=True):
        st.session_state.num_starting_stations += 1
        st.session_state.starting_stations.append(None)
        st.rerun()
    
    st.markdown("---")
    
    # Section: Maps Constraint (Optional)
    st.header("🗺️ Optional: Places of Interest Constraint")
    st.markdown("Add a constraint to ensure the meeting location has nearby restaurants, pubs, parks, etc.")
    
    # Initialize maps constraint session state
    if 'enable_poi_constraint' not in st.session_state:
        st.session_state.enable_poi_constraint = False
    
    constraint_enabled = st.checkbox(
        "Enable Places of Interest Constraint",
        value=st.session_state.enable_poi_constraint,
        key="poi_checkbox"
    )
    st.session_state.enable_poi_constraint = constraint_enabled
    
    poi_constraint = None
    if constraint_enabled:
        with st.expander("⚙️ POI Constraint Settings", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                poi_type = st.selectbox(
                    "Type of Place",
                    options=["restaurant", "pub", "park", "cafe", "bar", "museum", "library", "gym", "shopping_mall"],
                    index=0,
                    key="poi_type"
                )
            
            with col2:
                min_count = st.number_input(
                    "Minimum Count",
                    min_value=1,
                    max_value=20,
                    value=5,
                    step=1,
                    key="poi_min_count"
                )
            
            with col3:
                min_rating = st.selectbox(
                    "Minimum Rating",
                    options=[1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
                    index=4,  # Default to 3.0
                    key="poi_min_rating"
                )
            
            with col4:
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
            
            # Calculate journey times
            journey_times = []
            for start_idx, start_station in enumerate(selected_stn):
                path = routes[start_station]
                
                # Calculate total time
                total_time = 0
                for i in range(len(path) - 1):
                    try:
                        leg_time, _ = tfl.get_journey_time_with_penalty(path[i], path[i+1])
                        total_time = leg_time
                    except:
                        pass
                
                journey_times.append({
                    'start': start_station,
                    'path': path,
                    'time': total_time,
                    'idx': start_idx
                })
            
            # Display each journey
            for j_info in sorted(journey_times, key=lambda x: x['idx']):
                start_name = station_names.get(j_info['start'], j_info['start'])
                end_name = station_names.get(destination, destination)
                
                path_display = " → ".join(
                    [station_names.get(sid, sid) for sid in j_info['path']]
                )
                
                st.markdown(f"""
                <div class="journey-card">
                    <strong>Person {j_info['idx'] + 1}: {start_name} → {end_name}</strong><br>
                    <em>Journey: {path_display}</em><br>
                    <strong>Estimated time: {j_info['time']:.1f} minutes</strong>
                </div>
                """, unsafe_allow_html=True)
            
            # Check line status
            st.markdown("#### 🚆 Current Line Status")
            
            all_lines = set()
            for journey in journey_times:
                path = journey['path']
                for i in range(len(path) - 1):
                    try:
                        # Get the line info from the journey
                        graph = tfl._build_graph()
                        for dest, rt, line in graph.get(path[i], []):
                            if dest == path[i+1]:
                                all_lines.add(line)
                    except:
                        pass
            
            if all_lines:
                try:
                    line_status = tfl.get_line_status()
                    
                    has_delays = False
                    for line_id in all_lines:
                        # Get status for this line
                        if line_id in line_status:
                            status_codes = line_status[line_id]['status_codes']
                            line_name = line_status[line_id]['name']
                            
                            if 'Severe Delays' in status_codes or 'Delays' in status_codes or 'Service Closed' in status_codes:
                                st.markdown(f"""
                                <div class="status-warning">
                                    <strong>⚠️ {line_name}:</strong> {', '.join(status_codes)}
                                </div>
                                """, unsafe_allow_html=True)
                                has_delays = True
                    
                    if not has_delays:
                        st.success("✓ All lines operating normally")
                except:
                    st.info("Could not fetch line status at this time")
            
            st.markdown("---")

if __name__ == "__main__":
    main()
