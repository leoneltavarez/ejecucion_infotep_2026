import streamlit as st
import pandas as pd
import plotly.express as px

# Configuración de página con colores de INFOTEP
st.set_page_config(page_title="Dashboard Ejecución Leonel Tavarez", layout="wide")

# Estilo personalizado para los indicadores (Kpis)
st.markdown("""
    <style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #0056b3;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    # Tu URL de Google Sheets
    url = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    
    # 1. Limpieza y Formato de Fechas
    df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], errors='coerce')
    
    # 2. Ordenar por fecha (Menor a Mayor)
    df = df.sort_values(by='FECHA_INICIO', ascending=True)
    
    # Limpieza de numéricos para evitar errores
    df['HORAS_EJECUTADAS'] = pd.to_numeric(df['HORAS_EJECUTADAS'], errors='coerce').fillna(0)
    df['TOTAL_ACCIONES'] = pd.to_numeric(df['TOTAL_ACCIONES'], errors='coerce').fillna(0)
    # Asumiendo que 'OPERARIOS', 'MANDOS_MEDIOS' y 'GERENTES' sumados son los participantes
    df['PARTICIPANTES'] = pd.to_numeric(df['OPERARIOS'], errors='coerce').fillna(0) + \
                          pd.to_numeric(df['MANDOS_MEDIOS'], errors='coerce').fillna(0) + \
                          pd.to_numeric(df['GERENTES'], errors='coerce').fillna(0)
    
    return df

try:
    df = load_data()

    st.title("📊 Control de Acciones Formativas - INFOTEP")
    st.subheader(f"Gestión: Diógenes Leonel Tavarez")

    # --- FILTROS ---
    empresa = st.sidebar.multiselect("Filtrar por Empresa", options=df["EMPRESA"].unique())
    if empresa:
        df = df[df["EMPRESA"].isin(empresa)]

    # --- KPIS PRINCIPALES ---
    col1, col2, col3 = st.columns(3)
    
    total_horas = int(df['HORAS_EJECUTADAS'].sum())
    total_acciones = int(df['TOTAL_ACCIONES'].sum())
    total_participantes = int(df['PARTICIPANTES'].sum())

    with col1:
        st.metric("Total Horas", f"{total_horas}")
    with col2:
        st.metric("Acciones Formativas", f"{total_acciones}")
    with col3:
        st.metric("Total Participantes", f"{total_participantes}")

    # --- GRÁFICO COMPARATIVO ---
    st.markdown("### Comparativa por Empresa (Horas vs Participantes vs Acciones)")
    
    # Agrupamos datos para el gráfico
    df_chart = df.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES']].sum().reset_index()
    
    fig = px.bar(
        df_chart, 
        x='EMPRESA', 
        y=['HORAS_EJECUTADAS', 'PARTICIPANTES', 'TOTAL_ACCIONES'],
        barmode='group',
        title="Análisis de Variables por Empresa",
        color_discrete_map={
            'HORAS_EJECUTADAS': '#0056b3', # Azul Infotep
            'PARTICIPANTES': '#ffcc00',    # Amarillo/Naranja Infotep
            'TOTAL_ACCIONES': '#28a745'    # Verde éxito
        }
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- TABLA DE DATOS ORDENADA ---
    st.markdown("### Detalle de Ejecución (Ordenado por Fecha)")
    # Formateamos la fecha para que se vea bonita en la tabla
    df_display = df.copy()
    df_display['FECHA_INICIO'] = df_display['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
    st.dataframe(df_display, use_container_width=True)

except Exception as e:
    st.error(f"Error al cargar los datos: {e}")
    st.info("Asegúrate de que las columnas en Google Sheets se llamen exactamente: EMPRESA, FECHA_INICIO, HORAS_EJECUTADAS, TOTAL_ACCIONES, OPERARIOS, MANDOS_MEDIOS, GERENTES")