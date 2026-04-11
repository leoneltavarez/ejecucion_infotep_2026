import streamlit as st
import pandas as pd
import plotly.express as px
import json
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- ESTÉTICA ---
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

def list_files_in_folder(empresa_name):
    try:
        service = get_drive_service()
        if not service: return []
        query = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items: return []
        f_id = items[0]['id']
        res = service.files().list(q=f"'{f_id}' in parents and trashed = false", fields="files(id, name, webViewLink)").execute()
        return res.get('files', [])
    except: return []

# --- CARGA E INTEGRACIÓN ---
@st.cache_data(ttl=0) 
def load_integrated_data():
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    url_acad = "https://docs.google.com/spreadsheets/d/1DamhAcTIll23Op6JyQvJYvSjKeaCmx8f_FmkKDp1UXE/gviz/tq?tqx=out:csv"
    
    try:
        df_base = pd.read_csv(url_base)
        df_base.columns = [str(c).strip().upper() for c in df_base.columns]
        
        try:
            df_acad = pd.read_csv(url_acad)
            df_acad.columns = [str(c).strip().upper() for c in df_acad.columns]
            
            # Verificamos que existan las llaves de unión
            if 'CODIGO CURSO' in df_acad.columns and 'FACILITADOR' in df_acad.columns:
                df_acad_sub = df_acad[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
                df_final = pd.merge(df_base, df_acad_sub, on='CODIGO CURSO', how='left')
            else:
                df_final = df_base
                if 'FACILITADOR' not in df_final.columns: df_final['FACILITADOR'] = "POR ASIGNAR"
        except:
            df_final = df_base
            df_final['FACILITADOR'] = "ERROR CARGA ACADÉMICO"

        # Limpieza de fechas y números
        if 'FECHA INICIO' in df_final.columns:
            df_final['FECHA INICIO'] = pd.to_datetime(df_final['FECHA INICIO'], dayfirst=True, errors='coerce')

        for col in ['HORAS EJECUTADAS', 'OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)
        
        df_final['PARTICIPANTES'] = df_final['OPERARIOS'] + df_final['MANDOS MEDIOS'] + df_final['GERENTES']
        df_final['FACILITADOR'] = df_final['FACILITADOR'].fillna("SIN ASIGNAR")
        
        return df_final
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
try:
    df_data = load_integrated_data()
    
    if not df_data.empty:
        st.sidebar.title("🛠️ Filtros")
        f_empresa = st.sidebar.multiselect("Empresa", sorted(df_data["EMPRESA"].unique()))
        f_facilitador = st.sidebar.multiselect("Facilitador", sorted(df_data["FACILITADOR"].unique()))
        f_estado = st.sidebar.multiselect("Estado", sorted(df_data["ESTADO"].unique()), default=df_data["ESTADO"].unique())

        df_f = df_data[df_data["ESTADO"].isin(f_estado)]
        if f_empresa: df_f = df_f[df_f["EMPRESA"].isin(f_empresa)]
        if f_facilitador: df_f = df_f[df_f["FACILITADOR"].isin(f_facilitador)]

        t1, t2, t3 = st.tabs(["📊 Dashboard Maestro", "📋 Datos", "📂 Repositorio Drive"])

        with t1:
            st.title("Control de Gestión INFOTEP 2026")
            
            # Gráfico 1: Horas, Participantes y Acciones (Contando cada fila como 1 curso)
            st.subheader("1. Alcance: Horas, Participantes y Cursos")
            df_g1 = df_f.copy()
            df_g1['ACCIONES'] = 1
            df_g1 = df_g1.groupby('EMPRESA')[['HORAS EJECUTADAS', 'PARTICIPANTES', 'ACCIONES']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS EJECUTADAS', 'PARTICIPANTES', 'ACCIONES'], barmode='group', text_auto='d',
                          color_discrete_map={'HORAS EJECUTADAS': COLOR_AZUL, 'PARTICIPANTES': COLOR_AMARILLO, 'ACCIONES': COLOR_VERDE})
            st.plotly_chart(fig1, use_container_width=True)

            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("2. Niveles Jerárquicos")
                df_g2 = df_f.groupby('EMPRESA')[['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']].sum().reset_index()
                fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES'], barmode='stack', text_auto='d',
                              color_discrete_map={'OPERARIOS': COLOR_AZUL, 'MANDOS MEDIOS': COLOR_AMARILLO, 'GERENTES': COLOR_ROJO})
                st.plotly_chart(fig2, use_container_width=True)
            with col_b:
                st.subheader("3. Cursos por Facilitador")
                df_g3 = df_f.groupby('FACILITADOR').size().reset_index(name='TOTAL')
                fig3 = px.bar(df_g3, x='FACILITADOR', y='TOTAL', text_auto=True, color_discrete_sequence=[COLOR_AZUL])
                st.plotly_chart(fig3, use_container_width=True)

        with t2:
            st.dataframe(df_f, use_container_width=True, hide_index=True)

        with t3:
            if f_empresa and len(f_empresa) == 1:
                archivos = list_files_in_folder(f_empresa[0])
                for a in archivos: st.link_button(f"📄 {a['name']}", a['webViewLink'])
            else: st.info("Selecciona una empresa para ver sus archivos.")

except Exception as e:
    st.error(f"Error General: {e}")
