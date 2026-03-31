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
    .stTabs [aria-selected="true"] { background-color: #0056b3 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=0)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    if 'ESTADO' in df.columns:
        df['ESTADO'] = df['ESTADO'].astype(str).str.strip()
    
    # Procesamiento de fechas internas
    df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
    df['FECHA_TERMINO'] = pd.to_datetime(df['FECHA_TERMINO'], dayfirst=True, errors='coerce')
    
    columnas_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in columnas_num:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    return df

try:
    df_orig = load_data()
    st.sidebar.title("🛠️ Gestión INFOTEP")
    
    estados_disponibles = sorted([e for e in df_orig["ESTADO"].unique() if e != 'nan'])
    empresas_disponibles = sorted(df_orig["EMPRESA"].unique())
    
    f_empresa = st.sidebar.multiselect("Empresa", options=empresas_disponibles)
    f_estado = st.sidebar.multiselect("Estado", options=estados_disponibles, default=estados_disponibles)
    
    df = df_orig[df_orig["ESTADO"].isin(f_estado)]
    if f_empresa:
        df = df[df["EMPRESA"].isin(f_empresa)]

    tabs = st.tabs(["📊 Dashboard Ejecutivo", "📋 Tabla de Datos", "📂 Repositorio Drive"])

    with tabs[0]:
        st.title("Control de Ejecución 2026")
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Totales", f"{int(df['HORAS_EJECUTADAS'].sum()):,}")
        c2.metric("Acciones Formativas", f"{int(df['TOTAL_ACCIONES'].sum()):,}")
        c3.metric("Total Participantes", f"{int(df['PARTICIPANTES'].sum()):,}")
        
        st.divider()
        col_graf_1, col_graf_2 = st.columns(2)
        
        with col_graf_1:
            st.subheader("Ejecución: Horas, Part. y Acciones")
            df_graf1 = df.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
            fig1 = px.bar(
                df_graf1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'],
                barmode='group', text_auto='d', # 'd' quita el .0 en las barras
                color_discrete_map={'HORAS_EJECUTADAS': '#0056b3', 'PARTICIPANTES': '#ffcc00', 'TOTAL_ACCIONES': '#28a745'}
            )
            st.plotly_chart(fig1, use_container_width=True)

        with col_graf_2:
            st.subheader("Distribución por Nivel de Mando")
            df_graf2 = df.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(
                df_graf2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'],
                barmode='stack', text_auto='d',
                color_discrete_map={'OPERARIOS': '#0056b3', 'MANDOS_MEDIOS': '#ffcc00', 'GERENTES': '#17a2b8'}
            )
            st.plotly_chart(fig2, use_container_width=True)

    with tabs[1]:
        st.subheader("Registros Detallados")
        
        # --- LIMPIEZA VISUAL DE FECHAS PARA LA TABLA ---
        df_tabla = df.copy()
        # Formateamos las columnas de fecha a solo texto DD/MM/YYYY
        df_tabla['FECHA_INICIO'] = df_tabla['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        df_tabla['FECHA_TERMINO'] = df_tabla['FECHA_TERMINO'].dt.strftime('%d/%m/%Y')

        btn_c1, btn_c2 = st.columns(2)
        out_xl = BytesIO()
        with pd.ExcelWriter(out_xl, engine='xlsxwriter') as w: df.to_excel(w, index=False)
        btn_c1.download_button("📥 Descargar Excel", out_xl.getvalue(), "Reporte.xlsx", "application/vnd.ms-excel")
        btn_c2.download_button("📄 Descargar CSV", df.to_csv(index=False).encode('utf-8'), "Reporte.csv", "text/csv")
        
        # Mostramos la tabla limpia y habilitamos selección para copiar
        st.dataframe(df_tabla, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Archivos en Drive")
        if f_empresa and len(f_empresa) == 1:
            archivos = list_files_in_folder(f_empresa[0])
            if archivos:
                for a in archivos:
                    cn, cb = st.columns([4, 1])
                    cn.write(f"📄 {a['name']}")
                    cb.link_button("Abrir", a['webViewLink'])
            else: st.warning("No se encontró la carpeta en Drive.")
        else: st.info("Seleccione una sola empresa.")

except Exception as e: st.error(f"Error: {e}")
