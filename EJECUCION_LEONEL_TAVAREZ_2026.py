import streamlit as st
import pandas as pd
import plotly.express as px
import json
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- IDENTIDAD VISUAL INFOTEP ---
COLOR_AZUL = "#0056b3"
COLOR_AMARILLO = "#ffcc00"
COLOR_VERDE = "#28a745"
COLOR_ROJO = "#dc3545"

st.set_page_config(page_title="Dashboard Maestro - Leonel Tavarez", layout="wide")

# --- ESTILO PERSONALIZADO ---
st.markdown(f"""
    <style>
    .metric-container {{
        background-color: #f8f9fa;
        border-top: 5px solid {COLOR_AZUL};
        border-radius: 10px;
        padding: 20px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        text-align: center;
    }}
    .metric-title {{ color: #555; font-size: 1.1rem; font-weight: bold; }}
    .metric-value {{ color: {COLOR_AZUL}; font-size: 2.2rem; font-weight: bold; }}
    </style>
""", unsafe_allow_html=True)

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

# --- CARGA E INTEGRACIÓN DE DATOS ---
@st.cache_data(ttl=0) 
def load_integrated_data():
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    ID_ACADEMICO = "1DamhAcTIll23Op6JyQvJYvSjKeaCmx8f_FmkKDp1UXE"
    url_acad = f"https://docs.google.com/spreadsheets/d/{ID_ACADEMICO}/gviz/tq?tqx=out:csv"
    
    try:
        df_base = pd.read_csv(url_base)
        df_base.columns = [c.strip().upper() for c in df_base.columns]
        
        try:
            df_acad = pd.read_csv(url_acad)
            df_acad.columns = [c.strip().upper() for c in df_acad.columns]
            if 'CODIGO CURSO' in df_acad.columns and 'FACILITADOR' in df_acad.columns:
                df_acad_sub = df_acad[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
                df_final = pd.merge(df_base, df_acad_sub, on='CODIGO CURSO', how='left')
            else:
                df_final = df_base
        except:
            df_final = df_base

        if 'FECHA_INICIO' in df_final.columns:
            df_final['FECHA_INICIO'] = pd.to_datetime(df_final['FECHA_INICIO'], dayfirst=True, errors='coerce')
            df_final = df_final.sort_values(by='FECHA_INICIO', ascending=True)

        cols_num = ['HORAS_EJECUTADAS', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
        for col in cols_num:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)
        
        df_final['PARTICIPANTES'] = df_final['OPERARIOS'] + df_final['MANDOS_MEDIOS'] + df_final['GERENTES']
        df_final['FACILITADOR'] = df_final['FACILITADOR'].fillna("POR ASIGNAR")
        
        return df_final
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
try:
    df_data = load_integrated_data()
    
    st.sidebar.title("🛠️ Filtros Maestros")
    if st.sidebar.button("🔄 Sincronizar Datos"):
        st.cache_data.clear()
        st.rerun()

    f_empresa_list = sorted(df_data["EMPRESA"].unique())
    f_empresa = st.sidebar.multiselect("Empresa", f_empresa_list)
    f_facilitador = st.sidebar.multiselect("Facilitador", sorted(df_data["FACILITADOR"].unique()))
    f_accion = st.sidebar.multiselect("Acción Formativa", sorted(df_data["ACCION_FORMATIVA"].unique()))
    f_estado = st.sidebar.multiselect("Estado", sorted(df_data["ESTADO"].unique()), default=df_data["ESTADO"].unique())

    # Aplicar Filtros
    df_f = df_data[df_data["ESTADO"].isin(f_estado)]
    if f_empresa: df_f = df_f[df_f["EMPRESA"].isin(f_empresa)]
    if f_facilitador: df_f = df_f[df_f["FACILITADOR"].isin(f_facilitador)]
    if f_accion: df_f = df_f[df_f["ACCION_FORMATIVA"].isin(f_accion)]

    t_dash, t_tabla, t_drive = st.tabs(["📊 Dashboard", "📋 Registro Datos", "📂 Repositorio Drive"])

    with t_dash:
        st.title("Control Integrado INFOTEP 2026")
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f'<div class="metric-container"><div class="metric-title">Horas</div><div class="metric-value">{int(df_f["HORAS_EJECUTADAS"].sum()):,}</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="metric-container"><div class="metric-title">Cursos</div><div class="metric-value">{len(df_f)}</div></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="metric-container"><div class="metric-title">Participantes</div><div class="metric-value">{int(df_f["PARTICIPANTES"].sum()):,}</div></div>', unsafe_allow_html=True)
        c4.markdown(f'<div class="metric-container"><div class="metric-title">Facilitadores</div><div class="metric-value">{df_f["FACILITADOR"].nunique()}</div></div>', unsafe_allow_html=True)

        st.divider()
        
        # FILA 1 DE GRÁFICOS
        col_1a, col_1b = st.columns(2)
        with col_1a:
            st.subheader("1. Ejecución: Horas, Participantes y Cursos")
            # Agregamos la columna para contar acciones
            df_g1 = df_f.copy()
            df_g1['ACCIONES_FORMATIVAS'] = 1
            df_g1 = df_g1.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'ACCIONES_FORMATIVAS']].sum().reset_index()
            
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'ACCIONES_FORMATIVAS'], 
                          barmode='group', text_auto='d',
                          color_discrete_map={
                              'HORAS_EJECUTADAS': COLOR_AZUL, 
                              'PARTICIPANTES': COLOR_AMARILLO,
                              'ACCIONES_FORMATIVAS': COLOR_VERDE
                          })
            st.plotly_chart(fig1, use_container_width=True)
            
        with col_1b:
            st.subheader("2. Distribución de Niveles Jerárquicos")
            df_g2 = df_f.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], barmode='stack', text_auto='d',
                          color_discrete_map={'OPERARIOS': COLOR_AZUL, 'MANDOS_MEDIOS': COLOR_AMARILLO, 'GERENTES': COLOR_ROJO})
            st.plotly_chart(fig2, use_container_width=True)

        # FILA 2 DE GRÁFICOS
        st.divider()
        st.subheader("3. Productividad por Facilitador")
        df_g3 = df_f.groupby('FACILITADOR').size().reset_index(name='TOTAL_CURSOS')
        fig3 = px.bar(df_g3, x='FACILITADOR', y='TOTAL_CURSOS', text_auto=True,
                      color_discrete_sequence=[COLOR_AZUL])
        st.plotly_chart(fig3, use_container_width=True)

    with t_tabla:
        # Descargas y Tabla igual que antes
        d1, d2 = st.columns(2)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_f.to_excel(writer, index=False)
        d1.download_button("📥 Descargar Excel", output.getvalue(), "Reporte_Completo.xlsx")
        d2.download_button("📄 Descargar CSV", df_f.to_csv(index=False).encode('utf-8'), "Reporte_Completo.csv")
        
        df_disp = df_f.copy()
        if 'FECHA_INICIO' in df_disp.columns:
            df_disp['FECHA_INICIO'] = df_disp['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_disp, use_container_width=True, hide_index=True)

    with t_drive:
        # Repositorio Drive igual que antes
        st.subheader("Acceso a Documentos en Drive")
        if f_empresa and len(f_empresa) == 1:
            archivos = list_files_in_folder(f_empresa[0])
            if archivos:
                for a in archivos:
                    col_f, col_l = st.columns([4, 1])
                    col_f.write(f"📄 {a['name']}")
                    col_l.link_button("Abrir", a['webViewLink'])
            else:
                st.warning("No hay archivos para esta empresa.")
        else:
            st.info("Selecciona UNA empresa en el filtro lateral para ver sus archivos.")

except Exception as e:
    st.error(f"Error: {e}")
