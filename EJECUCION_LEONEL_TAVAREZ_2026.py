import streamlit as st
import pandas as pd
import plotly.express as px
import json
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard INFOTEP - Leonel Tavarez", layout="wide")

# --- CREDENCIALES DE GOOGLE DRIVE (ID CARPETA CAPACITACION 2026) ---
# Este es el ID que me pasaste de tu carpeta "EMPRESAS CAPACITACION 2026"
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"

def get_drive_service():
    try:
        # Lee el JSON desde la variable json_data en los Secrets de Streamlit
        info_json = st.secrets["google_creds"]["json_data"]
        info = json.loads(info_json)
        creds = service_account.Credentials.from_service_account_info(info)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error al cargar las credenciales de Google: {e}")
        return None

def list_files_in_folder(empresa_name):
    try:
        service = get_drive_service()
        if not service:
            return None
            
        # 1. Buscar la subcarpeta con el nombre exacto de la empresa dentro de la carpeta 2026
        query_folder = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query_folder, fields="files(id, name)").execute()
        items = results.get('files', [])
        
        if not items:
            return None
        
        folder_id = items[0]['id']
        # 2. Listar todos los archivos dentro de esa subcarpeta encontrada
        query_files = f"'{folder_id}' in parents and trashed = false"
        results_files = service.files().list(q=query_files, fields="files(id, name, webViewLink, mimeType)").execute()
        return results_files.get('files', [])
    except Exception as e:
        st.error(f"Error de conexión con Drive: {e}")
        return []

# --- ESTILOS PERSONALIZADOS ---
st.markdown("""
    <style>
    .stMetric { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #0056b3; }
    .block-container { padding-top: 2rem; }
    [data-testid="stMetricValue"] { font-size: 28px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    # Tu enlace de Google Sheets
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
    df = df.sort_values(by='FECHA_INICIO', ascending=True)
    
    # Limpieza de datos numéricos
    columnas_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in columnas_num:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    df['MES'] = df['FECHA_INICIO'].dt.month_name()
    return df

# --- LÓGICA PRINCIPAL ---
try:
    df_original = load_data()
    
    # --- FILTROS EN SIDEBAR ---
    st.sidebar.header("🛠️ Filtros de Gestión")
    filtro_estado = st.sidebar.multiselect("Estado del Programa", options=df_original["ESTADO"].unique(), default=df_original["ESTADO"].unique())
    filtro_empresa = st.sidebar.multiselect("Seleccionar Empresa", options=sorted(df_original["EMPRESA"].unique()))
    filtro_mes = st.sidebar.multiselect("Mes", options=df_original["MES"].unique())

    # Aplicar Filtros
    df = df_original[df_original["ESTADO"].isin(filtro_estado)]
    if filtro_empresa:
        df = df[df["EMPRESA"].isin(filtro_empresa)]
    if filtro_mes:
        df = df[df["MES"].isin(filtro_mes)]

    # --- NAVEGACIÓN POR PESTAÑAS (TABS) ---
    tabs = st.tabs(["📊 Dashboard Ejecutivo", "📋 Tabla de Datos", "📂 Repositorio Drive"])

    with tabs[0]:
        st.title("Control de Ejecución INFOTEP 2026")
        
        # Métricas principales
        m1, m2, m3 = st.columns(3)
        m1.metric("Horas Ejecutadas", f"{int(df['HORAS_EJECUTADAS'].sum()):,}")
        m2.metric("Acciones Totales", f"{int(df['TOTAL_ACCIONES'].sum()):,}")
        m3.metric("Total Participantes", f"{int(df['PARTICIPANTES'].sum()):,}")
        
        st.divider()
        
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("Esfuerzo por Empresa (Horas)")
            df_bar = df.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES']].sum().reset_index()
            fig1 = px.bar(df_bar, x='EMPRESA', y='HORAS_EJECUTADAS', text_auto=True, color_discrete_sequence=['#0056b3'])
            st.plotly_chart(fig1, use_container_width=True)
            
        with col_chart2:
            st.subheader("Distribución de Mandos")
            df_pie = df.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_pie, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], barmode='relative', text_auto=True)
            st.plotly_chart(fig2, use_container_width=True)

    with tabs[1]:
        st.subheader("Detalle de Registros")
        st.dataframe(df, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("📂 Archivos en la Nube")
        st.write("Esta sección conecta directamente con tu carpeta de Drive.")
        
        # Regla: Solo mostrar archivos si se selecciona UNA sola empresa
        if filtro_empresa and len(filtro_empresa) == 1:
            empresa_seleccionada = filtro_empresa[0]
            st.success(f"Explorando documentos para: **{empresa_seleccionada}**")
            
            with st.spinner("Accediendo a Google Drive..."):
                archivos = list_files_in_folder(empresa_seleccionada)
            
            if archivos:
                for arc in archivos:
                    col_icon, col_name, col_btn = st.columns([0.5, 4, 1.5])
                    # Icono según tipo de archivo
                    ext = "📄" if "pdf" in arc['mimeType'] else "📊"
                    col_icon.write(ext)
                    col_name.write(arc['name'])
                    col_btn.link_button("Ver Archivo", arc['webViewLink'])
            else:
                st.warning(f"No se encontró una carpeta llamada '{empresa_seleccionada}' dentro de 'EMPRESAS CAPACITACION 2026'.")
        else:
            st.info("💡 **Consejo:** Para ver los archivos (PDF/Excel), selecciona **una sola empresa** en el panel de la izquierda.")

except Exception as e:
    st.error(f"Hubo un problema al cargar el Dashboard: {e}")
