import streamlit as st
import pandas as pd
import plotly.express as px
import json
from datetime import datetime, date
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURACIÓN Y ESTÉTICA INFOTEP ---
C_AZUL, C_AMARILLO, C_VERDE, C_ROJO = "#0056b3", "#ffcc00", "#28a745", "#dc3545"
st.set_page_config(page_title="Gestión Leonel Tavarez 2026", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetric"] {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #0056b3;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .total-row-box {
        background-color: #0056b3;
        color: white;
        padding: 12px 18px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 15px;
        margin-top: 6px;
        display: flex;
        gap: 40px;
    }
    .total-item { display: flex; flex-direction: column; }
    .total-label { font-size: 11px; opacity: 0.85; text-transform: uppercase; }
    .total-value { font-size: 20px; font-weight: 900; }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXIÓN DRIVE ---
PARENT_FOLDER_ID = "19d0FCdGHQp9wG0DNBLgH5kPtG5rAGJ9r"

def get_drive_service():
    try:
        if "google_creds" in st.secrets:
            info = json.loads(st.secrets["google_creds"]["json_data"])
            if "private_key" in info:
                info["private_key"] = info["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/drive"]
            )
            return build('drive', 'v3', credentials=creds)
    except:
        return None
    return None

def list_files_in_folder(empresa_name):
    try:
        service = get_drive_service()
        if not service:
            return []
        query = f"name = '{empresa_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items:
            return []
        f_id = items[0]['id']
        res = service.files().list(
            q=f"'{f_id}' in parents and trashed = false",
            fields="files(name, webViewLink)"
        ).execute()
        return res.get('files', [])
    except:
        return []

# --- MOTOR DE DATOS ---
@st.cache_data(ttl=3600)
def load_and_merge_data():
    url_base = "https://docs.google.com/spreadsheets/d/1SiA8b7PAWOlTUfrHu_ew3Qt-D1JTVSZKQ8bUbSS4GQU/export?format=csv"
    url_acad = "https://docs.google.com/spreadsheets/d/1DamhAcTIll23Op6JyQvJYvSjKeaCmx8f_FmkKDp1UXE/export?format=csv"

    try:
        df_b = pd.read_csv(url_base)
        df_a = pd.read_csv(url_acad)
        df_b.columns = [c.strip().upper().replace("_", " ") for c in df_b.columns]
        df_a.columns = [c.strip().upper().replace("_", " ") for c in df_a.columns]

        def safe_clean(val):
            if pd.isna(val) or str(val).strip().lower() in ['nan', 'none', '']:
                return "S/D"
            try:
                return str(int(float(val))).strip()
            except:
                return str(val).strip()

        df_b['CODIGO CURSO'] = df_b['CODIGO CURSO'].apply(safe_clean)
        df_a['CODIGO CURSO'] = df_a['CODIGO CURSO'].apply(safe_clean)
        if 'RNC' in df_b.columns:
            df_b['RNC'] = df_b['RNC'].apply(safe_clean)

        if 'FACILITADOR' in df_a.columns:
            df_a_sub = df_a[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
            df_final = pd.merge(df_b, df_a_sub, on='CODIGO CURSO', how='left')
        else:
            df_final = df_b

        df_final['ESTADO'] = df_final['ESTADO'].astype(str).str.capitalize().str.strip()
        df_final = df_final[df_final['ESTADO'].isin(['Iniciado', 'Cerrado'])]

        # ─── CONVERSIÓN CRÍTICA DE FECHAS ────────────────────────────────────────
        df_final['FECHA_DT'] = pd.to_datetime(
            df_final['FECHA INICIO'], dayfirst=True, errors='coerce'
        ).dt.date
        df_final = df_final.dropna(subset=['FECHA_DT'])
        df_final = df_final.sort_values(by='FECHA_DT', ascending=True).reset_index(drop=True)
        # ─────────────────────────────────────────────────────────────────────────

        cols_num = ['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES', 'HORAS EJECUTADAS', 'HORAS FALTAN']
        for col in cols_num:
            if col not in df_final.columns:
                df_final[col] = 0
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0).astype(int)

        df_final['PARTICIPANTES'] = (
            df_final['OPERARIOS'] + df_final['MANDOS MEDIOS'] + df_final['GERENTES']
        )
        return df_final

    except Exception as e:
        st.error(f"Error en datos: {e}")
        return pd.DataFrame()

# --- CARGA INICIAL ---
df = load_and_merge_data()

if not df.empty:
    st.sidebar.header("🛠️ Filtros de Control")

    if st.sidebar.button("🔄 Sincronizar con Google Sheets"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")

    # ─── FILTRO DE FECHA ─────────────────────────────────────────────────────────
    st.sidebar.subheader("📅 Periodo de Capacitación")
    min_d, max_d = df['FECHA_DT'].min(), df['FECHA_DT'].max()

    rango_fecha = st.sidebar.date_input(
        "Rango de Fechas (Día/Mes/Año)",
        value=(min_d, max_d),
        min_value=min_d,
        max_value=max_d,
        format="DD/MM/YYYY"
    )

    if isinstance(rango_fecha, (list, tuple)) and len(rango_fecha) == 2:
        df_f = df[
            (df['FECHA_DT'] >= rango_fecha[0]) &
            (df['FECHA_DT'] <  rango_fecha[1])
        ].copy()
    elif isinstance(rango_fecha, (list, tuple)) and len(rango_fecha) == 1:
        df_f = df[df['FECHA_DT'] >= rango_fecha[0]].copy()
    else:
        df_f = df.copy()
    # ─────────────────────────────────────────────────────────────────────────────

    # ─── FILTROS EN CASCADA ───────────────────────────────────────────────────────
    # Cada filtro reduce las opciones del siguiente según lo seleccionado arriba

    # 1. EMPRESA — opciones del universo filtrado por fecha
    f_empresa = st.sidebar.multiselect(
        "Empresa", sorted(df_f['EMPRESA'].unique())
    )
    df_f1 = df_f[df_f['EMPRESA'].isin(f_empresa)] if f_empresa else df_f

    # 2. FACILITADOR — solo los facilitadores que existen en las empresas seleccionadas
    f_facilitador = st.sidebar.multiselect(
        "Facilitador", sorted(df_f1['FACILITADOR'].dropna().unique().astype(str))
    )
    df_f2 = df_f1[df_f1['FACILITADOR'].isin(f_facilitador)] if f_facilitador else df_f1

    # 3. ESTADO — solo los estados que existen tras los filtros anteriores
    f_estado = st.sidebar.multiselect(
        "Estado", sorted(df_f2['ESTADO'].unique()),
        default=sorted(df_f2['ESTADO'].unique())
    )
    df_f3 = df_f2[df_f2['ESTADO'].isin(f_estado)] if f_estado else df_f2

    # 4. ACCIÓN FORMATIVA — solo las que existen tras los filtros anteriores
    f_curso = st.sidebar.multiselect(
        "Acción Formativa", sorted(df_f3['ACCION FORMATIVA'].unique())
    )
    df_f = df_f3[df_f3['ACCION FORMATIVA'].isin(f_curso)] if f_curso else df_f3
    # ─────────────────────────────────────────────────────────────────────────────

    # --- TABS ---
    t1, t2, t3 = st.tabs(["📊 Dashboard Maestro", "📋 Tabla de Datos", "📂 Repositorio"])

    # ════════════════════════════════════════════════════════════════════════════
    with t1:
        st.title("Control Operativo Leonel Tavarez 2026")

        # ── KPIs ──
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Total Horas",          f"{df_f['HORAS EJECUTADAS'].sum():,}")
        with c2: st.metric("Participantes",         f"{df_f['PARTICIPANTES'].sum():,}")
        with c3: st.metric("Acciones Formativas",   f"{len(df_f):,}")
        with c4: st.metric("Empresas Impactadas",   f"{df_f['EMPRESA'].nunique()}")
        st.markdown("---")

        if not df_f.empty:

            # ── GRÁFICA 1: Acciones Formativas, Horas y Participantes por Empresa ──
            st.subheader("1. Alcance Operativo por Empresa")
            df_g1 = df_f.groupby('EMPRESA').agg(
                ACCIONES_FORMATIVAS=('ACCION FORMATIVA', 'count'),
                HORAS_EJECUTADAS=('HORAS EJECUTADAS', 'sum'),
                PARTICIPANTES=('PARTICIPANTES', 'sum')
            ).reset_index()
            fig1 = px.bar(
                df_g1, x='EMPRESA',
                y=['ACCIONES_FORMATIVAS', 'HORAS_EJECUTADAS', 'PARTICIPANTES'],
                barmode='group', text_auto=True,
                color_discrete_map={
                    'ACCIONES_FORMATIVAS': C_VERDE,
                    'HORAS_EJECUTADAS':    C_AZUL,
                    'PARTICIPANTES':       C_AMARILLO
                },
                labels={
                    'ACCIONES_FORMATIVAS': 'Acciones Formativas',
                    'HORAS_EJECUTADAS':    'Horas Ejecutadas',
                    'PARTICIPANTES':       'Participantes'
                }
            )
            fig1.update_layout(
                xaxis_title="Empresa", yaxis_title="Total", legend_title="Indicador",
                yaxis=dict(showgrid=False, tickformat="d"),
                xaxis=dict(showgrid=False),
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig1, use_container_width=True)

            st.markdown("---")

            col_a, col_b = st.columns(2)

            # ── GRÁFICA 2: Distribución de Niveles Jerárquicos por Empresa (apilada) ──
            with col_a:
                st.subheader("2. Distribución de Niveles")
                df_g2 = df_f.groupby('EMPRESA')[['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']].sum().reset_index()
                fig2 = px.bar(
                    df_g2, x='EMPRESA',
                    y=['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES'],
                    barmode='stack', text_auto=True,
                    color_discrete_map={
                        'OPERARIOS':     C_AZUL,
                        'MANDOS MEDIOS': C_AMARILLO,
                        'GERENTES':      C_ROJO
                    }
                )
                fig2.update_layout(
                    xaxis_title="Empresa", yaxis_title="Participantes", legend_title="Nivel",
                    yaxis=dict(showgrid=False, tickformat="d"),
                    xaxis=dict(showgrid=False),
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig2, use_container_width=True)

            # ── GRÁFICA 3: Acciones por Facilitador coloreadas por Empresa ──
            with col_b:
                st.subheader("3. Ejecución por Facilitador")
                df_g3 = df_f.groupby(['FACILITADOR', 'EMPRESA']).agg(
                    ACCIONES=('ACCION FORMATIVA', 'count'),
                    HORAS=('HORAS EJECUTADAS', 'sum'),
                    PARTICIPANTES=('PARTICIPANTES', 'sum')
                ).reset_index()
                fig3 = px.bar(
                    df_g3, x='FACILITADOR', y='ACCIONES',
                    color='EMPRESA', text_auto=True,
                    barmode='stack',
                    labels={
                        'FACILITADOR': 'Facilitador',
                        'ACCIONES':    'Acciones Formativas',
                        'EMPRESA':     'Empresa'
                    }
                )
                fig3.update_layout(
                    xaxis_title="Facilitador", yaxis_title="Acciones Formativas",
                    legend_title="Empresa",
                    yaxis=dict(showgrid=False, tickformat="d"),
                    xaxis=dict(showgrid=False),
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig3, use_container_width=True)

        else:
            st.warning("No hay datos para el rango de fechas y filtros seleccionados.")

    # ════════════════════════════════════════════════════════════════════════════
    with t2:
        st.subheader("📋 Registro Maestro")

        columnas = [
            'EMPRESA', 'RNC', 'ACCION FORMATIVA', 'FECHA INICIO', 'FECHA TERMINO',
            'CODIGO CURSO', 'FACILITADOR', 'ESTADO', 'HORAS EJECUTADAS',
            'HORAS FALTAN', 'OPERARIOS', 'MANDOS MEDIOS', 'GERENTES', 'PARTICIPANTES'
        ]
        # Solo incluir columnas que existan en el df
        columnas = [c for c in columnas if c in df_f.columns]

        # ── Pre-cálculo de totales ──
        total_acciones      = len(df_f)
        total_horas         = df_f['HORAS EJECUTADAS'].sum()
        total_participantes = df_f['PARTICIPANTES'].sum()
        total_empresas      = df_f['EMPRESA'].nunique()

        # ── Botones de descarga ──
        cd1, cd2, _ = st.columns([1.2, 1.2, 3.6])

        with cd1:
            fila_total_csv = {col: '' for col in columnas}
            fila_total_csv['EMPRESA']          = 'TOTAL GENERAL'
            fila_total_csv['ACCION FORMATIVA'] = f'{total_acciones} acciones'
            fila_total_csv['HORAS EJECUTADAS'] = total_horas
            fila_total_csv['PARTICIPANTES']    = total_participantes
            df_csv_export = pd.concat(
                [df_f[columnas], pd.DataFrame([fila_total_csv])],
                ignore_index=True
            ).fillna('')
            st.download_button(
                "📥 Descargar CSV",
                df_csv_export.to_csv(index=False).encode('utf-8'),
                "reporte.csv", "text/csv"
            )

        with cd2:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_f[columnas].to_excel(writer, index=False, sheet_name='Reporte')
                workbook  = writer.book
                worksheet = writer.sheets['Reporte']

                fmt_header = workbook.add_format({
                    'bold': True, 'bg_color': '#0056b3', 'font_color': '#FFFFFF',
                    'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 11
                })
                fmt_total_label = workbook.add_format({
                    'bold': True, 'bg_color': '#0056b3', 'font_color': '#FFFFFF',
                    'border': 1, 'align': 'left', 'valign': 'vcenter', 'font_size': 11
                })
                fmt_total_num = workbook.add_format({
                    'bold': True, 'bg_color': '#ffcc00', 'font_color': '#000000',
                    'border': 1, 'align': 'center', 'valign': 'vcenter',
                    'font_size': 12, 'num_format': '#,##0'
                })
                fmt_total_blank = workbook.add_format({
                    'bold': True, 'bg_color': '#0056b3', 'font_color': '#FFFFFF',
                    'border': 1
                })

                for col_idx, col_name in enumerate(columnas):
                    worksheet.write(0, col_idx, col_name, fmt_header)

                fila_total = len(df_f) + 1
                col_map = {col: i for i, col in enumerate(columnas)}

                for col in columnas:
                    worksheet.write(fila_total, col_map[col], '', fmt_total_blank)

                worksheet.write(fila_total, col_map['EMPRESA'],
                                '✔ TOTAL GENERAL', fmt_total_label)
                if 'ACCION FORMATIVA' in col_map:
                    worksheet.write(fila_total, col_map['ACCION FORMATIVA'],
                                    f'{total_acciones} Acciones Formativas', fmt_total_label)
                worksheet.write(fila_total, col_map['HORAS EJECUTADAS'],
                                total_horas, fmt_total_num)
                worksheet.write(fila_total, col_map['PARTICIPANTES'],
                                total_participantes, fmt_total_num)

                # Anchos de columna ajustados a las columnas visibles
                anchos_map = {
                    'EMPRESA': 28, 'RNC': 14, 'ACCION FORMATIVA': 40,
                    'FECHA INICIO': 14, 'FECHA TERMINO': 14, 'CODIGO CURSO': 16,
                    'FACILITADOR': 26, 'ESTADO': 12, 'HORAS EJECUTADAS': 18,
                    'HORAS FALTAN': 14, 'OPERARIOS': 12, 'MANDOS MEDIOS': 15,
                    'GERENTES': 12, 'PARTICIPANTES': 14
                }
                for i, col in enumerate(columnas):
                    worksheet.set_column(i, i, anchos_map.get(col, 14))

                worksheet.set_row(fila_total, 22)

            st.download_button("📥 Descargar Excel", output.getvalue(), "reporte.xlsx")

        # ── Tabla de datos completa ──
        st.dataframe(df_f[columnas], use_container_width=True, hide_index=True)

        # ── Totales dinámicos debajo de la tabla ──
        st.markdown(f"""
        <div class="total-row-box">
            <div class="total-item">
                <span class="total-label">📋 Acciones Formativas</span>
                <span class="total-value">{total_acciones:,}</span>
            </div>
            <div class="total-item">
                <span class="total-label">⏱️ Total Horas</span>
                <span class="total-value">{total_horas:,}</span>
            </div>
            <div class="total-item">
                <span class="total-label">👥 Total Participantes</span>
                <span class="total-value">{total_participantes:,}</span>
            </div>
            <div class="total-item">
                <span class="total-label">🏢 Empresas</span>
                <span class="total-value">{total_empresas:,}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════════
    with t3:
        st.subheader("📂 Documentos en Drive")
        if f_empresa and len(f_empresa) == 1:
            archivos = list_files_in_folder(f_empresa[0])
            if archivos:
                st.write(f"Archivos para **{f_empresa[0]}**:")
                st.markdown("---")
                for a in archivos:
                    col_file, col_btn = st.columns([0.7, 0.3])
                    with col_file:
                        st.write(f"📄 {a['name']}")
                    with col_btn:
                        st.link_button("Abrir Archivo", a['webViewLink'], use_container_width=True)
            else:
                st.warning("Carpeta vacía o sin acceso.")
        else:
            st.info("ℹ️ Selecciona una sola empresa para gestionar sus documentos.")
