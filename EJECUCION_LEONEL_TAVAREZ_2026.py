import streamlit as st
import pandas as pd
import plotly.express as px
import json
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- ESTÉTICA CORPORATIVA ---
C_AZUL, C_AMARILLO, C_VERDE, C_ROJO = "#0056b3", "#ffcc00", "#28a745", "#dc3545"

st.set_page_config(page_title="Dashboard Maestro - Leonel Tavarez", layout="wide")

# --- CONFIGURACIÓN DRIVE (PARA PESTAÑA DE ARCHIVOS) ---
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

# --- CARGA E INTEGRACIÓN DE DOCUMENTOS ---
@st.cache_data(ttl=0)
def load_and_merge_data():
    # URLs de exportación CSV (Ahora accesibles por ser públicas)
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/export?format=csv"
    url_acad = "https://docs.google.com/spreadsheets/d/1DamhAcTIll23Op6JyQvJYvSjKeaCmx8f_FmkKDp1UXE/export?format=csv"
    
    try:
        # 1. Leer Base de Datos
        df_b = pd.read_csv(url_base)
        # Limpiar encabezados: TODO_A_MAYUSCULAS y sin espacios/guiones
        df_b.columns = [c.strip().upper().replace("_", " ") for c in df_b.columns]
        
        # 2. Leer Archivo Académico
        df_a = pd.read_csv(url_acad)
        df_a.columns = [c.strip().upper().replace("_", " ") for c in df_a.columns]
        
        # 3. Preparar llave de unión (Código Curso)
        df_b['CODIGO CURSO'] = df_b['CODIGO CURSO'].astype(str).str.strip()
        df_a['CODIGO CURSO'] = df_a['CODIGO CURSO'].astype(str).str.strip()
        
        # 4. Cruzar datos para traer al FACILITADOR
        if 'FACILITADOR' in df_a.columns:
            df_a_sub = df_a[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
            df_final = pd.merge(df_b, df_a_sub, on='CODIGO CURSO', how='left')
        else:
            df_final = df_b

        # 5. Normalizar columnas numéricas para los gráficos
        cols_graficos = ['HORAS EJECUTADAS', 'OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']
        for col in cols_graficos:
            if col not in df_final.columns: df_final[col] = 0
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)

        df_final['PARTICIPANTES'] = df_final['OPERARIOS'] + df_final['MANDOS MEDIOS'] + df_final['GERENTES']
        df_final['FACILITADOR'] = df_final.get('FACILITADOR', 'POR ASIGNAR').fillna('SIN ASIGNAR')
        
        return df_final
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame()

# --- INTERFAZ DE USUARIO ---
try:
    df = load_and_merge_data()
    
    if not df.empty:
        st.sidebar.header("🛠️ Panel de Control")
        f_empresa = st.sidebar.multiselect("Seleccionar Empresa", sorted(df["EMPRESA"].unique()))
        f_facilitador = st.sidebar.multiselect("Seleccionar Facilitador", sorted(df["FACILITADOR"].unique()))
        f_estado = st.sidebar.multiselect("Estado", sorted(df["ESTADO"].unique()), default=df["ESTADO"].unique())

        # Aplicar Filtros
        df_f = df[df["ESTADO"].isin(f_estado)]
        if f_empresa: df_f = df_f[df_f["EMPRESA"].isin(f_empresa)]
        if f_facilitador: df_f = df_f[df_f["FACILITADOR"].isin(f_facilitador)]

        tab1, tab2, tab3 = st.tabs(["📊 Dashboard de Gestión", "📋 Registro de Datos", "📂 Documentos Drive"])

        with tab1:
            st.title("Control Integrado de Capacitación 2026")
            
            # GRÁFICO 1: EL ALCANCE TOTAL
            st.subheader("1. Resumen de Ejecución (Horas, Participantes y Cursos)")
            df_g1 = df_f.copy()
            df_g1['CANTIDAD CURSOS'] = 1
            df_g1 = df_g1.groupby('EMPRESA')[['HORAS EJECUTADAS', 'PARTICIPANTES', 'CANTIDAD CURSOS']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS EJECUTADAS', 'PARTICIPANTES', 'CANTIDAD CURSOS'], 
                          barmode='group', text_auto='d',
                          color_discrete_map={'HORAS EJECUTADAS': C_AZUL, 'PARTICIPANTES': C_AMARILLO, 'CANTIDAD CURSOS': C_VERDE})
            st.plotly_chart(fig1, use_container_width=True)

            col_izq, col_der = st.columns(2)
            with col_izq:
                # GRÁFICO 2: NIVELES (Vuelve tu gráfico de barras apiladas)
                st.subheader("2. Distribución por Nivel Jerárquico")
                df_g2 = df_f.groupby('EMPRESA')[['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']].sum().reset_index()
                fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES'], barmode='stack', text_auto='d',
                              color_discrete_map={'OPERARIOS': C_AZUL, 'MANDOS MEDIOS': C_AMARILLO, 'GERENTES': C_ROJO})
                st.plotly_chart(fig2, use_container_width=True)
            
            with col_der:
                # GRÁFICO 3: FACILITADORES
                st.subheader("3. Acciones por Facilitador")
                df_g3 = df_f.groupby('FACILITADOR').size().reset_index(name='TOTAL')
                fig3 = px.bar(df_g3, x='FACILITADOR', y='TOTAL', text_auto=True, color_discrete_sequence=[C_AZUL])
                st.plotly_chart(fig3, use_container_width=True)

        with tab2:
            st.subheader("Detalle de las Acciones Formativas")
            st.dataframe(df_f, use_container_width=True, hide_index=True)

        with tab3:
            st.subheader("Repositorio Digital")
            if f_empresa and len(f_empresa) == 1:
                docs = list_files_in_folder(f_empresa[0])
                if docs:
                    for d in docs: st.link_button(f"📄 Ver {d['name']}", d['webViewLink'])
                else: st.warning("No hay archivos para esta empresa en el Drive.")
            else: st.info("Por favor, selecciona una (1) empresa en el filtro para ver sus documentos.")

except Exception as e:
    st.error(f"Ocurrió un error inesperado: {e}")
