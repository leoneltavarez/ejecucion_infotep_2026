import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- LIBRERÍA DE PDF ---
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
    service = get_drive_service()
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaIoBaseUpload(BytesIO(content_bytes), mimetype='application/pdf')
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

# --- PROCESAMIENTO DE DATOS ---
@st.cache_data(ttl=0)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df['ESTADO'] = df['ESTADO'].astype(str).str.strip()
    df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
    df['FECHA_TERMINO'] = pd.to_datetime(df['FECHA_TERMINO'], dayfirst=True, errors='coerce')
    
    # Conversión a enteros para limpieza visual
    columnas_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in columnas_num:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    return df

try:
    df_orig = load_data()
    
    # --- BARRA LATERAL (SIDEBAR) ---
    st.sidebar.image("https://www.infotep.gob.do/images/logo_infotep.png", width=150) # Opcional: Logo
    st.sidebar.title("🛠️ Panel de Control")
    
    # 1. Generador de Cronogramas
    st.sidebar.subheader("📄 Cronogramas PDF")
    emp_pdf = st.sidebar.selectbox("Empresa para Cronograma", options=sorted(df_orig["EMPRESA"].unique()))
    if st.sidebar.button("🚀 Generar y Subir"):
        df_cerrados = df_orig[(df_orig["EMPRESA"] == emp_pdf) & (df_orig["ESTADO"] == "Cerrado")]
        acciones = df_cerrados['ACCION_FORMATIVA'].tolist()
        if not acciones:
            st.sidebar.warning(f"Sin cursos 'Cerrados' en {emp_pdf}")
        else:
            f_id = get_folder_id(emp_pdf)
            if f_id:
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
                        upload_to_drive(f.read(), f"Cronograma_{emp_pdf}_Parte_{p}.pdf", f_id)
                    os.remove(t_name)
                st.sidebar.success("✅ Cronogramas en Drive.")
            else: st.sidebar.error("Carpeta no encontrada.")

    st.sidebar.divider()
    
    # 2. Filtros de Vista
    st.sidebar.subheader("🔍 Filtros de Visualización")
    f_empresa = st.sidebar.multiselect("Empresas", options=sorted(df_orig["EMPRESA"].unique()))
    f_estado = st.sidebar.multiselect("Estados", options=sorted(df_orig["ESTADO"].unique()), default=df_orig["ESTADO"].unique())
    
    df_filtrado = df_orig[df_orig["ESTADO"].isin(f_estado)]
    if f_empresa:
        df_filtrado = df_filtrado[df_filtrado["EMPRESA"].isin(f_empresa)]

    # --- PANTALLA PRINCIPAL ---
    tabs = st.tabs(["📊 Dashboard Ejecutivo", "📋 Tabla de Datos", "📂 Repositorio Drive"])

    with tabs[0]:
        st.title("Control de Ejecución 2026")
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Totales", f"{int(df_filtrado['HORAS_EJECUTADAS'].sum()):,}")
        c2.metric("Acciones Formativas", f"{int(df_filtrado['TOTAL_ACCIONES'].sum()):,}")
        c3.metric("Participantes", f"{int(df_filtrado['PARTICIPANTES'].sum()):,}")
        
        st.divider()
        col_izq, col_der = st.columns(2)
        
        with col_izq:
            st.subheader("Alcance por Empresa")
            df_g1 = df_filtrado.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'], 
                          barmode='group', text_auto='d',
                          color_discrete_map={'HORAS_EJECUTADAS': COLOR_AZUL, 'PARTICIPANTES': COLOR_AMARILLO, 'TOTAL_ACCIONES': COLOR_VERDE})
            st.plotly_chart(fig1, use_container_width=True)

        with col_der:
            st.subheader("Distribución de Niveles")
            df_g2 = df_filtrado.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], 
                          barmode='stack', text_auto='d',
                          color_discrete_map={'OPERARIOS': COLOR_AZUL, 'MANDOS_MEDIOS': COLOR_AMARILLO, 'GERENTES': COLOR_ROJO})
            st.plotly_chart(fig2, use_container_width=True)

    with tabs[1]:
        st.subheader("Detalle de Cursos")
        # Botones de descarga
        d1, d2 = st.columns(2)
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            df_filtrado.to_excel(writer, index=False, sheet_name='Data')
        d1.download_button("📥 Descargar Excel", out.getvalue(), "Reporte_INFOTEP.xlsx", "application/vnd.ms-excel")
        d2.download_button("📄 Descargar CSV", df_filtrado.to_csv(index=False).encode('utf-8'), "Reporte_INFOTEP.csv", "text/csv")
        
        # Tabla Formateada
        df_tab = df_filtrado.copy()
        df_tab['FECHA_INICIO'] = df_tab['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        df_tab['FECHA_TERMINO'] = df_tab['FECHA_TERMINO'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_tab, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Archivos en Google Drive")
        if f_empresa and len(f_empresa) == 1:
            archivos = list_files_in_folder(f_empresa[0])
            if archivos:
                for a in archivos:
                    col_file, col_link = st.columns([4, 1])
                    col_file.write(f"📄 {a['name']}")
                    col_link.link_button("Abrir Archivo", a['webViewLink'])
            else: st.warning("No hay archivos en la carpeta de esta empresa.")
        else: st.info("Selecciona **una sola empresa** en el filtro lateral para ver su repositorio.")

except Exception as e:
    st.error(f"Error en la aplicación: {e}")
