import streamlit as st
import pandas as pd
import zipfile
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# Set page layout to wide for better charting
st.set_page_config(page_title="Rig Data Viewer", layout="wide")

@st.cache_data
def load_peep_file(uploaded_file):
    with zipfile.ZipFile(uploaded_file, 'r') as z:
        target_file = next((f for f in z.namelist() if f.endswith('.tp1')), None)
        if target_file:
            with z.open(target_file) as f:
                df = pd.read_csv(f, sep='\t', low_memory=False)
                return df
    return None

st.title("Time Log")

uploaded_file = st.file_uploader("Upload a .peep archive", type=["peep"])

if uploaded_file is not None:
    with st.spinner('Loading .tp1 data into memory... This may take a few seconds.'):
        df = load_peep_file(uploaded_file)
    
    if df is not None:
        # CLEANUP
        df.columns = df.columns.str.strip()
        df = df.loc[:, ~df.columns.duplicated()].copy()
        
        y_cols = [c for c in df.columns if str(c).endswith('(Y)')]
        
        if len(y_cols) > 0:
            st.success(f"Detected {len(y_cols)} available sensor channels.")
            base_params = [c.replace('(Y)', '') for c in y_cols]
            
            # This multiselect is outside the form so it updates immediately when you pick a new sensor
            selected_params = st.multiselect("Select Parameters to Overlay in Track", base_params)
            
            if selected_params:
                st.divider()
                
                # --- PROCESS ALL SELECTED TRACES FIRST ---
                traces_data = {}
                global_min_time = None
                global_max_time = None
                
                for param in selected_params:
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
                        
                        if not temp_df.empty and pd.api.types.is_datetime64_any_dtype(temp_df['Time']):
                            traces_data[param] = temp_df
                            t_min = temp_df['Time'].min()
                            t_max = temp_df['Time'].max()
                            
                            if global_min_time is None or t_min < global_min_time:
                                global_min_time = t_min
                            if global_max_time is None or t_max > global_max_time:
                                global_max_time = t_max

                if not traces_data:
                    st.error("No valid data survived the cleanup process for the selected parameters.")
                else:
                    # 🚨 HARDCODED PRESETS: Add or change defaults here 
                    PRESET_SCALES = {
                        "StandPipeSystem.PRS.1.TRC": {"min": 0.0, "max": 3000.0},
                        "HoistingSystem.HKH.1.TRC": {"min": 0.0, "max": 190.0},
                        "FlowMonitoring.PumpFlow.1": {"min": 0.0, "max": 1000.0},
                        "DrillBoreHoleReaming.ROPOnDepthStep": {"min": 0.0, "max": 200.0},
                        "HoistingSystem.WOH.1.TRC": {"min": 0.0, "max": 800.0}
                    }

                    # --- 🚨 THE CONTROL PANEL FORM 🚨 ---
                    # Everything inside this 'with' block won't trigger a refresh until "Submit" is pressed
                    with st.form("chart_settings_form"):
                        st.subheader("1. Filter Master Time Interval")
                        min_dt = global_min_time.to_pydatetime()
                        max_dt = global_max_time.to_pydatetime()
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            start_date = st.date_input("Start Date", min_dt.date())
                            start_time = st.time_input("Start Time", min_dt.time())
                        with c2:
                            end_date = st.date_input("End Date", max_dt.date())
                            end_time = st.time_input("End Time", max_dt.time())
                        
                        st.divider()
                        st.subheader("2. Adjust Individual Data Scales (X-Axis)")
                        
                        colors = px.colors.qualitative.Plotly
                        scales = {}
                        
                        for i, param in enumerate(selected_params):
                            if param not in traces_data:
                                continue
                                
                            color = colors[i % len(colors)]
                            
                            # Check if we have a hardcoded preset for this parameter
                            if param in PRESET_SCALES:
                                def_min = PRESET_SCALES[param]["min"]
                                def_max = PRESET_SCALES[param]["max"]
                            else:
                                # Fallback: Auto-calculate scale from the raw data
                                y_col = f"{param}(Y)"
                                data_min = float(traces_data[param][y_col].min())
                                data_max = float(traces_data[param][y_col].max())
                                buffer = (data_max - data_min) * 0.05 if data_max != data_min else 1.0
                                def_min = data_min - buffer
                                def_max = data_max + buffer
                            
                            col_name, col_min, col_max = st.columns([2, 1, 1])
                            with col_name:
                                st.markdown(f"<h4 style='color:{color}; margin-top:25px;'>{param}</h4>", unsafe_allow_html=True)
                            with col_min:
                                u_min = st.number_input("Min", value=float(def_min), key=f"min_{param}")
                            with col_max:
                                u_max = st.number_input("Max", value=float(def_max), key=f"max_{param}")
                                
                            scales[param] = (u_min, u_max, color)
                            
                        # The button that fires the form
                        submit_button = st.form_submit_button("🚀 Generate / Update Chart")

                    # --- BUILD THE CHART (Runs after the form is submitted) ---
                    start_dt = datetime.combine(start_date, start_time)
                    end_dt = datetime.combine(end_date, end_time)
                    
                    filtered_traces = {}
                    for param in selected_params:
                        if param in traces_data:
                            t_df = traces_data[param]
                            mask = (t_df['Time'] >= start_dt) & (t_df['Time'] <= end_dt)
                            f_df = t_df.loc[mask]
                            if not f_df.empty:
                                filtered_traces[param] = f_df
                                
                    if not filtered_traces:
                        st.warning("No data found in this time range.")
                    else:
                        num_params = len(filtered_traces)
                        axis_gap = 0.06 
                        y_domain_top = 1.0 - (axis_gap * (num_params - 1)) if num_params > 1 else 1.0
                        
                        fig = go.Figure()
                        
                        layout_updates = {
                            'yaxis': dict(autorange='reversed', title='Time', domain=[0, y_domain_top]),
                            'dragmode': 'pan',
                            'height': 800 + (num_params * 40), 
                            'margin': dict(t=50 + (num_params * 30), b=80), 
                            'legend': dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5)
                        }
                        
                        for i, (param, f_df) in enumerate(filtered_traces.items()):
                            y_col = f"{param}(Y)"
                            u_min, u_max, color = scales[param]
                            
                            axis_name = 'x' if i == 0 else f'x{i+1}'
                            layout_axis_name = 'xaxis' if i == 0 else f'xaxis{i+1}'
                            
                            fig.add_trace(go.Scatter(
                                x=f_df[y_col],
                                y=f_df['Time'],
                                mode='lines',
                                name=param,
                                xaxis=axis_name,
                                line=dict(color=color, width=1.5)
                            ))
                            
                            if i == 0:
                                layout_updates[layout_axis_name] = dict(
                                    range=[u_min, u_max], side='top', showgrid=True, zeroline=False,
                                    showticklabels=True, tickfont=dict(color=color), fixedrange=True 
                                )
                            else:
                                layout_updates[layout_axis_name] = dict(
                                    range=[u_min, u_max], overlaying='x', side='top', showgrid=False, zeroline=False,
                                    showticklabels=True, tickfont=dict(color=color),
                                    anchor='free', position=y_domain_top + (i * axis_gap), fixedrange=True 
                                )
                                
                        fig.update_layout(**layout_updates)
                        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
            else:
                st.info("👆 Please select one or more parameters from the dropdown above to generate the log.")
        else:
            st.warning("Standard (X)/(Y) tags not found. This file format may not support composite tracks.")
    else:
        st.error("Could not find a valid .tp1 data file inside the archive.")