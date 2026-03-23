import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard INFOTEP - Leonel Tavarez", layout="wide")

# Estilo para KPIs y limpieza visual
st.markdown("""
    <style>
    .stMetric {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #0056b3;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    .block-container { padding-top: 2rem; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    
    # 1. ELIMINAR COLUMNAS "UNNAMED" (Limpieza de basura de Excel)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # 2. Limpieza de Fechas y Orden Cronológico
    df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
    df = df.sort_values(by='FECHA_INICIO', ascending=True)
    
    # 3. Limpieza de Numéricos
    columnas_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in columnas_num:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    df['MES'] = df['FECHA_INICIO'].dt.month_name()
    
    return df

try:
    df_original = load_data()
    
    # --- BARRA LATERAL (FILTROS) ---
    st.sidebar.title("🛠️ Panel de Control")
    st.sidebar.markdown("---")
    
    filtro_estado = st.sidebar.multiselect("Estado de la Acción", options=df_original["ESTADO"].unique(), default=df_original["ESTADO"].unique())
    filtro_empresa = st.sidebar.multiselect("Seleccionar Empresa", options=df_original["EMPRESA"].unique())
    filtro_mes = st.sidebar.multiselect("Mes de Inicio", options=df_original["MES"].unique())

    # Aplicar Filtros
    df = df_original[df_original["ESTADO"].isin(filtro_estado)]
    if filtro_empresa:
        df = df[df["EMPRESA"].isin(filtro_empresa)]
    if filtro_mes:
        df = df[df["MES"].isin(filtro_mes)]

    # --- NAVEGACIÓN ---
    tabs = st.tabs(["📊 Dashboard de Gestión", "📋 Detalle de Datos"])

    with tabs[0]:
        st.title("Control de Ejecución Formativa - INFOTEP")
        st.caption("Analítica de Datos | Diógenes Leonel Tavarez")
        
        # KPIS
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Horas Ejecutadas", f"{int(df['HORAS_EJECUTADAS'].sum()):,}")
        with col2:
            st.metric("Acciones Formativas", f"{int(df['TOTAL_ACCIONES'].sum()):,}")
        with col3:
            st.metric("Total Participantes", f"{int(df['PARTICIPANTES'].sum()):,}")

        st.markdown("---")
        
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("Comparativa de Ejecución")
            df_chart = df.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
            fig1 = px.bar(
                df_chart, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'],
                barmode='group',
                text_auto=True,
                color_discrete_map={'HORAS_EJECUTADAS': '#0056b3', 'PARTICIPANTES': '#ffcc00', 'TOTAL_ACCIONES': '#28a745'}
            )
            fig1.update_traces(textposition='outside')
            st.plotly_chart(fig1, use_container_width=True)

        with col_right:
            st.subheader("Composición de Participantes")
            df_stack = df.groupby('EMPRESA')[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(
                df_stack, x='EMPRESA', y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'],
                barmode='relative',
                text_auto=True,
                color_discrete_map={'OPERARIOS': '#0056b3', 'MANDOS_MEDIOS': '#ffcc00', 'GERENTES': '#e63946'}
            )
            st.plotly_chart(fig2, use_container_width=True)

    with tabs[1]:
        st.subheader("Base de Datos Limpia (Sin columnas extra)")
        df_display = df.copy()
        # Formatear fecha para la tabla
        df_display['FECHA_INICIO'] = df_display['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_display, use_container_width=True)

        # Exportación
        st.markdown("### 📥 Descargar Reporte")
        col_b1, col_b2 = st.columns(2)
        csv = df.to_csv(index=False).encode('utf-8')
        col_b1.download_button("Descargar CSV", data=csv, file_name="reporte_infotep.csv", mime="text/csv")
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        col_b2.download_button("Descargar Excel", data=output.getvalue(), file_name="reporte_infotep.xlsx")

except Exception as e:
    st.error(f"Error en el sistema: {e}")