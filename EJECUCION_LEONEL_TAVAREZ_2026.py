import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# IMPORTANTE: Debes instalar fillpdf (pip install fillpdf)
# Nota: fillpdf requiere tener instalado pdftk en el servidor si se usa de forma avanzada, 
# pero para llenar campos básicos suele funcionar bien.
try:
    from fillpdf import fillpdfs
except ImportError:
    st.error("Falta la librería fillpdf. Agrégala a requirements.txt")

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Dashboard INFOTEP - Leonel Tavarez", layout="wide")
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"
PLANTILLA_PDF = 'PLANTILLA_FINAL.pdf' # Asegúrate de que este archivo esté en tu GitHub

# --- SERVICIOS DE GOOGLE ---
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
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

def list_files_in_folder(empresa_name):
    try:
        service = get_drive_service()
        f_id = get_folder_id(empresa_name)
        if not f_id: return []
        res = service.files().list(q=f"'{f_id}' in parents and trashed = false", fields="files(id, name, webViewLink)").execute()
        return res.get('files', [])
    except: return []

# --- ESTILOS ---
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
    
    # --- MOTOR DE CRONOGRAMAS EN SIDEBAR ---
    st.sidebar.subheader("📄 Generador de Cronogramas")
    empresa_cronograma = st.sidebar.selectbox("Seleccione Empresa", options=sorted(df_orig["EMPRESA"].unique()))
    
    if st.sidebar.button("🚀 Generar y Subir a Drive"):
        # Filtro: Solo estado "Cerrado" para la empresa elegida
        df_cerrados = df_orig[(df_orig["EMPRESA"] == empresa_cronograma) & (df_orig["ESTADO"] == "Cerrado")]
        acciones = df_cerrados['ACCION_FORMATIVA'].tolist()
        
        if not acciones:
            st.sidebar.warning(f"No hay acciones 'Cerradas' para {empresa_cronograma}")
        else:
            folder_id = get_folder_id(empresa_cronograma)
            if not folder_id:
                st.sidebar.error("No se encontró carpeta en Drive.")
            else:
                # Lógica de Paginación (Grupos de 8)
                lote_size = 8
                for i in range(0, len(acciones), lote_size):
                    lote_actual = acciones[i:i + lote_size]
                    parte = (i // lote_size) + 1
                    
                    datos_pdf = {'txt_empresa': empresa_cronograma, 'txt_regional': 'Cibao Norte'}
                    for idx, act in enumerate(lote_actual):
                        datos_pdf[f'accion_{idx+1}'] = act
                    
                    # Generar PDF temporal
                    temp_out = f"temp_{parte}.pdf"
                    fillpdfs.write_fillable_pdf(PLANTILLA_PDF, temp_out, datos_pdf)
                    
                    with open(temp_out, "rb") as f:
                        file_bytes = f.read()
                        nombre_final = f"Cronograma_{empresa_cronograma}_Parte_{parte}.pdf"
                        upload_to_drive(file_bytes, nombre_final, folder_id)
                    
                    os.remove(temp_out) # Limpiar temporal
                
                st.sidebar.success(f"✅ Se enviaron {((len(acciones)-1)//8)+1} archivos a Drive.")

    # --- RESTO DEL DASHBOARD ---
    # ... (Se mantiene igual que el código anterior)
    estados_disponibles = sorted([e for e in df_orig["ESTADO"].unique() if e != 'nan'])
    f_empresa = st.sidebar.multiselect("Filtro Vista: Empresa", options=sorted(df_orig["EMPRESA"].unique()))
    f_estado = st.sidebar.multiselect("Filtro Vista: Estado", options=estados_disponibles, default=estados_disponibles)
    
    df = df_orig[df_orig["ESTADO"].isin(f_estado)]
    if f_empresa: df = df[df["EMPRESA"].isin(f_empresa)]

    tabs = st.tabs(["📊 Dashboard Ejecutivo", "📋 Tabla de Datos", "📂 Repositorio Drive"])

    with tabs[0]:
        st.title("Control de Ejecución 2026")
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Totales", f"{int(df['HORAS_EJECUTADAS'].sum()):,}")
        c2.metric("Acciones Formativas", f"{int(df['TOTAL_ACCIONES'].sum()):,}")
        c3.metric("Total Participantes", f"{int(df['PARTICIPANTES'].sum()):,}")
        
        st.divider()
        col_1, col_2 = st.columns(2)
        with col_1:
            df_g1 = df.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'],
                          barmode='group', text_auto='d',
                          color_discrete_map={'HORAS_EJECUTADAS': '#0056b3', 'PARTICIPANTES': '#ffcc00', 'TOTAL_ACCIONES': '#28a745'})
            st.plotly_chart(fig1, use_container_width=True)
        with col_2:
            df_g2 = df.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'],
                          barmode='stack', text_auto='d',
                          color_discrete_map={'OPERARIOS': '#0056b3', 'MANDOS_MEDIOS': '#ffcc00', 'GERENTES': '#17a2b8'})
            st.plotly_chart(fig2, use_container_width=True)

    with tabs[1]:
        st.subheader("Registros Detallados")
        df_t = df.copy()
        df_t['FECHA_INICIO'] = df_t['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        df_t['FECHA_TERMINO'] = df_t['FECHA_TERMINO'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_t, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Archivos en Drive")
        if f_empresa and len(f_empresa) == 1:
            archivos = list_files_in_folder(f_empresa[0])
            if archivos:
                for a in archivos:
                    cn, cb = st.columns([4, 1])
                    cn.write(f"📄 {a['name']}")
                    cb.link_button("Abrir", a['webViewLink'])
            else: st.warning("Carpeta vacía o no encontrada.")
        else: st.info("Seleccione una sola empresa en el filtro de la izquierda.")

except Exception as e: st.error(f"Error: {e}")
