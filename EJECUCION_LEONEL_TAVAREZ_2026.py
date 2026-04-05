import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- LIBRERÍAS DE PDF ---
try:
    from fillpdf import fillpdfs
except ImportError:
    st.error("Por favor, añade 'fillpdf' a tu archivo requirements.txt")

# --- IDENTIDAD VISUAL INFOTEP ---
COLOR_AZUL = "#0056b3"
COLOR_AMARILLO = "#ffcc00"
COLOR_VERDE = "#28a745"
COLOR_ROJO = "#dc3545"

st.set_page_config(page_title="Dashboard INFOTEP - Leonel Tavarez", layout="wide")

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
    """Subida forzada para evitar Error 403 de cuota"""
    service = get_drive_service()
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaIoBaseUpload(BytesIO(content_bytes), mimetype='application/pdf', resumable=True)
    try:
        service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
    except Exception as e:
        st.error(f"Error al subir a Drive: {e}")

def get_folder_id(empresa_name):
    service = get_drive_service()
    if not service: return None
    query = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True).execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

# --- PROCESAMIENTO DE DATOS ---
@st.cache_data(ttl=60)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df['EMPRESA'] = df['EMPRESA'].astype(str).str.strip()
    df['ESTADO'] = df['ESTADO'].astype(str).str.strip()
    
    # Conversión limpia a números para los gráficos
    columnas_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in columnas_num:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    return df

# --- INTERFAZ PRINCIPAL ---
try:
    df_orig = load_data()
    st.sidebar.title("🛠️ Panel de Control")
    
    # 1. Generador de Cronogramas (Lógica de tu laptop integrada)
    st.sidebar.subheader("📄 Generar Cronograma")
    emp_pdf = st.sidebar.selectbox("Empresa para PDF", options=sorted(df_orig["EMPRESA"].unique()))
    
    if st.sidebar.button("🚀 Generar y Subir a Drive"):
        # Filtrar exactamente como en tu script de laptop
        acciones = df_orig[df_orig['EMPRESA'] == emp_pdf]['ACCION_FORMATIVA'].unique().tolist()
        
        if not acciones:
            st.sidebar.warning(f"No hay acciones formativas para {emp_pdf}")
        else:
            f_id = get_folder_id(emp_pdf)
            if f_id:
                # Lotes de 10 (según tu plantilla)
                lote_size = 10
                for i in range(0, len(acciones), lote_size):
                    lote = acciones[i:i+lote_size]
                    p = (i // lote_size) + 1
                    datos_pdf = {'txt_empresa': emp_pdf, 'txt_regional': 'Cibao Norte'}
                    for idx, acc in enumerate(lote):
                        datos_pdf[f'accion_{idx+1}'] = acc
                    
                    nombre_temp = f"temp_{p}.pdf"
                    fillpdfs.write_fillable_pdf(PLANTILLA_PDF, nombre_temp, datos_pdf)
                    
                    with open(nombre_temp, "rb") as f:
                        upload_to_drive(f.read(), f"Cronograma_{emp_pdf}_P{p}.pdf", f_id)
                    os.remove(nombre_temp)
                st.sidebar.success(f"✅ Cronogramas subidos para {emp_pdf}")
            else:
                st.sidebar.error("No se encontró la carpeta en Drive.")

    st.sidebar.divider()
    
    # 2. Filtros de Gráficos
    st.sidebar.subheader("🔍 Filtros de Visualización")
    f_empresa = st.sidebar.multiselect("Empresas", options=sorted(df_orig["EMPRESA"].unique()))
    f_estado = st.sidebar.multiselect("Estados", options=sorted(df_orig["ESTADO"].unique()), default=df_orig["ESTADO"].unique())
    
    df_filtrado = df_orig[df_orig["ESTADO"].isin(f_estado)]
    if f_empresa:
        df_filtrado = df_filtrado[df_filtrado["EMPRESA"].isin(f_empresa)]

    # --- PESTAÑAS ---
    t1, t2 = st.tabs(["📊 Dashboard Ejecutivo", "📋 Tabla de Datos"])

    with t1:
        st.title("Control de Ejecución 2026")
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Totales", f"{int(df_filtrado['HORAS_EJECUTADAS'].sum()):,}")
        c2.metric("Acciones Formativas", f"{int(df_filtrado['TOTAL_ACCIONES'].sum()):,}")
        c3.metric("Participantes", f"{int(df_filtrado['PARTICIPANTES'].sum()):,}")
        
        st.divider()
        col_izq, col_der = st.columns(2)
        
        with col_izq:
            st.subheader("Alcance Operativo")
            df_g1 = df_filtrado.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'], 
                          barmode='group', text_auto='d',
                          color_discrete_map={'HORAS_EJECUTADAS': COLOR_AZUL, 'PARTICIPANTES': COLOR_AMARILLO, 'TOTAL_ACCIONES': COLOR_VERDE})
            st.plotly_chart(fig1, use_container_width=True)

        with col_der:
            st.subheader("Niveles Jerárquicos")
            df_g2 = df_filtrado.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], 
                          barmode='stack', text_auto='d',
                          color_discrete_map={'OPERARIOS': COLOR_AZUL, 'MANDOS_MEDIOS': COLOR_AMARILLO, 'GERENTES': COLOR_ROJO})
            st.plotly_chart(fig2, use_container_width=True)

    with t2:
        st.subheader("Registros Detallados")
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Error general: {e}")
