import streamlit as st
import pandas as pd
import plotly.express as px
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- ESTÉTICA ---
C_AZUL, C_AMARILLO, C_VERDE, C_ROJO = "#0056b3", "#ffcc00", "#28a745", "#dc3545"
st.set_page_config(page_title="Dashboard Maestro - Leonel Tavarez", layout="wide")

# --- CONFIGURACIÓN DRIVE ---
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"

def get_drive_service():
    try:
        info = json.loads(st.secrets["google_creds"]["json_data"])
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
        res = service.files().list(q=f"'{f_id}' in parents and trashed = false", fields="files(name, webViewLink)").execute()
        return res.get('files', [])
    except: return []

# --- CARGA E INTEGRACIÓN LIMPIA ---
@st.cache_data(ttl=0)
def load_and_merge_data():
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/export?format=csv"
    url_acad = "https://docs.google.com/spreadsheets/d/1DamhAcTIll23Op6JyQvJYvSjKeaCmx8f_FmkKDp1UXE/export?format=csv"
    
    try:
        df_b = pd.read_csv(url_base)
        df_a = pd.read_csv(url_acad)

        # Normalización de encabezados
        df_b.columns = [c.strip().upper().replace("_", " ") for c in df_b.columns]
        df_a.columns = [c.strip().upper().replace("_", " ") for c in df_a.columns]
        
        # Limpieza de llaves de unión
        df_b['CODIGO CURSO'] = df_b['CODIGO CURSO'].astype(str).str.strip()
        df_a['CODIGO CURSO'] = df_a['CODIGO CURSO'].astype(str).str.strip()
        
        # Merge por Código de Curso
        if 'FACILITADOR' in df_a.columns:
            df_a_sub = df_a[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
            df_final = pd.merge(df_b, df_a_sub, on='CODIGO CURSO', how='left')
        else:
            df_final = df_b

        # LIMPIEZA ANT-ERRORES (Para evitar el error de comparación float vs str)
        for col in ['EMPRESA', 'FACILITADOR', 'ESTADO']:
            if col in df_final.columns:
                df_final[col] = df_final[col].fillna("SIN DATO").astype(str).str.strip()

        # Asegurar números
        for col in ['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES', 'HORAS EJECUTADAS']:
            if col not in df_final.columns: df_final[col] = 0
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)

        df_final['PARTICIPANTES'] = df_final['OPERARIOS'] + df_final['MANDOS MEDIOS'] + df_final['GERENTES']
        
        return df_final
    except Exception as e:
        st.error(f"Error en procesamiento: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
try:
    df = load_and_merge_data()
    
    if not df.empty:
        st.sidebar.header("🛠️ Filtros de Control")
        
        # El truco para evitar el error: convertir a set para quitar duplicados y asegurar que todo es str antes de sorted()
        def safe_sorted(col_name):
            values = df[col_name].unique()
            return sorted([str(x) for x in values if pd.notna(x)])

        f_empresa = st.sidebar.multiselect("Empresa", safe_sorted("EMPRESA"))
        f_facilitador = st.sidebar.multiselect("Facilitador", safe_sorted("FACILITADOR"))
        f_estado = st.sidebar.multiselect("Estado", safe_sorted("ESTADO"), default=df["ESTADO"].unique().tolist())

        df_f = df[df["ESTADO"].isin(f_estado)]
        if f_empresa: df_f = df_f[df_f["EMPRESA"].isin(f_empresa)]
        if f_facilitador: df_f = df_f[df_f["FACILITADOR"].isin(f_facilitador)]

        t1, t2, t3 = st.tabs(["📊 Dashboard", "📋 Registro", "📂 Drive"])

        with t1:
            st.title("Gestión de Capacitación 2026")
            
            # Gráfico 1: Alcance
            df_g1 = df_f.copy()
            df_g1['CURSOS'] = 1
            df_g1 = df_g1.groupby('EMPRESA')[['HORAS EJECUTADAS', 'PARTICIPANTES', 'CURSOS']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS EJECUTADAS', 'PARTICIPANTES', 'CURSOS'], barmode='group', text_auto='d',
                          color_discrete_map={'HORAS EJECUTADAS': C_AZUL, 'PARTICIPANTES': C_AMARILLO, 'CURSOS': C_VERDE})
            st.plotly_chart(fig1, use_container_width=True)

            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("Distribución Jerárquica")
                df_g2 = df_f.groupby('EMPRESA')[['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']].sum().reset_index()
                fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES'], barmode='stack', text_auto='d',
                              color_discrete_map={'OPERARIOS': C_AZUL, 'MANDOS MEDIOS': C_AMARILLO, 'GERENTES': C_ROJO})
                st.plotly_chart(fig2, use_container_width=True)
            with col_b:
                st.subheader("Participación Facilitador")
                df_g3 = df_f.groupby('FACILITADOR').size().reset_index(name='TOTAL')
                fig3 = px.bar(df_g3, x='FACILITADOR', y='TOTAL', text_auto=True, color_discrete_sequence=[C_AZUL])
                st.plotly_chart(fig3, use_container_width=True)

        with t2:
            st.dataframe(df_f, use_container_width=True, hide_index=True)

        with t3:
            if f_empresa and len(f_empresa) == 1:
                archivos = list_files_in_folder(f_empresa[0])
                for a in archivos: st.link_button(f"📄 {a['name']}", a['webViewLink'])
            else: st.info("Selecciona una empresa para ver sus archivos.")

except Exception as e:
    st.error(f"Error de visualización: {e}")
