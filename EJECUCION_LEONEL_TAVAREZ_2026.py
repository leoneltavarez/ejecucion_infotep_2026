import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Intentar cargar fillpdf
try:
    from fillpdf import fillpdfs
except ImportError:
    st.error("Falta la librería fillpdf. Agrégala a requirements.txt")

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Dashboard INFOTEP - Leonel Tavarez", layout="wide")
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"
PLANTILLA_PDF = 'PLANTILLA_FINAL.pdf'

# --- CONEXIÓN GOOGLE DRIVE ---
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

def get_folder_id(empresa_name):
    service = get_drive_service()
    if not service: return None
    query = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

def upload_to_drive(content_bytes, file_name, folder_id):
    service = get_drive_service()
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaIoBaseUpload(BytesIO(content_bytes), mimetype='application/pdf')
    
    # supportsAllDrives=True soluciona el error de "Storage Quota"
    service.files().create(
        body=file_metadata, 
        media_body=media, 
        fields='id',
        supportsAllDrives=True 
    ).execute()

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

# --- CARGA DE DATOS ---
@st.cache_data(ttl=0)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    if 'ESTADO' in df.columns:
        df['ESTADO'] = df['ESTADO'].astype(str).str.strip()
    
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
    
    # --- GENERADOR DE CRONOGRAMAS (8 POR HOJA) ---
    st.sidebar.subheader("📄 Generador de Cronogramas")
    empresa_cronograma = st.sidebar.selectbox("Empresa para PDF", options=sorted(df_orig["EMPRESA"].unique()))
    
    if st.sidebar.button("🚀 Generar y Subir a Drive"):
        # Filtro estricto: Solo Cerrados
        df_cerrados = df_orig[(df_orig["EMPRESA"] == empresa_cronograma) & (df_orig["ESTADO"] == "Cerrado")]
        acciones = df_cerrados['ACCION_FORMATIVA'].tolist()
        
        if not acciones:
            st.sidebar.warning(f"No hay cursos 'Cerrados' para {empresa_cronograma}")
        else:
            f_id = get_folder_id(empresa_cronograma)
            if not f_id:
                st.sidebar.error("No se encontró la carpeta en Drive.")
            else:
                lote_size = 8
                for i in range(0, len(acciones), lote_size):
                    lote_actual = acciones[i:i + lote_size]
                    parte = (i // lote_size) + 1
                    datos_pdf = {'txt_empresa': empresa_cronograma, 'txt_regional': 'Cibao Norte'}
                    for idx, act in enumerate(lote_actual):
                        datos_pdf[f'accion_{idx+1}'] = act
                    
                    temp_name = f"temp_{parte}.pdf"
                    fillpdfs.write_fillable_pdf(PLANTILLA_PDF, temp_name, datos_pdf)
                    with open(temp_name, "rb") as f:
                        upload_to_drive(f.read(), f"Cronograma_{empresa_cronograma}_P{parte}.pdf", f_id)
                    os.remove(temp_name)
                st.sidebar.success(f"✅ ¡Éxito! Cronogramas en Drive.")

    # --- FILTROS DE VISTA ---
    f_empresa = st.sidebar.multiselect("Filtrar Empresa", options=sorted(df_orig["EMPRESA"].unique()))
    f_estado = st.sidebar.multiselect("Filtrar Estado", options=sorted(df_orig["ESTADO"].unique()), default=df_orig["ESTADO"].unique())
    
    df = df_orig[df_orig["ESTADO"].isin(f_estado)]
    if f_empresa: df = df[df["EMPRESA"].isin(f_empresa)]

    tabs = st.tabs(["📊 Dashboard", "📋 Tabla de Datos", "📂 Repositorio Drive"])

    with tabs[0]:
        st.title("Control de Ejecución 2026")
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Totales", f"{int(df['HORAS_EJECUTADAS'].sum()):,}")
        c2.metric("Acciones Formativas", f"{int(df['TOTAL_ACCIONES'].sum()):,}")
        c3.metric("Total Participantes", f"{int(df['PARTICIPANTES'].sum()):,}")
        
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            df_g1 = df.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'], 
                          barmode='group', text_auto='d', # 'd' para enteros
                          color_discrete_map={'HORAS_EJECUTADAS': '#0056b3', 'PARTICIPANTES': '#ffcc00', 'TOTAL_ACCIONES': '#28a745'})
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            df_g2 = df.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], 
                          barmode='stack', text_auto='d',
                          color_discrete_map={'OPERARIOS': '#0056b3', 'MANDOS_MEDIOS': '#ffcc00', 'GERENTES': '#17a2b8'})
            st.plotly_chart(fig2, use_container_width=True)

    with tabs[1]:
        st.subheader("Registros Detallados")
        # Botones de descarga
        d1, d2 = st.columns(2)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Data')
        d1.download_button("📥 Descargar Excel", output.getvalue(), "Reporte.xlsx", "application/vnd.ms-excel")
        d2.download_button("📄 Descargar CSV", df.to_csv(index=False).encode('utf-8'), "Reporte.csv", "text/csv")
        
        df_v = df.copy()
        df_v['FECHA_INICIO'] = df_v['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        df_v['FECHA_TERMINO'] = df_v['FECHA_TERMINO'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_v, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Archivos en Drive")
        if f_empresa and len(f_empresa) == 1:
            archivos = list_files_in_folder(f_empresa[0])
            if archivos:
                for a in archivos:
                    cn, cb = st.columns([4, 1])
                    cn.write(f"📄 {a['name']}")
                    cb.link_button("Abrir", a['webViewLink'])
            else: st.warning("Carpeta vacía.")
        else: st.info("Filtra una sola empresa para ver sus archivos.")

except Exception as e: st.error(f"Error general: {e}")
