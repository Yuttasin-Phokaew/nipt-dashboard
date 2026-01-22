# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
from google.oauth2.service_account import Credentials
import re 

# --- 1. การตั้งค่า (Configuration) ---
# ใช้ ID เดิมของคุณ
SPREADSHEET_ID = '1VNblxx_MoETV5eynsIDtx22-y9OvXsYQ-2uFsq62U8M'
SHEET_NAME = 'DashBoard' 

REGIONAL_ORDER_1_13 = [f'เขตสุขภาพที่ {i}' for i in range(1, 13)]
REGIONAL_ORDER_1_13.append('ส่วนกลาง/อื่นๆ')

# --- 2. ฟังก์ชันจัดการข้อมูล ---
CHROMOSOME_GROUPS = ['T13', 'T18', 'T21', 'XO', 'XXX', 'XXY', 'XYY']
NON_CHROMOSOME_GROUPS = ['Low risk', 'Re-sampling', 'Re-library', 'No Call']

def map_risk_category(result):
    result_lower = str(result).lower().strip()
    if 'high risk' in result_lower or 'positive' in result_lower:
        return 'High risk'
    elif 'low risk' in result_lower or 'negative' in result_lower:
        return 'Low risk'
    elif 're-sampling' in result_lower or 'resampling' in result_lower:
        return 'Re-sampling'
    elif 're-library' in result_lower or 'relibrary' in result_lower:
        return 'Re-library'
    elif 'no call' in result_lower or 'nocall' in result_lower:
        return 'No Call'
    return 'Other' 

def clean_and_map_lab_results(result):
    result_upper = str(result).strip().upper()
    pattern = r'(' + '|'.join(re.escape(g) for g in CHROMOSOME_GROUPS) + r')'
    match = re.search(pattern, result_upper)
    if match:
        return match.group(1)
    risk_cat = map_risk_category(result_upper)
    if risk_cat in NON_CHROMOSOME_GROUPS:
        return risk_cat
    return 'Other (Detailed)'

@st.cache_data(ttl=600)
def load_data():
    try:
        # --- จุดที่แก้ไข: ดึง Credentials จาก Secrets แทนไฟล์ ---
        if "gcp_service_account" not in st.secrets:
            st.error("❌ ไม่พบข้อมูล 'gcp_service_account' ใน Streamlit Secrets")
            return pd.DataFrame()
            
        creds_info = st.secrets["gcp_service_account"]
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        gc = gspread.authorize(creds)
        
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)

        data = worksheet.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        df.columns = ['lab_no', 'institute', 'province', 'regional', 'lab_results']
        
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            
        invalid_vals = ['', 'nan', 'None', 'undefined', 'ไม่พบเขตสุขภาพ']
        df = df[~df['regional'].isin(invalid_vals)]
        df = df[~df['lab_results'].isin(invalid_vals)]

        df['lab_group'] = df['lab_results'].apply(clean_and_map_lab_results)
        df['risk_category'] = df['lab_results'].apply(map_risk_category)
        
        return df
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return pd.DataFrame()

def set_styles():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;600&display=swap');
        html, body, [class*="st-"] { font-family: 'Kanit', sans-serif; }
        .stMetric { background-color: #FFFFFF; border-radius: 8px; padding: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
        </style>
        """, unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="NIPT Analytics Dashboard", layout="wide")
    set_styles()
    st.title("📊 NIPT-NGS Data Analysis Dashboard")
    st.markdown("---")
    
    df_full = load_data()
    if df_full.empty: return

    # --- Filter Controls ---
    actual_regionals = df_full['regional'].unique().tolist()
    def get_regional_order(region_name):
        try: return REGIONAL_ORDER_1_13.index(str(region_name))
        except ValueError: return 99
    existing_regionals = sorted(actual_regionals, key=get_regional_order)
    
    col1, col2, col3, col4 = st.columns([1, 1, 1, 0.8]) 
    with col1: selected_regional = st.selectbox("เลือกเขตสุขภาพ", ['ทั้งหมด'] + existing_regionals)

    df_filtered = df_full.copy()
    if selected_regional != 'ทั้งหมด':
        df_filtered = df_filtered[df_filtered['regional'] == selected_regional]

    with col2:
        provinces_in_region = ['ทั้งหมด'] + sorted(df_filtered['province'].unique().tolist())
        selected_province = st.selectbox("เลือกจังหวัด", provinces_in_region)
    if selected_province != 'ทั้งหมด':
        df_filtered = df_filtered[df_filtered['province'] == selected_province]
        
    with col3:
        all_risk_categories = ['ทั้งหมด'] + sorted(df_full['risk_category'].unique().tolist())
        selected_risk = st.selectbox("ผลการตรวจหลัก", all_risk_categories)
    if selected_risk != 'ทั้งหมด':
        df_filtered = df_filtered[df_filtered['risk_category'] == selected_risk]

    with col4:
        st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True) 
        show_detailed = st.toggle("แสดงผลแบบละเอียด")

    # --- KPI Metrics ---
    total_cases = len(df_filtered)
    st.subheader(f"ภาพรวมข้อมูล ({total_cases:,} เคส)")
    
    df_kpi = df_filtered.groupby('risk_category').size().to_dict()
    RISK_TYPES = ['Low risk', 'High risk', 'Re-sampling', 'Re-library', 'No Call']
    
    cols = st.columns(len(RISK_TYPES))
    for i, risk in enumerate(RISK_TYPES):
        count = df_kpi.get(risk, 0)
        percent = (count/total_cases*100) if total_cases > 0 else 0
        cols[i].metric(risk, f"{count:,}", f"{percent:.1f}%", delta_color="normal" if risk=="Low risk" else "inverse")

    # --- Charts ---
    c1, c2 = st.columns(2)
    risk_colors = {'High risk':'#E54747', 'Low risk':'#33A02C', 'Re-sampling':'#FFBF00', 'Re-library':'#007bb6', 'No Call': '#606060'}

    with c1:
        fig_pie = px.pie(df_filtered, names='risk_category', color='risk_category', color_discrete_map=risk_colors, hole=0.4)
        fig_pie.update_layout(title="สัดส่วนผลตรวจ")
        st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        group_col = 'lab_group' if show_detailed else 'risk_category'
        if selected_regional != 'ทั้งหมด':
            df_bar = df_filtered.groupby(['province', group_col]).size().reset_index(name='count')
            fig_bar = px.bar(df_bar, x='province', y='count', color=group_col, barmode='group', color_discrete_map=risk_colors)
        else:
            df_bar = df_filtered.groupby('regional').size().reset_index(name='count')
            fig_bar = px.bar(df_bar, x='regional', y='count', text='count')
        st.plotly_chart(fig_bar, use_container_width=True)

    # --- Data Table ---
    st.dataframe(df_filtered[['lab_no', 'institute', 'province', 'regional', 'lab_results']], use_container_width=True)

if __name__ == "__main__":
    main()
