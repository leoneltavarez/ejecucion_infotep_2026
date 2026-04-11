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

# --- CARGA Y UNIÓN DE DATOS (Nivel Superior) ---
@st.cache_data(ttl=0) 
def load_integrated_data():
    # 1. Base de Datos Principal (Leonel Tavarez 2026)
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/gviz/tq?tqx=out:csv"
    
    # 2. Archivo Académico (ID extraído de tu información)
    # IMPORTANTE: Asegúrate de que este ID sea el del ARCHIVO, no de la carpeta.
    ID_ACADEMICO = "1GGnNe6VuVl2gTKgMTXLm62lMWtkgJRwv" 
    url_acad = f"https://docs.google.com/spreadsheets/d/{ID_ACADEMICO}/gviz/tq?tqx=out:csv"
    
    try:
        df_base = pd.read_csv(url_base)
        df_acad = pd.read_csv(url_acad)

        # Limpieza de columnas para asegurar el match
        df_base.columns = [c.strip().upper() for c in df_base.columns]
        df_acad.columns = [c.strip().upper() for c in df_acad.columns]

        # Seleccionar solo Facilitador y Código del archivo Académico
        if 'CODIGO CURSO' in df_acad.columns and 'FACILITADOR' in df_acad.columns:
            df_acad_sub = df_acad[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
            # Unión (Merge)
            df_final = pd.merge(df_base, df_acad_sub, on='CODIGO CURSO', how='left')
        else:
            df_final = df_base
            st.warning("⚠️ No se pudo realizar la unión por 'CODIGO CURSO'.")

        # Formateo de fechas y limpieza de textos
        if 'FECHA_INICIO' in df_final.columns:
            df_final['FECHA_INICIO'] = pd.to_datetime(df_final['FECHA_INICIO'], dayfirst=True, errors='coerce')
            df_final = df_final.sort_values(by='FECHA_INICIO', ascending=True)

        # Conversión numérica
        cols_num = ['HORAS_EJECUTADAS', 'OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']
        for col in cols_num:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)
        
        df_final['PARTICIPANTES'] = df_final['OPERARIOS'] + df_final['MANDOS_MEDIOS'] + df_final['GERENTES']
        df_final['FACILITADOR'] = df_final['FACILITADOR'].fillna("POR ASIGNAR")
        
        return df_final
    except Exception as e:
        st.error(f"Error técnico en integración: {e}")
        return pd.DataFrame()

# --- INTERFAZ DE USUARIO ---
try:
    df_data = load_integrated_data()
    
    st.sidebar.title("🛠️ Filtros Maestros")
    
    if st.sidebar.button("🔄 Sincronizar Drive"):
        st.cache_data.clear()
        st.rerun()

    # Filtros laterales
    f_empresa = st.sidebar.multiselect("Empresa", sorted(df_data["EMPRESA"].unique()))
    f_facilitador = st.sidebar.multiselect("Facilitador", sorted(df_data["FACILITADOR"].unique()))
    f_accion = st.sidebar.multiselect("Acción Formativa", sorted(df_data["ACCION_FORMATIVA"].unique()))
    f_estado = st.sidebar.multiselect("Estado", sorted(df_data["ESTADO"].unique()), default=df_data["ESTADO"].unique())

    # Aplicar Filtros
    df_f = df_data[df_data["ESTADO"].isin(f_estado)]
    if f_empresa: df_f = df_f[df_f["EMPRESA"].isin(f_empresa)]
    if f_facilitador: df_f = df_f[df_f["FACILITADOR"].isin(f_facilitador)]
    if f_accion: df_f = df_f[df_f["ACCION_FORMATIVA"].isin(f_accion)]

    t_dash, t_data = st.tabs(["📊 Dashboard Integrado", "📋 Registro Maestro"])

    with t_dash:
        st.title("Control de Ejecución y Facilitadores 2026")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f'<div class="metric-container"><div class="metric-title">Horas</div><div class="metric-value">{int(df_f["HORAS_EJECUTADAS"].sum()):,}</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="metric-container"><div class="metric-title">Cursos</div><div class="metric-value">{len(df_f)}</div></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="metric-container"><div class="metric-title">Participantes</div><div class="metric-value">{int(df_f["PARTICIPANTES"].sum()):,}</div></div>', unsafe_allow_html=True)
        # Nueva métrica: Cantidad de facilitadores distintos en el filtro
        c4.markdown(f'<div class="metric-container"><div class="metric-title">Facilitadores</div><div class="metric-value">{df_f["FACILITADOR"].nunique()}</div></div>', unsafe_allow_html=True)

        st.divider()
        col_l, col_r = st.columns(2)
        
        with col_l:
            st.subheader("Ejecución Operativa")
            df_g1 = df_f.groupby('EMPRESA')[['HORAS_EJECUTADAS', 'PARTICIPANTES']].sum().reset_index()
            fig1 = px.bar(df_g1, x='EMPRESA', y=['HORAS_EJECUTADAS', 'PARTICIPANTES'], barmode='group', text_auto='d',
                          color_discrete_map={'HORAS_EJECUTADAS': COLOR_AZUL, 'PARTICIPANTES': COLOR_AMARILLO})
            st.plotly_chart(fig1, use_container_width=True)
            
        with col_r:
            st.subheader("Jerarquías por Facilitador/Empresa")
            # Este gráfico se adapta a lo que selecciones (si es empresa o facilitador)
            eje_x = 'FACILITADOR' if f_facilitador or not f_empresa else 'EMPRESA'
            df_g2 = df_f.groupby(eje_x)[['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES']].sum().reset_index()
            fig2 = px.bar(df_g2, x=eje_x, y=['OPERARIOS', 'MANDOS_MEDIOS', 'GERENTES'], barmode='stack', text_auto='d',
                          color_discrete_map={'OPERARIOS': COLOR_AZUL, 'MANDOS_MEDIOS': COLOR_AMARILLO, 'GERENTES': COLOR_ROJO})
            st.plotly_chart(fig2, use_container_width=True)

    with t_data:
        st.subheader("Detalle Cronológico con Facilitadores")
        
        # Botones de descarga
        d1, d2 = st.columns(2)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_f.to_excel(writer, index=False)
        d1.download_button("📥 Descargar Reporte Maestro (Excel)", output.getvalue(), "Reporte_Integrado.xlsx")
        d2.download_button("📄 Descargar CSV", df_f.to_csv(index=False).encode('utf-8'), "Reporte_Integrado.csv")
        
        st.divider()
        
        # Formato de visualización
        df_disp = df_f.copy()
        if 'FECHA_INICIO' in df_disp.columns:
            df_disp['FECHA_INICIO'] = df_disp['FECHA_INICIO'].dt.strftime('%d/%m/%Y')
        
        # Mostrar columnas clave primero
        columnas_ordenadas = ['FECHA_INICIO', 'EMPRESA', 'ACCION_FORMATIVA', 'FACILITADOR', 'PARTICIPANTES', 'ESTADO']
        cols_visibles = [c for c in columnas_ordenadas if c in df_disp.columns]
        st.dataframe(df_disp[cols_visibles], use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Error en la aplicación: {e}")
