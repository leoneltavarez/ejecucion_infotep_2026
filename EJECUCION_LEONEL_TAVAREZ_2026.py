import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard INFOTEP - Leonel Tavarez", layout="wide")

# Estilo para KPIs con colores corporativos
st.markdown("""
    <style>
    .stMetric {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #0056b3;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    
    # 1. Limpieza de Fechas y Orden Cronológico
    df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
    df = df.sort_values(by='FECHA_INICIO', ascending=True)
    
    # 2. Limpieza de Numéricos (Sin decimales en visualización)
    columnas_num = ['HORAS_EJECUTADAS', 'TOTAL_ACCIONES', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
    for col in columnas_num:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Calcular Total Participantes
    df['PARTICIPANTES'] = df['OPERARIOS'] + df['MANDOS_MEDIOS'] + df['GERENTES']
    
    # Extraer Mes para el Slicer
    df['MES'] = df['FECHA_INICIO'].dt.month_name()
    
    return df

try:
    df_original = load_data()
    
    # --- BARRA LATERAL (SLICERS) ---
    st.sidebar.image("https://www.infotep.gob.do/images/logo.png", width=150) # Logo genérico INFOTEP
    st.sidebar.header("Filtros de Control")
    
    # Slicer de Estado
    filtro_estado = st.sidebar.multiselect("Estado de la Acción", options=df_original["ESTADO"].unique(), default=df_original["ESTADO"].unique())
    
    # Slicer de Empresa
    filtro_empresa = st.sidebar.multiselect("Seleccionar Empresa", options=df_original["EMPRESA"].unique())
    
    # Slicer de Mes
    filtro_mes = st.sidebar.multiselect("Mes de Inicio", options=df_original["MES"].unique())

    # Aplicar Filtros
    df = df_original[df_original["ESTADO"].isin(filtro_estado)]
    if filtro_empresa:
        df = df[df["EMPRESA"].isin(filtro_empresa)]
    if filtro_mes:
        df = df[df["MES"].isin(filtro_mes)]

    # --- NAVEGACIÓN POR PÁGINAS ---
    tabs = st.tabs(["📊 Dashboard Principal", "📋 Detalle de Datos"])

    with tabs[0]:
        st.title("Control de Ejecución Formativa")
        
        # KPIS con formato entero
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Horas Ejecutadas", f"{int(df['HORAS_EJECUTADAS'].sum()):,}")
        with col2:
            st.metric("Acciones Formativas", f"{int(df['TOTAL_ACCIONES'].sum()):,}")
        with col3:
            st.metric("Total Participantes", f"{int(df['PARTICIPANTES'].sum()):,}")

        # Gráfico Multivariable (Comparativa)
        st.subheader("Comparativa: Horas, Participantes y Acciones")
        df_chart = df.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
        
        fig = px.bar(
            df_chart, 
            x='EMPRESA', 
            y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'],
            barmode='group',
            color_discrete_map={
                'HORAS_EJECUTADAS': '#0056b3', # Azul INFOTEP
                'PARTICIPANTES': '#ffcc00',    # Mostaza/Naranja INFOTEP
                'TOTAL_ACCIONES': '#28a745'    # Verde
            }
        )
        st.plotly_chart(fig, use_container_width=True)

    with tabs[1]:
        st.subheader("Base de Datos Filtrada")
        
        # Mostrar tabla ordenada
        df_display = df.copy()
        df_display['FECHA_INICIO'] = df_display['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_display, use_container_width=True)

        # --- BOTONES DE EXPORTACIÓN ---
        st.markdown("### Exportar Reporte")
        col_btn1, col_btn2 = st.columns(2)
        
        # Exportar CSV
        csv = df.to_csv(index=False).encode('utf-8')
        col_btn1.download_button("Descargar en CSV", data=csv, file_name="reporte_leonel_tavarez.csv", mime="text/csv")
        
        # Exportar Excel (XLSX)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Ejecucion')
        col_btn2.download_button("Descargar en Excel", data=output.getvalue(), file_name="reporte_leonel_tavarez.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

except Exception as e:
    st.error(f"Se detectó un cambio en la estructura: {e}")