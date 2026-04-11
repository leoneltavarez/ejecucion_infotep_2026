import streamlit as st
import pandas as pd
import plotly.express as px
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURACIÓN ESTÉTICA ---
C_AZUL, C_AMARILLO, C_VERDE, C_ROJO = "#0056b3", "#ffcc00", "#28a745", "#dc3545"
st.set_page_config(page_title="Dashboard Maestro - Leonel Tavarez", layout="wide")

# --- CONEXIÓN DRIVE ---
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

# --- MOTOR DE DATOS (UNIÓN Y LIMPIEZA) ---
@st.cache_data(ttl=0)
def load_and_merge_data():
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/export?format=csv"
    url_acad = "https://docs.google.com/spreadsheets/d/1DamhAcTIll23Op6JyQvJYvSjKeaCmx8f_FmkKDp1UXE/export?format=csv"
    
    try:
        df_b = pd.read_csv(url_base)
        df_a = pd.read_csv(url_acad)

        # 1. Estandarizar encabezados
        df_b.columns = [c.strip().upper().replace("_", " ") for c in df_b.columns]
        df_a.columns = [c.strip().upper().replace("_", " ") for c in df_a.columns]
        
        # 2. Limpieza de llaves de unión (Código Curso)
        df_b['CODIGO CURSO'] = df_b['CODIGO CURSO'].astype(str).str.strip()
        df_a['CODIGO CURSO'] = df_a['CODIGO CURSO'].astype(str).str.strip()
        
        # 3. Merge (Unión)
        if 'FACILITADOR' in df_a.columns:
            df_a_sub = df_a[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
            df_final = pd.merge(df_b, df_a_sub, on='CODIGO CURSO', how='left')
        else:
            df_final = df_b

        # 4. LIMPIEZA ANT-ERROR CRÍTICA: Forzar STR y quitar NaNs
        columnas_filtro = ['EMPRESA', 'FACILITADOR', 'ESTADO', 'ACCION FORMATIVA']
        for col in columnas_filtro:
            if col in df_final.columns:
                # Convertimos a string y reemplazamos los nulos de pandas por un texto válido
                df_final[col] = df_final[col].fillna("SIN ESPECIFICAR").astype(str).str.strip()
                # Eliminar registros que pandas lee como 'nan' (texto)
                df_final[col] = df_final[col].replace(['nan', 'None', 'NaN'], 'SIN ESPECIFICAR')

        # 5. Asegurar números para KPIs y Gráficos
        cols_num = ['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES', 'HORAS EJECUTADAS']
        for col in cols_num:
            if col not in df_final.columns: df_final[col] = 0
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)

        df_final['PARTICIPANTES'] = df_final['OPERARIOS'] + df_final['MANDOS MEDIOS'] + df_final['GERENTES']
        
        return df_final
    except Exception as e:
        st.error(f"Error en carga: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
try:
    df = load_and_merge_data()
    
    if not df.empty:
        # SIDEBAR
        st.sidebar.header("🛠️ Filtros")
        
        # Función para opciones ordenadas que garantiza que todo es texto
        def get_safe_opts(col):
            opts = [str(x) for x in df[col].unique()]
            return sorted(opts)

        f_empresa = st.sidebar.multiselect("Empresa", get_safe_opts("EMPRESA"))
        f_curso = st.sidebar.multiselect("Acción Formativa", get_safe_opts("ACCION FORMATIVA"))
        f_facilitador = st.sidebar.multiselect("Facilitador", get_safe_opts("FACILITADOR"))
        
        opts_estado = get_safe_opts("ESTADO")
        f_estado = st.sidebar.multiselect("Estado", opts_estado, default=opts_estado)

        # Aplicar filtros
        df_f = df[df["ESTADO"].isin(f_estado)]
        if f_empresa: df_f = df_f[df_f["EMPRESA"].isin(f_empresa)]
        if f_curso: df_f = df_f[df_f["ACCION FORMATIVA"].isin(f_curso)]
        if f_facilitador: df_f = df_f[df_f["FACILITADOR"].isin(f_facilitador)]

        # TABS
        t1, t2, t3 = st.tabs(["📊 Dashboard Maestro", "📋 Tabla de Datos", "📂 Repositorio Drive"])

        with t1:
            st.title("Gestión de Capacitación Leonel Tavarez 2026")
            
            # KPIs - CUADROS DE TEXTO (INDICADORES)
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("Total Horas", f"{df_f['HORAS EJECUTADAS'].sum():,}")
            with c2: st.metric("Participantes", f"{df_f['PARTICIPANTES'].sum():,}")
            with c3: st.metric("Acciones Formativas", f"{len(df_f):,}")
            with c4: st.metric("Empresas Impactadas", f"{df_f['EMPRESA'].nunique()}")

            st.markdown("---")

            # Gráficos
            st.subheader("1. Alcance Operativo por Empresa")
            df_g1 = df_f.copy()
            df_g1['CURSOS'] = 1
            df_g1 = df_g1.groupby('EMPRESA')[['HORAS EJECUTADAS', 'PARTICIPANTES', 'CURSOS']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS EJECUTADAS', 'PARTICIPANTES', 'CURSOS'], barmode='group', text_auto='d',
                          color_discrete_map={'HORAS EJECUTADAS': C_AZUL, 'PARTICIPANTES': C_AMARILLO, 'CURSOS': C_VERDE})
            st.plotly_chart(fig1, use_container_width=True)

            cola, colb = st.columns(2)
            with cola:
                st.subheader("2. Distribución de Niveles")
                df_g2 = df_f.groupby('EMPRESA')[['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']].sum().reset_index()
                fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES'], barmode='stack', text_auto='d',
                              color_discrete_map={'OPERARIOS': C_AZUL, 'MANDOS MEDIOS': C_AMARILLO, 'GERENTES': C_ROJO})
                st.plotly_chart(fig2, use_container_width=True)
            with colb:
                st.subheader("3. Acciones por Facilitador")
                df_g3 = df_f.groupby('FACILITADOR').size().reset_index(name='TOTAL')
                fig3 = px.bar(df_g3, x='FACILITADOR', y='TOTAL', text_auto=True, color_discrete_sequence=[C_AZUL])
                st.plotly_chart(fig3, use_container_width=True)

        with t2:
            st.subheader("Visualización General de Datos")
            st.dataframe(df_f, use_container_width=True, hide_index=True)

        with t3:
            if f_empresa and len(f_empresa) == 1:
                docs = list_files_in_folder(f_empresa[0])
                if docs:
                    for d in docs: st.link_button(f"📄 Abrir {d['name']}", d['webViewLink'])
                else: st.warning("No hay archivos registrados.")
            else: st.info("Selecciona una empresa en el filtro para ver sus archivos.")

except Exception as e:
    st.error(f"Error Técnico Detetado: {e}")
