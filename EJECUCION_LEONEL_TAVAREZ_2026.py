import streamlit as st
import pandas as pd
import plotly.express as px
import json
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- IDENTIDAD VISUAL ---
COLOR_AZUL = "#0056b3"
COLOR_AMARILLO = "#ffcc00"
COLOR_VERDE = "#28a745"
COLOR_ROJO = "#dc3545"

st.set_page_config(page_title="Dashboard Maestro - Leonel Tavarez", layout="wide")

# --- CONFIGURACIÓN DRIVE ---
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

# --- CARGA E INTEGRACIÓN ---
@st.cache_data(ttl=0) 
def load_integrated_data():
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    ID_ACADEMICO = "1DamhAcTIll23Op6JyQvJYvSjKeaCmx8f_FmkKDp1UXE"
    url_acad = f"https://docs.google.com/spreadsheets/d/{ID_ACADEMICO}/gviz/tq?tqx=out:csv"
    
    try:
        # Cargar y normalizar Base Principal
        df_base = pd.read_csv(url_base)
        df_base.columns = [c.strip().upper().replace("_", " ") for c in df_base.columns]
        
        # Cargar y normalizar Académico
        try:
            df_acad = pd.read_csv(url_acad)
            df_acad.columns = [c.strip().upper().replace("_", " ") for c in df_acad.columns]
            
            if 'CODIGO CURSO' in df_acad.columns:
                df_acad_sub = df_acad[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
                df_final = pd.merge(df_base, df_acad_sub, on='CODIGO CURSO', how='left')
            else:
                df_final = df_base
        except:
            df_final = df_base

        # Limpieza de datos
        if 'FECHA INICIO' in df_final.columns:
            df_final['FECHA INICIO'] = pd.to_datetime(df_final['FECHA INICIO'], dayfirst=True, errors='coerce')
            df_final = df_final.sort_values(by='FECHA INICIO', ascending=True)

        cols_num = ['HORAS EJECUTADAS', 'OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']
        for col in cols_num:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)
        
        df_final['PARTICIPANTES'] = df_final['OPERARIOS'] + df_final['MANDOS MEDIOS'] + df_final['GERENTES']
        df_final['FACILITADOR'] = df_final['FACILITADOR'].fillna("POR ASIGNAR")
        
        return df_final
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
try:
    df_data = load_integrated_data()
    
    if not df_data.empty:
        st.sidebar.title("🛠️ Filtros Maestros")
        f_empresa = st.sidebar.multiselect("Empresa", sorted(df_data["EMPRESA"].unique()))
        f_facilitador = st.sidebar.multiselect("Facilitador", sorted(df_data["FACILITADOR"].unique()))
        f_accion = st.sidebar.multiselect("Acción Formativa", sorted(df_data["ACCION FORMATIVA"].unique()))
        f_estado = st.sidebar.multiselect("Estado", sorted(df_data["ESTADO"].unique()), default=df_data["ESTADO"].unique())

        df_f = df_data[df_data["ESTADO"].isin(f_estado)]
        if f_empresa: df_f = df_f[df_f["EMPRESA"].isin(f_empresa)]
        if f_facilitador: df_f = df_f[df_f["FACILITADOR"].isin(f_facilitador)]
        if f_accion: df_f = df_f[df_f["ACCION FORMATIVA"].isin(f_accion)]

        t_dash, t_tabla, t_drive = st.tabs(["📊 Dashboard", "📋 Registro Datos", "📂 Repositorio Drive"])

        with t_dash:
            st.title("Control Integrado INFOTEP 2026")
            
            # Gráfico 1: Ejecución Operativa (Horas, Participantes y Cantidad de Cursos)
            st.subheader("1. Alcance Operativo (Horas, Participantes y Acciones)")
            df_g1 = df_f.copy()
            df_g1['ACCIONES FORMATIVAS'] = 1
            df_g1 = df_g1.groupby('EMPRESA')[['HORAS EJECUTADAS', 'PARTICIPANTES', 'ACCIONES FORMATIVAS']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS EJECUTADAS', 'PARTICIPANTES', 'ACCIONES FORMATIVAS'], 
                          barmode='group', text_auto='d',
                          color_discrete_map={'HORAS EJECUTADAS': COLOR_AZUL, 'PARTICIPANTES': COLOR_AMARILLO, 'ACCIONES FORMATIVAS': COLOR_VERDE})
            st.plotly_chart(fig1, use_container_width=True)

            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("2. Niveles Jerárquicos")
                df_g2 = df_f.groupby('EMPRESA')[['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']].sum().reset_index()
                fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES'], barmode='stack', text_auto='d',
                              color_discrete_map={'OPERARIOS': COLOR_AZUL, 'MANDOS MEDIOS': COLOR_AMARILLO, 'GERENTES': COLOR_ROJO})
                st.plotly_chart(fig2, use_container_width=True)
            
            with col_b:
                st.subheader("3. Productividad Facilitadores")
                df_g3 = df_f.groupby('FACILITADOR').size().reset_index(name='TOTAL CURSOS')
                fig3 = px.bar(df_g3, x='FACILITADOR', y='TOTAL CURSOS', text_auto=True, color_discrete_sequence=[COLOR_AZUL])
                st.plotly_chart(fig3, use_container_width=True)

        with t_tabla:
            st.dataframe(df_f, use_container_width=True, hide_index=True)

        with t_drive:
            if f_empresa and len(f_empresa) == 1:
                archivos = list_files_in_folder(f_empresa[0])
                for a in archivos:
                    st.link_button(f"📄 Abrir {a['name']}", a['webViewLink'])
            else:
                st.info("Selecciona una sola empresa para ver sus archivos.")

except Exception as e:
    st.error(f"Error en la aplicación: {e}")
