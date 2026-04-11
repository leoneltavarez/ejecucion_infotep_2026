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

# --- PROCESAMIENTO DE DATOS ---
@st.cache_data(ttl=0)
def load_and_merge_data():
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/export?format=csv"
    url_acad = "https://docs.google.com/spreadsheets/d/1DamhAcTIll23Op6JyQvJYvSjKeaCmx8f_FmkKDp1UXE/export?format=csv"
    
    try:
        df_b = pd.read_csv(url_base)
        df_a = pd.read_csv(url_acad)

        df_b.columns = [c.strip().upper().replace("_", " ") for c in df_b.columns]
        df_a.columns = [c.strip().upper().replace("_", " ") for c in df_a.columns]
        
        df_b['CODIGO CURSO'] = df_b['CODIGO CURSO'].astype(str).str.strip()
        df_a['CODIGO CURSO'] = df_a['CODIGO CURSO'].astype(str).str.strip()
        
        if 'FACILITADOR' in df_a.columns:
            df_a_sub = df_a[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
            df_final = pd.merge(df_b, df_a_sub, on='CODIGO CURSO', how='left')
        else:
            df_final = df_b

        # REGLA DE NEGOCIO: Solo Iniciado y Cerrado
        df_final['ESTADO'] = df_final['ESTADO'].astype(str).str.capitalize().str.strip()
        df_final = df_final[df_final['ESTADO'].isin(['Iniciado', 'Cerrado'])]

        # Limpieza de textos
        for col in ['EMPRESA', 'FACILITADOR', 'ACCION FORMATIVA']:
            if col in df_final.columns:
                df_final[col] = df_final[col].fillna("No Definido").astype(str).str.strip()

        # Números
        cols_num = ['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES', 'HORAS EJECUTADAS']
        for col in cols_num:
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)

        df_final['PARTICIPANTES'] = df_final['OPERARIOS'] + df_final['MANDOS MEDIOS'] + df_final['GERENTES']
        
        return df_final
    except Exception as e:
        st.error(f"Error en datos: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
df = load_and_merge_data()

if not df.empty:
    st.sidebar.header("🛠️ Filtros Inteligentes")
    
    # --- LÓGICA DE FILTROS EN CASCADA ---
    # 1. Filtro de Empresa primero
    lista_empresas = sorted(df['EMPRESA'].unique().tolist())
    f_empresa = st.sidebar.multiselect("Empresa", lista_empresas)

    # 2. El resto de datos depende de la empresa seleccionada
    df_temp = df[df['EMPRESA'].isin(f_empresa)] if f_empresa else df

    # 3. Filtros dependientes
    lista_cursos = sorted(df_temp['ACCION FORMATIVA'].unique().tolist())
    f_curso = st.sidebar.multiselect("Acción Formativa", lista_cursos)
    
    lista_facilitadores = sorted(df_temp['FACILITADOR'].unique().tolist())
    f_facilitador = st.sidebar.multiselect("Facilitador", lista_facilitadores)
    
    lista_estados = sorted(df_temp['ESTADO'].unique().tolist())
    f_estado = st.sidebar.multiselect("Estado", lista_estados, default=lista_estados)

    # Aplicación final de filtros
    df_f = df_temp[df_temp['ESTADO'].isin(f_estado)]
    if f_curso: df_f = df_f[df_f['ACCION FORMATIVA'].isin(f_curso)]
    if f_facilitador: df_f = df_f[df_f['FACILITADOR'].isin(f_facilitador)]

    t1, t2, t3 = st.tabs(["📊 Dashboard", "📋 Tabla de Datos", "📂 Repositorio"])

    with t1:
        st.title("Gestión Leonel Tavarez 2026")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Horas", f"{df_f['HORAS EJECUTADAS'].sum():,}")
        with c2: st.metric("Participantes", f"{df_f['PARTICIPANTES'].sum():,}")
        with c3: st.metric("Cursos", f"{len(df_f):,}")
        with c4: st.metric("Empresas", f"{df_f['EMPRESA'].nunique()}")

        st.markdown("---")
        
        st.subheader("Alcance por Empresa")
        df_g1 = df_f.groupby('EMPRESA')[['HORAS EJECUTADAS', 'PARTICIPANTES']].sum().reset_index()
        fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS EJECUTADAS', 'PARTICIPANTES'], barmode='group', text_auto='.2s',
                      color_discrete_map={'HORAS EJECUTADAS': C_AZUL, 'PARTICIPANTES': C_AMARILLO})
        st.plotly_chart(fig1, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Niveles Jerárquicos")
            df_g2 = df_f.groupby('EMPRESA')[['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES'], barmode='stack',
                          color_discrete_map={'OPERARIOS': C_AZUL, 'MANDOS MEDIOS': C_AMARILLO, 'GERENTES': C_ROJO})
            st.plotly_chart(fig2, use_container_width=True)
        with col_b:
            st.subheader("Facilitadores por Empresa")
            # Este es el gráfico que te gusta: muestra cuántas acciones dio cada facilitador en lo filtrado
            df_g3 = df_f.groupby(['FACILITADOR', 'EMPRESA']).size().reset_index(name='ACCIONES')
            fig3 = px.bar(df_g3, x='FACILITADOR', y='ACCIONES', color='EMPRESA', text_auto=True,
                          color_discrete_sequence=px.colors.qualitative.Prism)
            st.plotly_chart(fig3, use_container_width=True)

    with t2:
        st.subheader("Búsqueda y Detalle de Acciones")
        # Filtro de búsqueda interno en la tabla (ideal para buscar facilitadores rápido)
        busqueda = st.text_input("🔍 Escribe para buscar (Facilitador, Curso, etc.):")
        if busqueda:
            df_t = df_f[df_f.apply(lambda row: busqueda.lower() in row.astype(str).str.lower().values, axis=1)]
        else:
            df_t = df_f
        st.dataframe(df_t, use_container_width=True, hide_index=True)

    with t3:
        if f_empresa and len(f_empresa) == 1:
            archivos = list_files_in_folder(f_empresa[0])
            for a in archivos: st.link_button(f"📄 {a['name']}", a['webViewLink'])
        else: st.info("Selecciona una sola empresa para ver sus archivos.")
