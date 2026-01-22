# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError
import re 
import json

# --- 1. การตั้งค่าข้อมูลและการเชื่อมต่อ (Configuration) ---
SPREADSHEET_ID = '1VNblxx_MoETV5eynsIDtx22-y9OvXsYQ-2uFsq62U8M'
SHEET_NAME = 'DashBoard' 
CREDENTIALS_FILE = 'google_sheet_credentials.json'

REGIONAL_ORDER_1_13 = [f'เขตสุขภาพที่ {i}' for i in range(1, 14)] # แก้เป็น 14 เพื่อให้ครอบคลุมถึงเขต 13
REGIONAL_ORDER_1_13.append('ส่วนกลาง/อื่นๆ')

# --- 2. ฟังก์ชันจัดการข้อมูล (Data Processing) ---
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
    return 'Other'

@st.cache_data(ttl=600)
def load_data():
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        
        # ตรวจสอบชื่อใน st.secrets ให้ตรงกับหัวข้อในเมนู Secrets
        if "gcp_service_account" in st.secrets:
            creds_info = st.secrets["gcp_service_account"]
            # ใช้ from_service_account_info (สำหรับข้อมูลที่เป็น Dictionary)
            creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        else:
            # สำหรับรันในเครื่องตัวเอง
            creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
            
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(SHEET_NAME)

        data = worksheet.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        df.columns = ['lab_no', 'institute', 'province', 'regional', 'lab_results']
        
        # ลบช่องว่าง และกรองแถวที่ไม่ต้องการออกเพื่อให้ Dropdown สะอาด
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            
        invalid_vals = ['', 'nan', 'None', 'undefined', 'ไม่พบเขตสุขภาพ']
        df = df[~df['regional'].isin(invalid_vals)]
        df = df[~df['lab_results'].isin(invalid_vals)]

        df['lab_group'] = df['lab_results'].apply(clean_and_map_lab_results)
        df['risk_category'] = df['lab_results'].apply(map_risk_category)
        
        return df
    except Exception as e:
        st.error(f"❌ การเชื่อมต่อล้มเหลว: {e}")
        return pd.DataFrame()

def set_styles():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;600&display=swap');
        html, body, [class*="st-"] { font-family: 'Kanit', sans-serif; }
        .main { background-color: #FAFAFA; }
        .stMetric { background-color: #FFFFFF; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04); padding: 15px; min-height: 100px; }
        .stExpander, .stPlotlyChart { background-color: #FFFFFF; border-radius: 8px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); }
        h1, h2, h3 { color: #262626; font-weight: 600; }
                [data-testid="stMetric"] {
            background-color: #FFFFFF;
            border: 1px solid #F0F2F6;
            border-radius: 12px;
            padding: 15px 20px !important;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.02);
            transition: transform 0.2s ease;
        }
        [data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0, 0, 0, 0.05);
        }
        
        /* จัดการ Margin สำหรับอุปกรณ์พกพา */
        @media (max-width: 768px) {
            .main .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
        }
        </style>
        """, unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="NIPT Analytics Dashboard", layout="wide")
    set_styles()
    st.title("📊 NIPT-NGS Data Analysis Dashboard")
    st.markdown("---")
    
    df_full = load_data()
    if df_full.empty: return

    # --- 5. การสร้าง Filter Controls ---
    actual_regionals = df_full['regional'].unique().tolist()
    def get_regional_order(region_name):
        try: return REGIONAL_ORDER_1_13.index(str(region_name))
        except ValueError: return 99
    existing_regionals = sorted(actual_regionals, key=get_regional_order)
    
    col1, col2, col3, col4 = st.columns([1, 1, 1, 0.8]) 
    with col1: selected_regional = st.selectbox("เลือกเขตสุขภาพ (Regional)", ['ทั้งหมด'] + existing_regionals)

    df_filtered = df_full.copy()
    if selected_regional != 'ทั้งหมด':
        df_filtered = df_filtered[df_filtered['regional'] == selected_regional]

    with col2:
        provinces_in_region = ['ทั้งหมด'] + sorted(df_filtered['province'].unique().tolist())
        selected_province = st.selectbox("เลือกจังหวัด (Province)", provinces_in_region)
    if selected_province != 'ทั้งหมด':
        df_filtered = df_filtered[df_filtered['province'] == selected_province]
        
    with col3:
        all_risk_categories = ['ทั้งหมด'] + sorted(df_full['risk_category'].unique().tolist())
        selected_risk = st.selectbox("เลือกผลการตรวจหลัก", all_risk_categories)
    
    with col4:
        st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True) 
        show_detailed_results = st.toggle("แสดงผลแบบละเอียด", value=False)
        
    # --- 6. แก้ไขจุดนี้: ให้ Dropdown ผลตรวจหลักทำงานได้แม้จะเปิด Toggle ละเอียด ---
    if selected_risk != 'ทั้งหมด':
        df_filtered = df_filtered[df_filtered['risk_category'] == selected_risk]

    st.markdown("---")
    if df_filtered.empty:
        st.warning("🚨 ไม่พบข้อมูลที่ตรงตามเงื่อนไขตัวกรองที่เลือก.") 
        return 

    total_cases = len(df_filtered)
    st.subheader("ภาพรวมข้อมูล NIPT ตามตัวกรอง" + (" (ผลการตรวจละเอียด)" if show_detailed_results else ""))
    
    # --- 7.0 แสดง KPI: ปรับปรุงให้ครบ 100% ---
    df_kpi_count = df_filtered.groupby('risk_category').size().reset_index(name='จำนวนเคส')
    df_kpi_count.set_index('risk_category', inplace=True)
    
    # สลับลำดับให้ Low risk อยู่ก่อน High risk
    RISK_MAPPINGS = {
        'Low risk': ('🟢 Low risk', 'normal'),
        'High risk': ('🔴 High risk', 'inverse'),
        'Re-sampling': ('🟡 Re-sampling', 'off'),
        'Re-library': ('🔵 Re-library', 'off'),
        'No Call': ('⚫ No Call', 'off'),
        'Other': ('⚪ Other/อื่นๆ', 'off'),
    }

    cols_kpi = st.columns([1, 1, 1, 1, 1, 1, 1])
    with cols_kpi[0]:
        st.metric(label="✅ จำนวนการตรวจรวม", value=f"{total_cases:,} เคส", delta="Total", delta_color="off")
    
    for i, (category, (label, color)) in enumerate(RISK_MAPPINGS.items()):
        count = df_kpi_count.loc[category, 'จำนวนเคส'] if category in df_kpi_count.index else 0
        percent = (count / total_cases * 100) if total_cases > 0 else 0
        with cols_kpi[i+1]:
            st.metric(label=label, value=f"{count:,} เคส", delta=f"{percent:.2f}%", delta_color=color)

    st.markdown("<br>", unsafe_allow_html=True) 
    col_chart_1, col_chart_2 = st.columns(2)
    risk_colors = {'High risk':'#E54747', 'Low risk':'#33A02C', 'Re-sampling':'#FFBF00', 'Re-library':'#007bb6', 'No Call': '#606060', 'Other': '#AAAAAA'}
    
    # 7.1 กราฟวงกลม (ลบ undefined)
    # 7.1 กราฟวงกลมดีไซน์ Minimal พร้อมหลอดข้อมูลด้านข้าง
    with col_chart_1:
        st.subheader(f"สัดส่วนผลการตรวจ NIPT-NGS")
        
        # กรองข้อมูลกลุ่มหลัก
        valid_risks = ['Low risk', 'High risk', 'Re-sampling', 'Re-library', 'No Call']
        df_pie_data = df_filtered[df_filtered['risk_category'].isin(valid_risks)]
        
        # แบ่งเป็น 2 คอลัมน์ย่อย (ซ้าย: กราฟเต็มวง, ขวา: หลอดข้อมูล)
        inner_col1, inner_col2 = st.columns([1, 1.2])
        
        with inner_col1:
            # 1. กราฟวงกลมแบบเต็มวง (hole=0)
            fig_pie = px.pie(
                df_pie_data, names='risk_category', color='risk_category', 
                color_discrete_map=risk_colors, 
                hole=0 # <--- ปรับเป็น 0 เพื่อให้กราฟเต็มวง
            )
            # ปิดตัวเลขบนกราฟ และย้าย Legend ไปไว้ด้านบน
            fig_pie.update_traces(textinfo='none', hovertemplate="<b>%{label}</b><br>%{value} เคส")
            fig_pie.update_layout(
                legend=dict(orientation="h", yanchor="bottom", y=1.15, xanchor="center", x=0.5),
                margin=dict(t=0, b=0, l=0, r=0),
                height=280,
                showlegend=True
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with inner_col2:
            # 2. หลอดข้อมูลด้านข้าง (Progress Bars)
            st.markdown("<div style='padding-top: 15px;'></div>", unsafe_allow_html=True)
            for risk in valid_risks:
                count = len(df_filtered[df_filtered['risk_category'] == risk])
                percent = (count / total_cases * 100) if total_cases > 0 else 0
                color = risk_colors.get(risk, '#AAAAAA')
                
                # HTML สำหรับหลอดข้อมูล
                st.markdown(f"""
                    <div style="margin-bottom: 12px;">
                        <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 2px;">
                            <span style="font-weight: 500;">{risk}</span>
                            <span style="color: #666;">{count:,} ({percent:.1f}%)</span>
                        </div>
                        <div style="background-color: #f0f2f6; border-radius: 4px; height: 10px; width: 100%;">
                            <div style="background-color: {color}; height: 10px; width: {percent}%; border-radius: 4px;"></div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

    # 7.2 กราฟแท่ง (แยกแท่งเฉพาะเมื่อเลือกเขต)

    # 7.2 กราฟแท่ง (Bar Chart) - แก้ไข Error และลบชื่อแกน
    with col_chart_2:
        # กำหนดลำดับที่ถูกต้องสำหรับเขตสุขภาพ (1-13)
        correct_order = [f'เขตสุขภาพที่ {i}' for i in range(1, 14)] + ['ส่วนกลาง/อื่นๆ']
        
        # กรองข้อมูลให้สะอาด
        invalid_vals = ['', 'nan', 'None', 'undefined', 'ไม่พบเขตสุขภาพ']
        df_bar_clean = df_filtered[~df_filtered['regional'].isin(invalid_vals)]
        
        group_col = 'lab_group' if show_detailed_results else 'risk_category'

        if selected_regional != 'ทั้งหมด':
            st.subheader(f"แยกตามจังหวัด ในเขต {selected_regional}")
            df_bar_data = df_bar_clean[df_bar_clean['province'] != ''].groupby(['province', group_col]).size().reset_index(name='จำนวนเคส')
            
            fig_bar = px.bar(df_bar_data, x='province', y='จำนวนเคส', color=group_col, 
                             text='จำนวนเคส', color_discrete_map=risk_colors, barmode='group')
        else:
            st.subheader("แยกตามเขตสุขภาพทั้งหมด")
            df_bar_data = df_bar_clean.groupby('regional').size().reset_index(name='จำนวนเคส')
            
            # สร้างกราฟและกำหนดลำดับแกน X (category_orders)
            fig_bar = px.bar(df_bar_data, x='regional', y='จำนวนเคส', text='จำนวนเคส', 
                             color='จำนวนเคส', color_continuous_scale='Teal',
                             category_orders={'regional': correct_order}) # <--- สั่งให้เรียง 1-13 ที่ตรงนี้

        # ปรับแต่ง Layout และเอาคำว่า Regional / Province ออก
        fig_bar.update_layout(
            font_family="Kanit", 
            hovermode='x unified',
            margin=dict(t=20, b=20, l=0, r=0)
        )
        
        # ลบชื่อหัวข้อแกน X และ Y
        fig_bar.update_xaxes(title_text="") 
        fig_bar.update_yaxes(title_text="")
        
        st.plotly_chart(fig_bar, use_container_width=True)
    
    # --- 9. ตารางข้อมูล ---
    st.markdown("---")
    header_html = f"""<div style="background-color: #FFFFFF; border: 1px solid #F0F2F6; border-radius: 8px 8px 0 0; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
        <h3 style="font-size: 1.25rem; font-weight: 600; color: #262626; margin: 0;">ข้อมูลรายชื่อ ({len(df_filtered):,} รายการ)</h3>
    </div>"""
    st.markdown(header_html, unsafe_allow_html=True)

    df_display = df_filtered[['lab_no', 'institute', 'province', 'regional', 'lab_results', 'risk_category']].copy()
    def get_colored_result(row):
        emoji = {'High risk':'🔴', 'Low risk':'🟢', 'Re-sampling':'🟡', 'Re-library':'🔵', 'No Call':'⚫'}.get(row['risk_category'], '⚪')
        return f"{emoji} {row['lab_results']}"
            
    df_display['ผลการตรวจ'] = df_display.apply(get_colored_result, axis=1)
    df_display = df_display.drop(columns=['risk_category', 'lab_results']).rename(columns={'lab_no': 'เลขที่ใบส่งตรวจ', 'institute': 'สถานพยาบาล', 'province': 'จังหวัด', 'regional': 'เขตสุขภาพ'})
    
    df_display_final = df_display[['เลขที่ใบส่งตรวจ', 'สถานพยาบาล', 'จังหวัด', 'เขตสุขภาพ', 'ผลการตรวจ']].reset_index(drop=True)
    df_display_final.index += 1
    st.dataframe(df_display_final, use_container_width=True, height=400)

if __name__ == "__main__":

    main()


