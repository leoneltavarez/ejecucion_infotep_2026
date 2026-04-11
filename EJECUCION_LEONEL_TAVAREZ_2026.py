import streamlit as st
import pandas as pd
import plotly.express as px
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard Maestro - Leonel Tavarez", layout="wide")

# Colores INFOTEP
C_AZUL, C_AMARILLO, C_VERDE, C_ROJO = "#0056b3", "#ffcc00", "#28a745", "#dc3545"

# --- REPOSITORIO DRIVE ---
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"

def get_drive_service():
    try:
        info = json.loads(st.secrets["google_creds"]["json_data"])
        if "private_key" in info: info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive"])
        return build('drive', 'v3', credentials=creds)
    except: return None

def list_files_in_folder(empresa_name):
    try:
        service = get_drive_service()
        if not service: return []
        query = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder'"
        res = service.files().list(q=query, fields="files(id, name)").execute()
        items = res.get('files', [])
        if not items: return []
        res_docs = service.files().list(q=f"'{items[0]['id']}' in parents and trashed = false", fields="files(name, webViewLink)").execute()
        return res_docs.get('files', [])
    except: return []

# --- MOTOR DE INTEGRACIÓN INFALIBLE ---
@st.cache_data(ttl=0)
def load_and_merge_data():
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    url_acad = "https://docs.google.com/spreadsheets/d/1DamhAcTIll23Op6JyQvJYvSjKeaCmx8f_FmkKDp1UXE/gviz/tq?tqx=out:csv"
    
    try:
        # 1. Cargar y estandarizar Base Principal
        df_b = pd.read_csv(url_base)
        df_b.columns = [c.strip().upper().replace("_", " ") for c in df_b.columns]
        
        # 2. Cargar y estandarizar Académico
        df_a = pd.read_csv(url_acad)
        df_a.columns = [c.strip().upper().replace("_", " ") for c in df_a.columns]
        
        # 3. Limpieza profunda de la llave de unión
        df_b['CODIGO CURSO'] = df_b['CODIGO CURSO'].astype(str).str.strip()
        df_a['CODIGO CURSO'] = df_a['CODIGO CURSO'].astype(str).str.strip()
        
        # 4. Cruce de datos (Solo traemos Facilitador del Académico)
        if 'FACILITADOR' in df_a.columns:
            df_a_sub = df_a[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
            df_final = pd.merge(df_b, df_a_sub, on='CODIGO CURSO', how='left')
        else:
            df_final = df_b

        # 5. Asegurar columnas numéricas (Estandarización de nombres)
        cols_map = {'HORAS EJECUTADAS': 0, 'OPERARIOS': 0, 'MANDOS MEDIOS': 0, 'GERENTES': 0, 'TOTAL PTES': 0}
        for col in cols_map:
            if col not in df_final.columns: df_final[col] = 0
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)

        df_final['PARTICIPANTES'] = df_final['OPERARIOS'] + df_final['MANDOS MEDIOS'] + df_final['GERENTES']
        df_final['FACILITADOR'] = df_final.get('FACILITADOR', 'POR ASIGNAR').fillna('SIN ASIGNAR')
        
        return df_final
    except Exception as e:
        st.error(f"Error en integración: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
try:
    df = load_and_merge_data()
    
    if not df.empty:
        st.sidebar.title("🛠️ Filtros de Gestión")
        f_empresa = st.sidebar.multiselect("Empresa", sorted(df["EMPRESA"].unique()))
        f_facilitador = st.sidebar.multiselect("Facilitador", sorted(df["FACILITADOR"].unique()))
        f_estado = st.sidebar.multiselect("Estado", sorted(df["ESTADO"].unique()), default=df["ESTADO"].unique())

        df_f = df[df["ESTADO"].isin(f_estado)]
        if f_empresa: df_f = df_f[df_f["EMPRESA"].isin(f_empresa)]
        if f_facilitador: df_f = df_f[df_f["FACILITADOR"].isin(f_facilitador)]

        t_dash, t_datos, t_drive = st.tabs(["📊 Dashboard Maestro", "📋 Registro", "📂 Drive"])

        with t_dash:
            st.title("Control Operativo 2026")
            
            # Gráfico 1: Ejecución Triple
            st.subheader("1. Alcance Operativo: Horas, Participantes y Cantidad de Cursos")
            df_g1 = df_f.copy()
            df_g1['CURSOS'] = 1
            df_g1 = df_g1.groupby('EMPRESA')[['HORAS EJECUTADAS', 'PARTICIPANTES', 'CURSOS']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS EJECUTADAS', 'PARTICIPANTES', 'CURSOS'], 
                          barmode='group', text_auto='d',
                          color_discrete_map={'HORAS EJECUTADAS': C_AZUL, 'PARTICIPANTES': C_AMARILLO, 'CURSOS': C_VERDE})
            st.plotly_chart(fig1, use_container_width=True)

            c_left, c_right = st.columns(2)
            with c_left:
                st.subheader("2. Distribución de Niveles")
                df_g2 = df_f.groupby('EMPRESA')[['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']].sum().reset_index()
                fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES'], barmode='stack', text_auto='d',
                              color_discrete_map={'OPERARIOS': C_AZUL, 'MANDOS MEDIOS': C_AMARILLO, 'GERENTES': C_ROJO})
                st.plotly_chart(fig2, use_container_width=True)
            with c_right:
                st.subheader("3. Productividad Facilitador")
                df_g3 = df_f.groupby('FACILITADOR').size().reset_index(name='TOTAL')
                fig3 = px.bar(df_g3, x='FACILITADOR', y='TOTAL', text_auto=True, color_discrete_sequence=[C_AZUL])
                st.plotly_chart(fig3, use_container_width=True)

        with t_datos:
            st.dataframe(df_f, use_container_width=True, hide_index=True)

        with t_drive:
            if f_empresa and len(f_empresa) == 1:
                archivos = list_files_in_folder(f_empresa[0])
                if archivos:
                    for a in archivos: st.link_button(f"📂 Abrir {a['name']}", a['webViewLink'])
                else: st.warning("No se encontraron documentos.")
            else: st.info("Filtra una sola empresa para ver sus archivos.")

except Exception as e:
    st.error(f"Error de visualización: {e}")
