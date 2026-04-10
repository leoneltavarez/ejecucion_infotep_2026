import streamlit as st
import pandas as pd
import plotly.express as px
import json
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- IDENTIDAD VISUAL INFOTEP ---
COLOR_AZUL = "#0056b3"
COLOR_AMARILLO = "#ffcc00"
COLOR_VERDE = "#28a745"
COLOR_ROJO = "#dc3545"

st.set_page_config(page_title="Dashboard INFOTEP - Leonel Tavarez", layout="wide")

# --- ESTILO PERSONALIZADO ---
st.markdown(f"""
    <style>
    .metric-container {{
        background-color: #f8f9fa;
        border-top: 5px solid {COLOR_AZUL};
        border-radius: 10px;
        padding: 20px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        text-align: center;
    }}
    .metric-title {{ color: #555; font-size: 1.2rem; margin-bottom: 10px; font-weight: bold; }}
    .metric-value {{ color: {COLOR_AZUL}; font-size: 2.5rem; font-weight: bold; }}
    </style>
""", unsafe_allow_html=True)

# --- CONFIGURACIÓN DRIVE (SE MANTIENE IGUAL) ---
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"

def get_drive_service():
    try:
        info_json = st.secrets["google_creds"]["json_data"]
        info = json.loads(info_json)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive"])
        return build('drive', 'v3', credentials=creds)
    except: return None

def get_folder_id(empresa_name):
    service = get_drive_service()
    if not service: return None
    query = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True).execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

def list_files_in_folder(empresa_name):
    try:
        service = get_drive_service()
        f_id = get_folder_id(empresa_name)
        if not f_id: return []
        res = service.files().list(q=f"'{f_id}' in parents and trashed = false", fields="files(id, name, webViewLink)", supportsAllDrives=True).execute()
        return res.get('files', [])
    except: return []

# --- CARGA DE DATOS Y MEJORAS DE ORDENAMIENTO ---
@st.cache_data(ttl=0) 
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # Limpieza de textos
    for col in ['EMPRESA', 'ESTADO', 'ACCION_FORMATIVA']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    
    # --- MEJORA 1: ORDENAR POR FECHA ---
    if 'FECHA_INICIO' in df.columns:
        df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
        df = df.sort_values(by='FECHA_INICIO', ascending=True)

    # Conversión numérica
    columnas_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in columnas_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    return df

# --- INTERFAZ ---
try:
    df_orig = load_data()
    st.sidebar.title("🛠️ Panel de Control")
    
    if st.sidebar.button("🔄 Sincronizar Base de Datos"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.subheader("🔍 Filtros de Reporte")
    f_empresa = st.sidebar.multiselect("Empresa(s)", options=sorted(df_orig["EMPRESA"].unique()))
    f_estado = st.sidebar.multiselect("Estado(s)", options=sorted(df_orig["ESTADO"].unique()), default=df_orig["ESTADO"].unique())
    
    # --- MEJORA 3: FILTRO DE ACCIONES FORMATIVAS ---
    df_v = df_orig[df_orig["ESTADO"].isin(f_estado)]
    if f_empresa:
        df_v = df_v[df_v["EMPRESA"].isin(f_empresa)]
    
    lista_acciones = sorted(df_v["ACCION_FORMATIVA"].unique())
    f_accion = st.sidebar.multiselect("Acción Formativa", options=lista_acciones)

    if f_accion:
        df_v = df_v[df_v["ACCION_FORMATIVA"].isin(f_accion)]

    t_dash, t_data, t_drive = st.tabs(["📊 Dashboard Ejecutivo", "📋 Tabla de Datos", "📂 Repositorio Drive"])

    with t_dash:
        st.title("Control de Ejecución 2026")
        
        # --- MEJORA 2: CONTEO DE CURSOS ESPECÍFICOS ---
        total_cursos_filtrados = len(df_v)
        h_total = f"{int(df_v['HORAS_EJECUTADAS'].sum()):,}"
        p_total = f"{int(df_v['PARTICIPANTES'].sum()):,}"

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="metric-container"><div class="metric-title">Horas Ejecutadas</div><div class="metric-value">{h_total}</div></div>', unsafe_allow_html=True)
        with c2:
            label_accion = "Cursos Seleccionados" if f_accion else "Total Acciones"
            st.markdown(f'<div class="metric-container"><div class="metric-title">{label_accion}</div><div class="metric-value">{total_cursos_filtrados}</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="metric-container"><div class="metric-title">Participantes</div><div class="metric-value">{p_total}</div></div>', unsafe_allow_html=True)
        
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Alcance Operativo")
            df_g1 = df_v.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES'], barmode='group', text_auto='d',
                          color_discrete_map={'HORAS_EJECUTADAS': COLOR_AZUL, 'PARTICIPANTES': COLOR_AMARILLO})
            st.plotly_chart(fig1, use_container_width=True)
            
        with col2:
            # --- MEJORA 4: GRÁFICO DE JERARQUÍA FILTRABLE POR ACCIÓN ---
            st.subheader("Niveles Jerárquicos por Selección")
            df_g2 = df_v.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], barmode='stack', text_auto='d',
                          color_discrete_map={'OPERARIOS': COLOR_AZUL, 'MANDOS_MEDIOS': COLOR_AMARILLO, 'GERENTES': COLOR_ROJO})
            st.plotly_chart(fig2, use_container_width=True)

    with t_data:
        st.subheader("📋 Detalle de Acciones (Orden Cronológico)")
        
        # Botones de descarga (Se mantienen como pediste)
        d_c1, d_c2 = st.columns(2)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_v.to_excel(writer, index=False, sheet_name='Reporte')
        d_c1.download_button("📥 Descargar Excel", output.getvalue(), "Reporte_INFOTEP.xlsx")
        d_c2.download_button("📄 Descargar CSV", df_v.to_csv(index=False).encode('utf-8'), "Reporte_INFOTEP.csv")
        
        st.divider()
        # Mostrar tabla ordenada
        st.dataframe(df_v, use_container_width=True, hide_index=True)

    with t_drive:
        st.subheader("Repositorio de Documentos")
        if f_empresa and len(f_empresa) == 1:
            archivos = list_files_in_folder(f_empresa[0])
            if archivos:
                for a in archivos:
                    col_f, col_l = st.columns([4, 1])
                    col_f.write(f"📄 {a['name']}")
                    col_l.link_button("Abrir", a['webViewLink'])
            else:
                st.warning("No hay archivos para esta empresa.")
        else:
            st.info("Selecciona una sola empresa para explorar su Drive.")

except Exception as e:
    st.error(f"Error técnico: {e}")
