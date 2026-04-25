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
    /* Fila de totales al final de la tabla */
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

        if 'FACILITADOR' in df_a.columns:
            df_a_sub = df_a[['CODIGO CURSO', 'FACILITADOR']].drop_duplicates(subset=['CODIGO CURSO'])
            df_final = pd.merge(df_b, df_a_sub, on='CODIGO CURSO', how='left')
        else:
            df_final = df_b

        df_final['ESTADO'] = df_final['ESTADO'].astype(str).str.capitalize().str.strip()
        df_final = df_final[df_final['ESTADO'].isin(['Iniciado', 'Cerrado'])]

        # ─── CONVERSIÓN CRÍTICA DE FECHAS ────────────────────────────────────────
        # Extraemos solo la parte date para comparaciones exactas sin interferencia de horas
        df_final['FECHA_DT'] = pd.to_datetime(
            df_final['FECHA INICIO'], errors='coerce'
        ).dt.date
        df_final = df_final.dropna(subset=['FECHA_DT'])
        # Ordenamos desde el origen por fecha ascendente
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

    if st.sidebar.button("🔄 Sincronizar Datos"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")

    # ─── FILTRO DE FECHA CORREGIDO ────────────────────────────────────────────
    st.sidebar.subheader("📅 Periodo de Capacitación")
    min_d, max_d = df['FECHA_DT'].min(), df['FECHA_DT'].max()

    rango_fecha = st.sidebar.date_input(
        "Rango de Fechas (Día/Mes/Año)",
        value=(min_d, max_d),      # ← tupla evita el fallo de isinstance con list
        min_value=min_d,
        max_value=max_d,
        format="DD/MM/YYYY"
    )

    # Streamlit puede devolver tupla de 1 o 2 elementos mientras el usuario elige
    if isinstance(rango_fecha, (list, tuple)) and len(rango_fecha) == 2:
        fecha_inicio = rango_fecha[0]
        fecha_fin    = rango_fecha[1]
        # Regla: >= inicio  Y  < fin  (el día final queda excluido)
        df_f = df[
            (df['FECHA_DT'] >= fecha_inicio) &
            (df['FECHA_DT'] <  fecha_fin)
        ].copy()
    elif isinstance(rango_fecha, (list, tuple)) and len(rango_fecha) == 1:
        df_f = df[df['FECHA_DT'] >= rango_fecha[0]].copy()
    else:
        df_f = df.copy()
    # ─────────────────────────────────────────────────────────────────────────

    # --- FILTROS DINÁMICOS ---
    f_empresa = st.sidebar.multiselect("Empresa", sorted(df_f['EMPRESA'].unique()))
    if f_empresa:
        df_f = df_f[df_f['EMPRESA'].isin(f_empresa)]

    f_facilitador = st.sidebar.multiselect(
        "Facilitador", sorted(df_f['FACILITADOR'].unique().astype(str))
    )
    if f_facilitador:
        df_f = df_f[df_f['FACILITADOR'].isin(f_facilitador)]

    f_estado = st.sidebar.multiselect(
        "Estado", sorted(df_f['ESTADO'].unique()), default=sorted(df_f['ESTADO'].unique())
    )
    if f_estado:
        df_f = df_f[df_f['ESTADO'].isin(f_estado)]

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

            # ── GRÁFICA 1: Horas y Participantes por Empresa ──
            st.subheader("📊 Alcance por Empresa")
            df_g1 = df_f.groupby('EMPRESA')[['HORAS EJECUTADAS', 'PARTICIPANTES']].sum().reset_index()
            fig1 = px.bar(
                df_g1, x='EMPRESA', y=['HORAS EJECUTADAS', 'PARTICIPANTES'],
                barmode='group', text_auto=True,
                color_discrete_map={'HORAS EJECUTADAS': C_AZUL, 'PARTICIPANTES': C_AMARILLO}
            )
            fig1.update_layout(xaxis_title="Empresa", yaxis_title="Total", legend_title="Indicador")
            st.plotly_chart(fig1, use_container_width=True)

            st.markdown("---")

            # ── GRÁFICA 2: Niveles Jerárquicos (Operarios / Mandos Medios / Gerentes) ──
            st.subheader("🏭 Distribución por Nivel Jerárquico")
            df_g2 = df_f[['OPERARIOS', 'MANDOS MEDIOS', 'GERENTES']].sum().reset_index()
            df_g2.columns = ['Nivel', 'Total']
            fig2 = px.bar(
                df_g2, x='Nivel', y='Total',
                text_auto=True,
                color='Nivel',
                color_discrete_map={
                    'OPERARIOS':     C_AZUL,
                    'MANDOS MEDIOS': C_AMARILLO,
                    'GERENTES':      C_VERDE
                }
            )
            fig2.update_layout(showlegend=False, xaxis_title="Nivel", yaxis_title="Participantes")
            st.plotly_chart(fig2, use_container_width=True)

            st.markdown("---")

            # ── GRÁFICA 3: Resumen por Facilitador ──
            st.subheader("👤 Desempeño por Facilitador")
            df_g3 = df_f.groupby('FACILITADOR').agg(
                Acciones_Formativas=('ACCION FORMATIVA', 'count'),
                Horas_Ejecutadas=('HORAS EJECUTADAS', 'sum'),
                Participantes=('PARTICIPANTES', 'sum'),
                Empresas=('EMPRESA', 'nunique')
            ).reset_index().rename(columns={'FACILITADOR': 'Facilitador'})

            fig3 = px.bar(
                df_g3, x='Facilitador',
                y=['Acciones_Formativas', 'Horas_Ejecutadas', 'Participantes'],
                barmode='group', text_auto=True,
                color_discrete_map={
                    'Acciones_Formativas': C_VERDE,
                    'Horas_Ejecutadas':    C_AZUL,
                    'Participantes':       C_AMARILLO
                },
                labels={
                    'Acciones_Formativas': 'Acciones Formativas',
                    'Horas_Ejecutadas':    'Horas Ejecutadas',
                    'Participantes':       'Participantes'
                }
            )
            fig3.update_layout(xaxis_title="Facilitador", yaxis_title="Total", legend_title="Indicador")
            st.plotly_chart(fig3, use_container_width=True)

            # Tabla detalle por facilitador
            st.dataframe(
                df_g3.rename(columns={
                    'Acciones_Formativas': 'Acciones Formativas',
                    'Horas_Ejecutadas':    'Horas Ejecutadas'
                }),
                use_container_width=True,
                hide_index=True
            )

        else:
            st.warning("No hay datos para el rango de fechas y filtros seleccionados.")

    # ════════════════════════════════════════════════════════════════════════════
    with t2:
        st.subheader("📋 Registro Maestro")

        columnas = [
            'EMPRESA', 'RNC', 'ACCION FORMATIVA', 'FECHA INICIO', 'FECHA TERMINO',
            'FACILITADOR', 'ESTADO', 'HORAS EJECUTADAS', 'PARTICIPANTES'
        ]

        # ── Pre-cálculo de totales ──
        total_acciones      = len(df_f)
        total_horas         = df_f['HORAS EJECUTADAS'].sum()
        total_participantes = df_f['PARTICIPANTES'].sum()
        total_empresas      = df_f['EMPRESA'].nunique()

        # ── Botones de descarga ──
        cd1, cd2, _ = st.columns([1.2, 1.2, 3.6])

        with cd1:
            # CSV con fila de totales al final
            fila_total_csv = {
                'EMPRESA': 'TOTAL GENERAL',
                'RNC': '',
                'ACCION FORMATIVA': f'{total_acciones} acciones',
                'FECHA INICIO': '',
                'FECHA TERMINO': '',
                'FACILITADOR': '',
                'ESTADO': '',
                'HORAS EJECUTADAS': total_horas,
                'PARTICIPANTES': total_participantes
            }
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
            # Excel con fila de totales formateada (azul INFOTEP + amarillo)
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

                # Encabezados con color azul
                for col_idx, col_name in enumerate(columnas):
                    worksheet.write(0, col_idx, col_name, fmt_header)

                # Fila de totales al final
                fila_total = len(df_f) + 1
                col_map = {col: i for i, col in enumerate(columnas)}

                for col in columnas:
                    worksheet.write(fila_total, col_map[col], '', fmt_total_blank)

                worksheet.write(fila_total, col_map['EMPRESA'],
                                '✔ TOTAL GENERAL', fmt_total_label)
                worksheet.write(fila_total, col_map['ACCION FORMATIVA'],
                                f'{total_acciones} Acciones Formativas', fmt_total_label)
                worksheet.write(fila_total, col_map['HORAS EJECUTADAS'],
                                total_horas, fmt_total_num)
                worksheet.write(fila_total, col_map['PARTICIPANTES'],
                                total_participantes, fmt_total_num)

                # Ancho de columnas
                anchos = [30, 14, 42, 14, 14, 28, 12, 18, 14]
                for i, ancho in enumerate(anchos):
                    worksheet.set_column(i, i, ancho)

                worksheet.set_row(fila_total, 22)

            st.download_button("📥 Descargar Excel", output.getvalue(), "reporte.xlsx")

        # ── Tabla ordenada por fecha ascendente ──
        st.dataframe(df_f[columnas], use_container_width=True, hide_index=True)

        # ── Totales dinámicos debajo de la tabla (estilo tabla dinámica) ──
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
        st.subheader("📂 Repositorio")
        if f_empresa and len(f_empresa) == 1:
            archivos = list_files_in_folder(f_empresa[0])
            if archivos:
                for a in archivos:
                    col_file, col_btn = st.columns([0.7, 0.3])
                    with col_file:
                        st.write(f"📄 {a['name']}")
                    with col_btn:
                        st.link_button("Abrir", a['webViewLink'])
            else:
                st.warning("No hay archivos en esta carpeta.")
        else:
            st.info("Selecciona una sola empresa para ver documentos.")
