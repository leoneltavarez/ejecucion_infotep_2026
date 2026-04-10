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

st.set_page_config(page_title="Dashboard INFOTEP - Leonel Tavarez", layout="wide")

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
    .metric-title {{ color: #555; font-size: 1.2rem; margin-bottom: 10px; font-weight: bold; }}
    .metric-value {{ color: {COLOR_AZUL}; font-size: 2.5rem; font-weight: bold; }}
    </style>
""", unsafe_allow_html=True)

# --- CONFIGURACIÓN DRIVE (MANTENIDA) ---
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

# --- CARGA Y ORDENAMIENTO DE DATOS ---
@st.cache_data(ttl=0) 
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    for col in ['EMPRESA', 'ESTADO', 'ACCION_FORMATIVA']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    
    # ORDENAR POR FECHA (Lógica interna)
    if 'FECHA_INICIO' in df.columns:
        df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
        df = df.sort_values(by='FECHA_INICIO', ascending=True)

    columnas_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in columnas_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    return df

try:
    df_orig = load_data()
    st.sidebar.title("🛠️ Panel de Control")
    
    if st.sidebar.button("🔄 Sincronizar Base de Datos"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.subheader("🔍 Filtros de Reporte")
    f_empresa = st.sidebar.multiselect("Empresa(s)", options=sorted(df_orig["EMPRESA"].unique()))
    f_estado = st.sidebar.multiselect("Estado(s)", options=sorted(df_orig["ESTADO"].unique()), default=df_orig["ESTADO"].unique())
    
    df_v = df_orig[df_orig["ESTADO"].isin(f_estado)]
    if f_empresa:
        df_v = df_v[df_v["EMPRESA"].isin(f_empresa)]
    
    lista_acciones = sorted(df_v["ACCION_FORMATIVA"].unique())
    f_accion = st.sidebar.multiselect("Acción Formativa", options=lista_acciones)

    if f_accion:
        df_v = df_v[df_v["ACCION_FORMATIVA"].isin(f_accion)]

    t_dash, t_data, t_drive = st.tabs(["📊 Dashboard Ejecutivo", "📋 Tabla de Datos", "📂 Repositorio Drive"])

    with t_dash:
        st.title("Control de Ejecución 2026")
        
        # Métrica de Cursos: Si hay filtro, cuenta las filas resultantes
        total_acciones_conteo = len(df_v)
        h_total = f"{int(df_v['HORAS_EJECUTADAS'].sum()):,}"
        p_total = f"{int(df_v['PARTICIPANTES'].sum()):,}"

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="metric-container"><div class="metric-title">Horas Ejecutadas</div><div class="metric-value">{h_total}</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="metric-container"><div class="metric-title">Total Cursos</div><div class="metric-value">{total_acciones_conteo}</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="metric-container"><div class="metric-title">Participantes</div><div class="metric-value">{p_total}</div></div>', unsafe_allow_html=True)
        
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Alcance Operativo")
            # Agregamos una columna auxiliar para contar las filas en el gráfico
            df_g1 = df_v.copy()
            df_g1['CANTIDAD_CURSOS'] = 1
            df_g1 = df_g1.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'CANTIDAD_CURSOS']].sum().reset_index()
            
            # Ajuste del gráfico para incluir la CANTIDAD_CURSOS (el "2" que mencionas)
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'CANTIDAD_CURSOS'], 
                          barmode='group', text_auto='d',
                          color_discrete_map={
                              'HORAS_EJECUTADAS': COLOR_AZUL, 
                              'PARTICIPANTES': COLOR_AMARILLO,
                              'CANTIDAD_CURSOS': COLOR_VERDE
                          })
            st.plotly_chart(fig1, use_container_width=True)
            
        with col2:
            st.subheader("Niveles Jerárquicos")
            df_g2 = df_v.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], barmode='stack', text_auto='d',
                          color_discrete_map={'OPERARIOS': COLOR_AZUL, 'MANDOS_MEDIOS': COLOR_AMARILLO, 'GERENTES': COLOR_ROJO})
            st.plotly_chart(fig2, use_container_width=True)

    with t_data:
        st.subheader("📋 Detalle de Acciones (Orden Cronológico)")
        
        d_c1, d_c2 = st.columns(2)
        # Para la descarga, mantenemos el dataframe original pero ordenado
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_v.to_excel(writer, index=False, sheet_name='Reporte')
        d_c1.download_button("📥 Descargar Excel", output.getvalue(), "Reporte_INFOTEP.xlsx")
        d_c2.download_button("📄 Descargar CSV", df_v.to_csv(index=False).encode('utf-8'), "Reporte_INFOTEP.csv")
        
        st.divider()
        
        # --- MEJORA: FORMATO DE FECHA PARA VISUALIZACIÓN ---
        df_display = df_v.copy()
        if 'FECHA_INICIO' in df_display.columns:
            # Convertimos a string con formato día/mes/año para la tabla
            df_display['FECHA_INICIO'] = df_display['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ... (Resto del código de Drive se mantiene igual)
except Exception as e:
    st.error(f"Error técnico: {e}")
