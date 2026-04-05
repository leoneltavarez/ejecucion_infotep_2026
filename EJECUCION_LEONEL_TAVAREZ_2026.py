import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- INTENTO DE IMPORTACIÓN DE LIBRERÍAS CRÍTICAS ---
try:
    from fillpdf import fillpdfs
except ImportError:
    st.error("Error: Librería 'fillpdf' no encontrada. Agrégala a requirements.txt")

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard INFOTEP - Leonel Tavarez", layout="wide")

# --- CONSTANTES ---
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"
PLANTILLA_PDF = 'PLANTILLA_FINAL.pdf'

# --- FUNCIONES DE GOOGLE DRIVE ---
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
    
    # supportsAllDrives=True soluciona el problema de permisos en carpetas compartidas
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
    except:
        return []

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

# --- LÓGICA PRINCIPAL ---
try:
    df_orig = load_data()
    st.sidebar.title("🛠️ Gestión INFOTEP")
    
    # SECCIÓN DE CRONOGRAMAS (PAGINACIÓN DE 8)
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
                st.sidebar.error("No se encontró la carpeta en Drive.")
            else:
                lote_size = 8
                for i in range(0, len(acciones), lote_size):
                    lote = acciones[i : i + lote_size]
                    parte = (i // lote_size) + 1
                    datos = {'txt_empresa': emp_pdf, 'txt_regional': 'Cibao Norte'}
                    for idx, act in enumerate(lote):
                        datos[f'accion_{idx+1}'] = act
                    
                    temp_pdf = f"temp_{parte}.pdf"
                    fillpdfs.write_fillable_pdf(PLANTILLA_PDF, temp_pdf, datos)
                    with open(temp_pdf, "rb") as f:
                        upload_to_drive(f.read(), f"Cronograma_{emp_pdf}_P{parte}.pdf", f_id)
                    os.remove(temp_pdf)
                st.sidebar.success("✅ Cronogramas enviados con éxito.")

    # FILTROS DE VISTA
    f_empresa = st.sidebar.multiselect("Empresa (Vista)", options=sorted(df_orig["EMPRESA"].unique()))
    f_estado = st.sidebar.multiselect("Estado (Vista)", options=sorted(df_orig["ESTADO"].unique()), default=df_orig["ESTADO"].unique())
    
    df = df_orig[df_orig["ESTADO"].isin(f_estado)]
    if f_empresa:
        df = df[df["EMPRESA"].isin(f_empresa)]

    # TABS PRINCIPALES
    tabs = st.tabs(["📊 Dashboard", "📋 Tabla de Datos", "📂 Repositorio Drive"])

    with tabs[0]:
        st.title("Control de Ejecución 2026")
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Totales", f"{int(df['HORAS_EJECUTADAS'].sum()):,}")
        c2.metric("Acciones Formativas", f"{int(df['TOTAL_ACCIONES'].sum()):,}")
        c3.metric("Total Participantes", f"{int(df['PARTICIPANTES'].sum()):,}")
        
        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            df_g1 = df.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'], barmode='group', text_auto='d')
            st.plotly_chart(fig1, use_container_width=True)
        with col_b:
            df_g2 = df.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], barmode='stack', text_auto='d')
            st.plotly_chart(fig2, use_container_width=True)

    with tabs[1]:
        st.subheader("Registros Detallados")
        # Botones de descarga
        d1, d2 = st.columns(2)
        towrite = BytesIO()
        with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Data')
        d1.download_button("📥 Excel", towrite.getvalue(), "Reporte.xlsx", "application/vnd.ms-excel")
        d2.download_button("📄 CSV", df.to_csv(index=False).encode('utf-8'), "Reporte.csv", "text/csv")
        
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
                    col_n, col_b = st.columns([4, 1])
                    col_n.write(f"📄 {a['name']}")
                    col_b.link_button("Abrir", a['webViewLink'])
            else:
                st.warning("No se encontraron archivos en esta carpeta.")
        else:
            st.info("Seleccione una sola empresa en el filtro lateral.")

except Exception as e:
    st.error(f"Se ha producido un error: {e}")
