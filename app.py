import streamlit as st
import pandas as pd
import zipfile
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# Set page layout to wide and inject CSS to remove empty top space
st.set_page_config(page_title="Rig Data Viewer", layout="wide")
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

@st.cache_data
def load_peep_file(uploaded_file):
    with zipfile.ZipFile(uploaded_file, 'r') as z:
        target_file = next((f for f in z.namelist() if f.endswith('.tp1')), None)
        if target_file:
            with z.open(target_file) as f:
                df = pd.read_csv(f, sep='\t', low_memory=False)
                return df
    return None

st.title("Tri-Track Rig Sensor Log")

uploaded_file = st.file_uploader("Upload a .peep archive", type=["peep"])

if uploaded_file is not None:
    with st.spinner('Loading archive into memory...'):
        df = load_peep_file(uploaded_file)
    
    if df is not None:
        df.columns = df.columns.str.strip()
        df = df.loc[:, ~df.columns.duplicated()].copy()
        
        y_cols = [c for c in df.columns if str(c).endswith('(Y)')]
        
        if len(y_cols) > 0:
            st.success(f"Detected {len(y_cols)} available sensor channels.")
            base_params = [c.replace('(Y)', '') for c in y_cols]
            
            # --- 🚨 UPDATED IDEAL DEFAULT TEMPLATES ---
            ideal_t1 = [
                "StandPipeSystem.PRS.1.TRC", 
                "HoistingSystem.HKH.1.TRC", 
                "FlowMonitoring.PumpFlow.1", 
                "HoistingSystem.WOH.1.TRC"
            ]
            ideal_t2 = [
                "TopDrive.TRQ.1.TRC", 
                "TopDrive.RPM.1.TRC",
                "DrillBoreHoleReaming.WOBDriller",
                "DrillBoreHoleReaming.ROPOnDepthStep"
            ]
            ideal_t3 = [
                "FlowLineSystem.Fpdl.1.TRC",
                "DegasserOut_1.MW.Modbus.TRC",
                "DegasserIn_1.MW.Modbus.TRC",
                "DegasserOut_1.TMP.Modbus.TRC",
                "DegasserIn_1.TMP.Modbus.TRC"
            ]
            
            # Safety check: Only apply defaults if they actually exist in this specific file
            def_t1 = [p for p in ideal_t1 if p in base_params]
            def_t2 = [p for p in ideal_t2 if p in base_params]
            def_t3 = [p for p in ideal_t3 if p in base_params]

            # --- TRI-TRACK SELECTION UI (Ratio: 50% / 25% / 25%) ---
            t1_col, t2_col, t3_col = st.columns([2, 1, 1])
            with t1_col:
                track1_params = st.multiselect("Select Parameters for TRACK 1", base_params, default=def_t1)
            with t2_col:
                track2_params = st.multiselect("Select Parameters for TRACK 2", base_params, default=def_t2)
            with t3_col:
                track3_params = st.multiselect("Select Parameters for TRACK 3", base_params, default=def_t3)
            
            all_selected_params = list(dict.fromkeys(track1_params + track2_params + track3_params))
            
            if all_selected_params:
                st.divider()
                
                # Fast global time extraction
                global_min_time = None
                global_max_time = None
                x_cols = [c for c in df.columns if str(c).endswith('(X)')]
                
                if x_cols:
                    first_x = x_cols[0]
                    raw_x = df[first_x].iloc[:, 0] if isinstance(df[first_x], pd.DataFrame) else df[first_x]
                    numeric_time = pd.to_numeric(raw_x, errors='coerce')
                    
                    if numeric_time.notna().any():
                        base_date = pd.Timestamp('1899-12-30')
                        global_min_time = base_date + pd.to_timedelta(numeric_time.min(), unit='D')
                        global_max_time = base_date + pd.to_timedelta(numeric_time.max(), unit='D')
                    else:
                        dt_time = pd.to_datetime(raw_x, errors='coerce').dropna()
                        if not dt_time.empty:
                            global_min_time = dt_time.min()
                            global_max_time = dt_time.max()

                if global_min_time is None:
                    global_min_time = datetime.now()
                    global_max_time = datetime.now()

                # 🚨 UPDATED HARDCODED PRESETS WITH NEW TRACK 3 SENSORS
                PRESET_SCALES = {
                    "StandPipeSystem.PRS.1.TRC": {"min": 0.0, "max": 4000.0},
                    "HoistingSystem.HKH.1.TRC": {"min": 0.0, "max": 190.0},
                    "FlowMonitoring.PumpFlow.1": {"min": 0.0, "max": 1000.0},
                    "HoistingSystem.WOH.1.TRC": {"min": 0.0, "max": 420.0},
                    "TopDrive.TRQ.1.TRC": {"min": 0.0, "max": 50000.0},
                    "TopDrive.RPM.1.TRC": {"min": 0.0, "max": 100.0},
                    "DrillBoreHoleReaming.WOBDriller": {"min": 0.0, "max": 200.0},
                    "DrillBoreHoleReaming.ROPOnDepthStep": {"min": 0.0, "max": 300.0},
                    "FlowLineSystem.Fpdl.1.TRC": {"min": 0.0, "max": 100.0},
                    "DegasserOut_1.MW.Modbus.TRC": {"min": 5.0, "max": 13.0},
                    "DegasserIn_1.MW.Modbus.TRC": {"min": 5.0, "max": 13.0},
                    "DegasserOut_1.TMP.Modbus.TRC": {"min": 0.0, "max": 250.0},
                    "DegasserIn_1.TMP.Modbus.TRC": {"min": 0.0, "max": 250.0}
                }
                
                colors = px.colors.qualitative.Plotly
                color_map = {param: colors[i % len(colors)] for i, param in enumerate(all_selected_params)}

                with st.form("chart_settings_form"):
                    st.subheader("1. Filter Master Time Interval")
                    min_dt = global_min_time if isinstance(global_min_time, datetime) else global_min_time.to_pydatetime()
                    max_dt = global_max_time if isinstance(global_max_time, datetime) else global_max_time.to_pydatetime()
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        start_date = st.date_input("Start Date", min_dt.date())
                        start_time = st.time_input("Start Time", min_dt.time())
                    with c2:
                        end_date = st.date_input("End Date", max_dt.date())
                        end_time = st.time_input("End Time", max_dt.time())
                    
                    st.divider()
                    st.subheader("2. Adjust Individual Data Scales (X-Axis)")
                    
                    scales = {}
                    
                    # --- SCALE SETTINGS UI ---
                    ui_t1, ui_t2, ui_t3 = st.columns([2, 1, 1])
                    
                    track_configs = [
                        (ui_t1, track1_params, "TRACK 1"),
                        (ui_t2, track2_params, "TRACK 2"),
                        (ui_t3, track3_params, "TRACK 3")
                    ]
                    
                    for track_col, t_params, t_name in track_configs:
                        with track_col:
                            if t_params:
                                st.markdown(f"**{t_name} SCALES**")
                            for param in t_params:
                                color = color_map[param]
                                
                                def_min = PRESET_SCALES[param]["min"] if param in PRESET_SCALES else 0.0
                                def_max = PRESET_SCALES[param]["max"] if param in PRESET_SCALES else 1000.0
                                
                                c_name, c_min, c_max = st.columns([2, 1, 1])
                                with c_name:
                                    st.markdown(f"<h5 style='color:{color}; margin-top:28px; font-size:14px;'>{param}</h5>", unsafe_allow_html=True)
                                with c_min:
                                    u_min = st.number_input("Min", value=float(def_min), key=f"min_{t_name}_{param}")
                                with c_max:
                                    u_max = st.number_input("Max", value=float(def_max), key=f"max_{t_name}_{param}")
                                    
                                scales[f"{t_name}_{param}"] = (u_min, u_max)
                        
                    submit_button = st.form_submit_button("🚀 Generate / Update Tri-Track Chart")

                # --- BUILD THE CHART ---
                if submit_button:
                    with st.spinner("Processing tracks and syncing axes..."):
                        start_dt = datetime.combine(start_date, start_time)
                        end_dt = datetime.combine(end_date, end_time)
                        
                        filtered_traces = {}
                        for param in all_selected_params:
                            x_col = f"{param}(X)"
                            y_col = f"{param}(Y)"
                            
                            if x_col in df.columns and y_col in df.columns:
                                raw_x = df[x_col].iloc[:, 0] if isinstance(df[x_col], pd.DataFrame) else df[x_col]
                                raw_y = df[y_col].iloc[:, 0] if isinstance(df[y_col], pd.DataFrame) else df[y_col]
                                
                                temp_df = pd.DataFrame({'Time': raw_x, y_col: raw_y}).dropna()
                                
                                base_date = pd.Timestamp('1899-12-30')
                                numeric_time = pd.to_numeric(temp_df['Time'], errors='coerce')
                                
                                if numeric_time.notna().any():
                                    temp_df['Time'] = base_date + pd.to_timedelta(numeric_time, unit='D')
                                else:
                                    temp_df['Time'] = pd.to_datetime(temp_df['Time'], errors='coerce')
                                
                                temp_df = temp_df.dropna(subset=['Time'])
                                temp_df[y_col] = pd.to_numeric(temp_df[y_col], errors='coerce')
                                temp_df = temp_df.dropna()
                                
                                mask = (temp_df['Time'] >= start_dt) & (temp_df['Time'] <= end_dt)
                                f_df = temp_df.loc[mask]
                                
                                if not f_df.empty:
                                    filtered_traces[param] = f_df
                                    
                        if not filtered_traces:
                            st.warning("No data found in this time range.")
                        else:
                            # DYNAMIC DOMAIN MATH
                            max_params = max(len(track1_params), len(track2_params), len(track3_params))
                            axis_gap = 0.05 
                            y_domain_top = 1.0 - (axis_gap * (max_params - 1)) if max_params > 1 else 1.0
                            
                            if len(track3_params) > 0:
                                track_domains = [
                                    ("TRACK 1", track1_params, [0.0, 0.48]),
                                    ("TRACK 2", track2_params, [0.52, 0.74]), 
                                    ("TRACK 3", track3_params, [0.78, 1.0])   
                                ]
                            else:
                                track_domains = [
                                    ("TRACK 1", track1_params, [0.0, 0.48]),
                                    ("TRACK 2", track2_params, [0.52, 1.0])   
                                ]
                            
                            fig = go.Figure()
                            
                            layout_updates = {
                                'yaxis': dict(autorange='reversed', title='Time', domain=[0, y_domain_top]),
                                'dragmode': 'pan',
                                'height': 850, 
                                'margin': dict(t=50, b=40, l=40, r=40), 
                                'showlegend': False 
                            }
                            
                            axis_counter = 1
                            
                            for t_name, t_params, x_domain in track_domains:
                                if not t_params: continue
                                
                                base_axis_name = f'x{axis_counter}' if axis_counter > 1 else 'x'
                                
                                for i, param in enumerate(t_params):
                                    if param not in filtered_traces: continue
                                    
                                    u_min, u_max = scales[f"{t_name}_{param}"]
                                    color = color_map[param]
                                    f_df = filtered_traces[param]
                                    
                                    axis_name = f'x{axis_counter}' if axis_counter > 1 else 'x'
                                    layout_axis_name = f'xaxis{axis_counter}' if axis_counter > 1 else 'xaxis'
                                    
                                    fig.add_trace(go.Scatter(
                                        x=f_df[f"{param}(Y)"],
                                        y=f_df['Time'],
                                        mode='lines',
                                        name=param,
                                        xaxis=axis_name,
                                        line=dict(color=color, width=1.5)
                                    ))
                                    
                                    if i == 0:
                                        layout_updates[layout_axis_name] = dict(
                                            title=dict(text=param, font=dict(color=color, size=12), standoff=0),
                                            range=[u_min, u_max], side='top', showgrid=True, zeroline=False,
                                            showticklabels=True, tickfont=dict(color=color, size=10), fixedrange=True,
                                            domain=x_domain
                                        )
                                    else:
                                        layout_updates[layout_axis_name] = dict(
                                            title=dict(text=param, font=dict(color=color, size=12), standoff=0),
                                            range=[u_min, u_max], overlaying=base_axis_name, side='top', showgrid=False, zeroline=False,
                                            showticklabels=True, tickfont=dict(color=color, size=10), fixedrange=True,
                                            anchor='free', position=y_domain_top + (i * axis_gap),
                                            domain=x_domain
                                        )
                                        
                                    axis_counter += 1
                                    
                            fig.update_layout(**layout_updates)
                            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
            else:
                st.info("👆 Please select parameters for Track 1, Track 2, or Track 3 to generate the log.")
        else:
            st.warning("Standard (X)/(Y) tags not found. This file format may not support composite tracks.")
    else:
        st.error("Could not find a valid .tp1 data file inside the archive.")