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
    st.error("Falta la librería fillpdf en requirements.txt")

# --- CONFIGURACIÓN VISUAL INFOTEP ---
COLOR_AZUL = "#0056b3"
COLOR_AMARILLO = "#ffcc00"
COLOR_VERDE = "#28a745"
COLOR_ROJO = "#dc3545"

st.set_page_config(page_title="Gestión INFOTEP - Leonel Tavarez", layout="wide")

# --- CONSTANTES ---
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
    service = get_drive_service()
    # Metadatos clave: forzamos a que NO use la cuota del robot
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(BytesIO(content_bytes), mimetype='application/pdf')
    
    # supportsAllDrives permite trabajar en carpetas de terceros/institucionales
    service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id',
        supportsAllDrives=True 
    ).execute()

def get_folder_id(empresa_name):
    service = get_drive_service()
    query = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True).execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

@st.cache_data(ttl=0)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # Limpieza de datos
    df['ESTADO'] = df['ESTADO'].astype(str).str.strip()
    df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
    df['FECHA_TERMINO'] = pd.to_datetime(df['FECHA_TERMINO'], dayfirst=True, errors='coerce')
    
    # Conversión a enteros para evitar el ".0" en gráficos
    cols_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in cols_num:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    return df

try:
    df_orig = load_data()
    st.sidebar.title("🛠️ Gestión INFOTEP")
    
    # --- CRONOGRAMAS ---
    st.sidebar.subheader("📄 Generador de Cronogramas")
    emp_pdf = st.sidebar.selectbox("Seleccione Empresa", options=sorted(df_orig["EMPRESA"].unique()))
    
    if st.sidebar.button("🚀 Generar y Subir a Drive"):
        df_cerrados = df_orig[(df_orig["EMPRESA"] == emp_pdf) & (df_orig["ESTADO"] == "Cerrado")]
        acciones = df_cerrados['ACCION_FORMATIVA'].tolist()
        
        if not acciones:
            st.sidebar.warning(f"No hay cursos 'Cerrados' para {emp_pdf}")
        else:
            f_id = get_folder_id(emp_pdf)
            if not f_id:
                st.sidebar.error("Carpeta no encontrada en Drive.")
            else:
                # Paginación de 8
                lote_size = 8
                for i in range(0, len(acciones), lote_size):
                    lote = acciones[i:i+lote_size]
                    p = (i // lote_size) + 1
                    datos = {'txt_empresa': emp_pdf, 'txt_regional': 'Cibao Norte'}
                    for idx, act in enumerate(lote):
                        datos[f'accion_{idx+1}'] = act
                    
                    t_name = f"temp_{p}.pdf"
                    fillpdfs.write_fillable_pdf(PLANTILLA_PDF, t_name, datos)
                    with open(t_name, "rb") as f:
                        upload_to_drive(f.read(), f"Cronograma_{emp_pdf}_P{p}.pdf", f_id)
                    os.remove(t_name)
                st.sidebar.success("✅ ¡Cronogramas subidos!")

    # --- DASHBOARD ---
    f_emp = st.sidebar.multiselect("Filtrar Empresa", options=sorted(df_orig["EMPRESA"].unique()))
    df = df_orig.copy()
    if f_emp:
        df = df[df["EMPRESA"].isin(f_emp)]

    t1, t2 = st.tabs(["📊 Dashboard", "📋 Datos"])

    with t1:
        st.header("Análisis de Capacitación 2026")
        
        # Gráfico 1: Horas y Acciones (Colores INFOTEP)
        df_g1 = df.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
        fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'], 
                      barmode='group', text_auto='d',
                      color_discrete_sequence=[COLOR_AZUL, COLOR_AMARILLO, COLOR_VERDE])
        st.plotly_chart(fig1, use_container_width=True)

        # Gráfico 2: Niveles (Colores INFOTEP)
        df_g2 = df.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
        fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], 
                      barmode='stack', text_auto='d',
                      color_discrete_sequence=[COLOR_AZUL, COLOR_AMARILLO, COLOR_ROJO])
        st.plotly_chart(fig2, use_container_width=True)

    with t2:
        # Botones de descarga
        c1, c2 = st.columns(2)
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as w:
            df.to_excel(w, index=False)
        c1.download_button("📥 Excel", out.getvalue(), "Reporte.xlsx")
        
        # Tabla con fechas limpias
        df_v = df.copy()
        df_v['FECHA_INICIO'] = df_v['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        df_v['FECHA_TERMINO'] = df_v['FECHA_TERMINO'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_v, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Error: {e}")
