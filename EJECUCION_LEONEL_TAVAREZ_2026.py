import streamlit as st
import pandas as pd
import plotly.express as px
import json
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard INFOTEP - Leonel Tavarez", layout="wide")

# --- CREDENCIALES DE GOOGLE DRIVE ---
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"

def get_drive_service():
    try:
        info_json = st.secrets["google_creds"]["json_data"]
        info = json.loads(info_json)
        # Corrección técnica para la llave privada
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(info)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error en credenciales: {e}")
        return None

def list_files_in_folder(empresa_name):
    try:
        service = get_drive_service()
        if not service: return None
        query = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items: return None
        f_id = items[0]['id']
        res = service.files().list(q=f"'{f_id}' in parents and trashed = false", fields="files(id, name, webViewLink, mimeType)").execute()
        return res.get('files', [])
    except: return []

# --- ESTILOS INFOTEP ---
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border-left: 5px solid #0056b3; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 4px 4px 0 0; padding: 10px; }
    .stTabs [aria-selected="true"] { background-color: #0056b3; color: white; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
    columnas_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in columnas_num:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    df['MES'] = df['FECHA_INICIO'].dt.month_name()
    return df

try:
    df_orig = load_data()
    st.sidebar.title("🛠️ Gestión INFOTEP")
    f_empresa = st.sidebar.multiselect("Empresa", options=sorted(df_orig["EMPRESA"].unique()))
    f_estado = st.sidebar.multiselect("Estado", options=df_orig["ESTADO"].unique(), default=df_orig["ESTADO"].unique())
    
    df = df_orig[df_orig["ESTADO"].isin(f_estado)]
    if f_empresa: df = df[df["EMPRESA"].isin(f_empresa)]

    tabs = st.tabs(["📊 Dashboard Ejecutivo", "📋 Tabla de Datos", "📂 Repositorio Drive"])

    with tabs[0]:
        st.title("Control de Ejecución 2026")
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Totales", f"{int(df['HORAS_EJECUTADAS'].sum()):,}")
        c2.metric("Acciones", f"{int(df['TOTAL_ACCIONES'].sum()):,}")
        c3.metric("Participantes", f"{int(df['PARTICIPANTES'].sum()):,}")
        
        col_a, col_b = st.columns(2)
        # Colores INFOTEP: Azul (#0056b3) y Dorado (#ffcc00)
        with col_a:
            fig1 = px.bar(df.groupby('EMPRESA')['HORAS_EJECUTADAS'].sum().reset_index(), x='EMPRESA', y='HORAS_EJECUTADAS', title="Horas por Empresa", color_discrete_sequence=['#0056b3'])
            st.plotly_chart(fig1, use_container_width=True)
        with col_b:
            fig2 = px.bar(df.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index(), x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], title="Distribución de Personal", color_discrete_map={'OPERARIOS':'#0056b3', 'MANDOS_MEDIOS':'#ffcc00', 'GERENTES':'#e63946'})
            st.plotly_chart(fig2, use_container_width=True)

    with tabs[1]:
        st.subheader("Registros Detallados")
        # BOTÓN DE DESCARGA EXCEL
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Datos')
        st.download_button(label="📥 Descargar Tabla en Excel", data=output.getvalue(), file_name="Reporte_Infotep.xlsx", mime="application/vnd.ms-excel")
        st.dataframe(df, use_container_width=True)

    with tabs[2]:
        st.subheader("Archivos en Drive")
        if f_empresa and len(f_empresa) == 1:
            emp = f_empresa[0]
            archivos = list_files_in_folder(emp)
            if archivos:
                for a in archivos:
                    col_n, col_b = st.columns([4, 1])
                    col_n.write(f"📄 {a['name']}")
                    col_b.link_button("Abrir", a['webViewLink'])
            else:
                st.warning(f"No hay carpeta para '{emp}' en 'EMPRESAS CAPACITACION 2026'.")
        else:
            st.info("Seleccione una sola empresa para ver sus documentos.")

except Exception as e:
    st.error(f"Error: {e}")
