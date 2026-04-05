import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- LIBRERÍAS CRÍTICAS ---
try:
    from fillpdf import fillpdfs
except ImportError:
    st.error("Falta 'fillpdf' en requirements.txt")

# --- IDENTIDAD VISUAL INFOTEP ---
COLOR_AZUL = "#0056b3"
COLOR_AMARILLO = "#ffcc00"
COLOR_VERDE = "#28a745"
COLOR_ROJO = "#dc3545"

st.set_page_config(page_title="Gestión INFOTEP - Leonel Tavarez", layout="wide")

# --- CONFIGURACIÓN DRIVE ---
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
        st.error(f"Error de conexión: {e}")
        return None

def upload_to_drive(content_bytes, file_name, folder_id):
    """
    FIX CRÍTICO: Usa 'supportsAllDrives' y evita que el robot sea el 'owner'
    para saltar el error de quota 403.
    """
    service = get_drive_service()
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(BytesIO(content_bytes), mimetype='application/pdf', resumable=True)
    
    try:
        service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True  # Permite usar el espacio de la carpeta compartida
        ).execute()
    except Exception as e:
        st.error(f"Error al subir a Drive: {e}")

def get_folder_id(empresa_name):
    service = get_drive_service()
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

# --- CARGA DE DATOS (URL Directa de tu Drive) ---
@st.cache_data(ttl=60)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # Limpieza de textos y tipos
    df['EMPRESA'] = df['EMPRESA'].astype(str).str.strip()
    df['ESTADO'] = df['ESTADO'].astype(str).str.strip()
    
    # Asegurar que los números sean enteros (evita el .0 en los gráficos)
    cols_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in cols_num:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    return df

# --- INTERFAZ ---
try:
    df_orig = load_data()
    st.sidebar.title("🛠️ Gestión INFOTEP")
    
    # 1. GENERADOR DE CRONOGRAMAS (Tu lógica de laptop integrada)
    st.sidebar.subheader("📄 Generar Cronograma")
    emp_pdf = st.sidebar.selectbox("Seleccione Empresa", options=sorted(df_orig["EMPRESA"].unique()))
    
    if st.sidebar.button("🚀 Generar y Subir"):
        # Lógica exacta de tu script local: filtrar acciones de la empresa
        acciones = df_orig[df_orig['EMPRESA'] == emp_pdf]['ACCION_FORMATIVA'].unique().tolist()
        
        if not acciones:
            st.sidebar.warning("No se encontraron acciones formativas.")
        else:
            f_id = get_folder_id(emp_pdf)
            if f_id:
                # Lote de 10 como en tu script
                lote_size = 10
                for i in range(0, len(acciones), lote
