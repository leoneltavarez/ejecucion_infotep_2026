import streamlit as st
import pandas as pd
import plotly.express as px
import json
from datetime import datetime, date
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURACIÓN Y ESTÉTICA INFOTEP ---
C_AZUL, C_AMARILLO, C_VERDE, C_ROJO = "#0056b3", "#ffcc00", "#28a745", "#dc3545"
st.set_page_config(page_title="Gestión Leonel Tavarez 2026", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetric"] {
        background-color: #f8f9fa; padding: 15px; border-radius: 10px;
        border-left: 5px solid #0056b3; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXIÓN DRIVE ---
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"

def get_drive_service():
    try:
        if "google_creds" in st.secrets:
            info = json.loads(st.secrets["google_creds"]["json_data"])
            if "private_key" in info:
                info["private_key"] = info["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive"])
            return build('drive', 'v3', credentials=creds)
    except: return None
    return None

def list_files_in_folder(empresa_name):
    try:
        service = get_drive_service()
        if not service: return []
        query = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items: return []
        f_id = items[0]['id']
        res = service.files().list(q=f"'{f_id}' in parents and trashed = false", fields="files(name, webViewLink)").execute()
        return res.get('files', [])
    except: return []

# --- MOTOR DE DATOS (RECONSTRUIDO) ---
@st.cache_data(ttl=600)
def load_and_merge_data():
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/export?format=csv"
    url_acad = "https://docs.google.com/spreadsheets/d/1DamhAcTIll23Op6JyQvJYvSjKeaCmx8f_FmkKDp1UXE/export?format=csv"
    
    try:
        df_b = pd.read_csv(url_base)
        df_a = pd.read_csv(url_acad)
        df_b.columns = [c.strip().upper().replace("_", " ") for c in df_b.columns]
        df_a.columns = [c.strip().upper().replace("_", " ") for c in df_a.columns]
        
        # Limpieza de códigos
        df_b['CODIGO CURSO'] = df_b['CODIGO CURSO'].astype(str).str.strip()
        df_a['CODIGO CURSO'] = df_a['CODIGO CURSO'].astype(str).str.strip()
        
        # Unir facilitador
        if 'FACILITADOR' in df_a.columns:
            df_a_sub = df_a[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
            df_final = pd.merge(df_b, df_a_sub, on='CODIGO CURSO', how='left')
        else:
            df_final = df_b

        # Limpiar Estado
        df_final['ESTADO'] = df_final['ESTADO'].astype(str).str.capitalize().str.strip()
        df_final = df_final[df_final['ESTADO'].isin(['Iniciado', 'Cerrado'])]
        
        # --- PROCESAMIENTO CRÍTICO DE FECHAS ---
        # Forzamos la conversión y eliminamos horas/minutos para que solo quede el día
        df_final['FECHA_COMPARABLE'] = pd.to_datetime(df_final['FECHA INICIO'], dayfirst=False, errors='coerce').dt.date
        df_final = df_final.dropna(subset=['FECHA_COMPARABLE'])
        
        # Aseguramos que las columnas numéricas sean enteras
        cols_num = ['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES', 'HORAS EJECUTADAS', 'HORAS FALTAN']
        for col in cols_num:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)

        df_final['PARTICIPANTES'] = df_final['OPERARIOS'] + df_final['MANDOS MEDIOS'] + df_final['GERENTES']
        return df_final
    except Exception as e:
        st.error(f"Error técnico en datos: {e}")
        return pd.DataFrame()

# --- CARGA INICIAL ---
df_raw = load_and_merge_data()

if not df_raw.empty:
    st.sidebar.header("🛠️ Filtros de Control")
    
    if st.sidebar.button("🔄 Sincronizar Google Sheets"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")
    
    # --- 1. FILTRO DE FECHA (EL MURO DE CONTENCIÓN) ---
    st.sidebar.subheader("📅 Periodo de Capacitación")
    min_val, max_val = df_raw['FECHA_COMPARABLE'].min(), df_raw['FECHA_COMPARABLE'].max()
    
    rango_fecha = st.sidebar.date_input(
        "Rango (Día/Mes/Año)", 
        [min_val, max_val],
        format="DD/MM/YYYY"
    )
    
    # Aplicamos el filtro de fecha inmediatamente al DataFrame original
    if isinstance(rango_fecha, list) and len(rango_fecha) == 2:
        # Lógica: >= Inicio y < Final (Tu regla de exclusión)
        df_f = df_raw[(df_raw['FECHA_COMPARABLE'] >= rango_fecha[0]) & (df_raw['FECHA_COMPARABLE'] < rango_fecha[1])].copy()
    else:
        df_f = df_raw.copy()

    # --- 2. FILTROS SECUNDARIOS (Sobre lo que sobrevivió a la fecha) ---
    f_empresa = st.sidebar.multiselect("Empresa", sorted(df_f['EMPRESA'].unique()))
    if f_empresa: df_f = df_f[df_f['EMPRESA'].isin(f_empresa)]
    
    f_facilitador = st.sidebar.multiselect("Facilitador", sorted(df_f['FACILITADOR'].unique().astype(str)))
    if f_facilitador: df_f = df_f[df_f['FACILITADOR'].isin(f_facilitador)]
    
    f_estado = st.sidebar.multiselect("Estado", sorted(df_f['ESTADO'].unique()), default=sorted(df_f['ESTADO'].unique()))
    if f_estado: df_f = df_f[df_f['ESTADO'].isin(f_estado)]

    # --- RENDERIZADO DE INTERFAZ ---
    t1, t2, t3 = st.tabs(["📊 Dashboard Maestro", "📋 Tabla de Datos", "📂 Repositorio"])

    with t1:
        st.title("Control Operativo Leonel Tavarez 2026")
        c1, c2, c3, c4 = st.columns(4)
        # Las métricas ahora dependen 100% del df_f filtrado
        with c1: st.metric("Total Horas", f"{df_f['HORAS EJECUTADAS'].sum():,}")
        with c2: st.metric("Participantes", f"{df_f['PARTICIPANTES'].sum():,}")
        with c3: st.metric("Acciones Formativas", f"{len(df_f):,}")
        with c4: st.metric("Empresas Impactadas", f"{df_f['EMPRESA'].nunique()}")
        st.markdown("---")
        
        if not df_f.empty:
            df_g = df_f.groupby('EMPRESA')[['HORAS EJECUTADAS', 'PARTICIPANTES']].sum().reset_index()
            fig = px.bar(df_g, x='EMPRESA', y=['HORAS EJECUTADAS', 'PARTICIPANTES'], 
                         barmode='group', text_auto=True,
                         color_discrete_map={'HORAS EJECUTADAS': C_AZUL, 'PARTICIPANTES': C_AMARILLO})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No hay datos para el rango de fechas seleccionado.")

    with t2:
        st.subheader("📋 Registro Maestro")
        columnas = ['EMPRESA', 'RNC', 'ACCION FORMATIVA', 'FECHA INICIO', 'FECHA TERMINO', 'FACILITADOR', 'ESTADO', 'HORAS EJECUTADAS', 'PARTICIPANTES']
        
        # Fila de Totales Dinámica
        totales = {
            'EMPRESA': 'TOTAL GENERAL FILTRADO',
            'ACCION FORMATIVA': f'{len(df_f)} Acciones Formativas',
            'HORAS EJECUTADAS': df_f['HORAS EJECUTADAS'].sum(),
            'PARTICIPANTES': df_f['PARTICIPANTES'].sum()
        }
        
        df_con_total = pd.concat([df_f[columnas], pd.DataFrame([totales])], ignore_index=True).fillna('')

        # Botones de descarga
        cd1, cd2, _ = st.columns([1.2, 1.2, 3.6])
        with cd1:
            st.download_button("📥 CSV", df_con_total.to_csv(index=False).encode('utf-8'), "reporte.csv", "text/csv")
        with cd2:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_con_total.to_excel(writer, index=False, sheet_name='Reporte')
            st.download_button("📥 Excel", output.getvalue(), "reporte.xlsx")

        st.dataframe(df_con_total, use_container_width=True, hide_index=True)

    with t3:
        st.subheader("📂 Repositorio")
        if f_empresa and len(f_empresa) == 1:
            archivos = list_files_in_folder(f_empresa[0])
            if archivos:
                for a in archivos:
                    st.write(f"📄 {a['name']}")
                    st.link_button("Abrir", a['webViewLink'])
            else: st.warning("Carpeta vacía.")
        else: st.info("Selecciona una empresa para gestionar documentos.")
