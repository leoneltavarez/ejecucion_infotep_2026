import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- LIBRERÍAS ---
try:
    from fillpdf import fillpdfs
except ImportError:
    st.error("Error: Falta 'fillpdf'. Agrégalo a requirements.txt")

# --- IDENTIDAD INFOTEP ---
COLOR_AZUL = "#0056b3"
COLOR_AMARILLO = "#ffcc00"
COLOR_VERDE = "#28a745"
COLOR_ROJO = "#dc3545"

st.set_page_config(page_title="Gestión INFOTEP - Leonel Tavarez", layout="wide")

# --- CONFIGURACIÓN GOOGLE ---
# ID de la carpeta principal "EMPRESAS CAPACITACION 2026"
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"
PLANTILLA_PDF = 'PLANTILLA_FINAL.pdf'

def get_drive_service():
    try:
        info_json = st.secrets["google_creds"]["json_data"]
        info = json.loads(info_json)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(info)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error de credenciales: {e}")
        return None

def upload_to_drive(content_bytes, file_name, folder_id):
    """Subida con bypass de cuota 403"""
    service = get_drive_service()
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaIoBaseUpload(BytesIO(content_bytes), mimetype='application/pdf')
    
    # supportsAllDrives=True es vital para usar el espacio de la cuenta propietaria
    service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id',
        supportsAllDrives=True 
    ).execute()

def get_folder_id(empresa_name):
    service = get_drive_service()
    if not service: return None
    # Buscamos la carpeta de la empresa dentro de la carpeta principal
    query = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True).execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

def list_files_in_folder(empresa_name):
    try:
        service = get_drive_service()
        f_id = get_folder_id(empresa_name)
        if not f_id: return []
        res = service.files().list(
            q=f"'{f_id}' in parents and trashed = false", 
            fields="files(id, name, webViewLink)",
            supportsAllDrives=True
        ).execute()
        return res.get('files', [])
    except: return []

# --- CARGA DE DATOS (Tu Base de Datos de Drive) ---
@st.cache_data(ttl=0)
def load_data():
    # URL de tu CSV publicado o conectado
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # Limpieza básica
    df['EMPRESA'] = df['EMPRESA'].astype(str).str.strip()
    df['ESTADO'] = df['ESTADO'].astype(str).str.strip()
    
    # Fechas
    df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
    df['FECHA_TERMINO'] = pd.to_datetime(df['FECHA_TERMINO'], dayfirst=True, errors='coerce')
    
    # Números enteros
    cols_n = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for c in cols_n:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    return df

# --- LÓGICA DE LA APLICACIÓN ---
try:
    df_orig = load_data()
    st.sidebar.title("🛠️ Gestión INFOTEP")
    
    # --- 1. SECCIÓN DE CRONOGRAMAS ---
    st.sidebar.subheader("📄 Generar Cronogramas")
    emp_cron = st.sidebar.selectbox("Empresa para PDF", options=sorted(df_orig["EMPRESA"].unique()))
    
    if st.sidebar.button("🚀 Iniciar Generación Masiva"):
        # Lógica de tu laptop: filtrar acciones de la empresa
        df_emp = df_orig[df_orig['EMPRESA'] == emp_cron]
        acciones = df_emp['ACCION_FORMATIVA'].unique().tolist()
        
        if not acciones:
            st.sidebar.warning(f"No hay datos para {emp_cron}")
        else:
            f_id = get_folder_id(emp_cron)
            if f_id:
                # Paginación de 10 acciones (como tu script de laptop)
                lote_size = 10
                for i in range(0, len(acciones), lote_size):
                    lote = acciones[i:i+lote_size]
                    parte = (i // lote_size) + 1
                    
                    datos_pdf = {'txt_empresa': emp_cron, 'txt_regional': 'Cibao Norte'}
                    for idx, acc in enumerate(lote):
                        datos_pdf[f'accion_{idx+1}'] = acc
                    
                    temp_file = f"temp_{parte}.pdf"
                    fillpdfs.write_fillable_pdf(PLANTILLA_PDF, temp_file, datos_pdf)
                    
                    with open(temp_file, "rb") as f:
                        upload_to_drive(f.read(), f"Cronograma_{emp_cron}_P{parte}.pdf", f_id)
                    os.remove(temp_file)
                st.sidebar.success(f"✅ ¡Éxito! Archivos subidos a Drive.")
            else:
                st.sidebar.error("No se encontró la carpeta de la empresa en Drive.")

    st.sidebar.divider()

    # --- 2. FILTROS DE VISUALIZACIÓN ---
    st.sidebar.subheader("🔍 Filtros de Reporte")
    f_emp = st.sidebar.multiselect("Seleccionar Empresas", options=sorted(df_orig["EMPRESA"].unique()))
    f_est = st.sidebar.multiselect("Seleccionar Estados", options=sorted(df_orig["ESTADO"].unique()), default=df_orig["ESTADO"].unique())

    # Aplicar filtros
    df_v = df_orig[df_orig["ESTADO"].isin(f_est)]
    if f_emp:
        df_v = df_v[df_v["EMPRESA"].isin(f_emp)]

    # --- TABS ---
    t_dash, t_data, t_drive = st.tabs(["📊 Dashboard Ejecutivo", "📋 Tabla de Datos", "📂 Repositorio Drive"])

    with t_dash:
        st.title("Control de Ejecución 2026")
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Totales", f"{int(df_v['HORAS_EJECUTADAS'].sum()):,}")
        c2.metric("Acciones Formativas", f"{int(df_v['TOTAL_ACCIONES'].sum()):,}")
        c3.metric("Participantes", f"{int(df_v['PARTICIPANTES'].sum()):,}")
        
        st.divider()
        col_L, col_R = st.columns(2)
        with col_L:
            st.subheader("Alcance Operativo")
            df_g1 = df_v.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'], 
                          barmode='group', text_auto='d',
                          color_discrete_map={'HORAS_EJECUTADAS': COLOR_AZUL, 'PARTICIPANTES': COLOR_AMARILLO, 'TOTAL_ACCIONES': COLOR_VERDE})
            st.plotly_chart(fig1, use_container_width=True)
        with col_R:
            st.subheader("Niveles Jerárquicos")
            df_g2 = df_v.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], 
                          barmode='stack', text_auto='d',
                          color_discrete_map={'OPERARIOS': COLOR_AZUL, 'MANDOS_MEDIOS': COLOR_AMARILLO, 'GERENTES': COLOR_ROJO})
            st.plotly_chart(fig2, use_container_width=True)

    with t_data:
        st.subheader("Registros Base")
        # Botones descarga
        d1, d2 = st.columns(2)
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as w:
            df_v.to_excel(w, index=False)
        d1.download_button("📥 Bajar Excel", buf.getvalue(), "Reporte.xlsx")
        d2.download_button("📄 Bajar CSV", df_v.to_csv(index=False).encode('utf-8'), "Reporte.csv")
        
        # Tabla
        df_tab = df_v.copy()
        df_tab['FECHA_INICIO'] = df_tab['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        df_tab['FECHA_TERMINO'] = df_tab['FECHA_TERMINO'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_tab, use_container_width=True, hide_index=True)

    with t_drive:
        st.subheader("Repositorio Drive")
        if f_emp and len(f_emp) == 1:
            files = list_files_in_folder(f_emp[0])
            if files:
                for f in files:
                    col_txt, col_btn = st.columns([4, 1])
                    col_txt.write(f"📄 {f['name']}")
                    col_btn.link_button("Abrir", f['webViewLink'])
            else: st.warning("No hay archivos.")
        else: st.info("Filtra **una sola empresa** para ver sus archivos.")

except Exception as e:
    st.error(f"Error general: {e}")
