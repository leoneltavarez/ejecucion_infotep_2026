import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO

# 1. Configuración de la página
st.set_page_config(page_title="Ejecución Leonel Tavarez 2026", layout="wide")

@st.cache_data
def load_data():
    SHEET_ID = "1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU"
    URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
    df = pd.read_csv(URL)
    
    df.columns = [c.strip() for c in df.columns]
    
    # Procesamiento de fechas
    df['FECHA_INICIO'] = pd.to_datetime(df['FECHA_INICIO'], dayfirst=True, errors='coerce')
    df['FECHA_TERMINO'] = pd.to_datetime(df['FECHA_TERMINO'], dayfirst=True, errors='coerce')
    
    # Nombre del mes para filtros
    df['Mes'] = df['FECHA_INICIO'].dt.month_name()
    
    # Limpieza numérica
    df['TOTAL_PTES'] = pd.to_numeric(df['TOTAL_PTES'], errors='coerce').fillna(0)
    df['HORAS_EJECUTADAS'] = pd.to_numeric(df['HORAS_EJECUTADAS'], errors='coerce').fillna(0)
    df['TOTAL_ACCIONES'] = pd.to_numeric(df['TOTAL_ACCIONES'], errors='coerce')
    
    return df

df = load_data()

# --- NAVEGACIÓN ---
st.sidebar.title("Navegación")
pagina = st.sidebar.radio("Ir a:", ["📊 Dashboard Ejecutivo", "📋 Base de Datos Completa"])

st.sidebar.markdown("---")
st.sidebar.header("Filtros")

estados = df['ESTADO'].dropna().unique()
estado_sel = st.sidebar.multiselect("Estado:", options=estados, default=estados)

meses = df['Mes'].dropna().unique()
mes_sel = st.sidebar.multiselect("Mes:", options=meses, default=meses)

empresas = sorted(df['EMPRESA'].unique())
emp_sel = st.sidebar.multiselect("Empresa:", options=empresas, default=empresas)

# Aplicar filtros
df_filtrado = df[
    (df['ESTADO'].isin(estado_sel)) & 
    (df['Mes'].isin(mes_sel)) & 
    (df['EMPRESA'].isin(emp_sel))
].copy()

# Formateo de fechas DD-MM-YYYY
df_filtrado['INICIO_FMT'] = df_filtrado['FECHA_INICIO'].dt.strftime('%d-%m-%Y')
df_filtrado['TERMINO_FMT'] = df_filtrado['FECHA_TERMINO'].dt.strftime('%d-%m-%Y')

if pagina == "📊 Dashboard Ejecutivo":
    st.title("💼 Dashboard de Ejecución Empresarial")
    
    if not df_filtrado.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Suma de Horas", f"{df_filtrado['HORAS_EJECUTADAS'].sum():,.1f}")
        c2.metric("Suma de Participantes", f"{df_filtrado['TOTAL_PTES'].sum():,.0f}")
        c3.metric("Acciones Formativas", f"{df_filtrado['TOTAL_ACCIONES'].count()}")

        st.markdown("---")
        
        st.subheader("📊 Resumen por Empresa")
        resumen_ejecutivo = df_filtrado[['EMPRESA', 'ACCION_FORMATIVA', 'INICIO_FMT', 'TERMINO_FMT', 'TOTAL_PTES', 'HORAS_EJECUTADAS']].copy()
        resumen_ejecutivo.columns = ['Empresa', 'Acción Formativa', 'Inicio', 'Término', 'Participantes', 'Horas']
        
        st.dataframe(resumen_ejecutivo, use_container_width=True, hide_index=True)
        
        fig = px.bar(df_filtrado.groupby('EMPRESA')['HORAS_EJECUTADAS'].sum().reset_index(), 
                     x='EMPRESA', y='HORAS_EJECUTADAS', text_auto=True, title="Horas por Empresa")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Sin datos para filtrar.")

elif pagina == "📋 Base de Datos Completa":
    st.title("📋 Registro Detallado")
    
    df_full_display = df_filtrado.copy()
    df_full_display['FECHA_INICIO'] = df_full_display['INICIO_FMT']
    df_full_display['FECHA_TERMINO'] = df_full_display['TERMINO_FMT']
    df_full_display = df_full_display.drop(columns=['INICIO_FMT', 'TERMINO_FMT', 'Mes'])
    
    st.dataframe(df_full_display, use_container_width=True, hide_index=True)
    
    st.markdown("### 📥 Exportar Datos")
    col_csv, col_excel = st.columns(2)
    
    # --- BOTÓN CSV ---
    with col_csv:
        csv_data = df_full_display.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Descargar en CSV",
            data=csv_data,
            file_name="ejecucion_leonel.csv",
            mime="text/csv"
        )
    
    # --- BOTÓN EXCEL ---
    with col_excel:
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_full_display.to_excel(writer, index=False, sheet_name='Ejecucion')
        st.download_button(
            label="Descargar en Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name="ejecucion_leonel.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )