
import io
from datetime import date, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Gestión de Órdenes de Servicio",
    page_icon="📊",
    layout="wide",
)

# ============================================================
# REGLAS DEL ANÁLISIS
# ============================================================

CASOS = [
    "INSTALACION",
    "INSTALACION TV",
    "TRASLADO DE SERVICIO",
    "CLIENTE SIN SERVICIO",
    "CAMBIO DE PLAN",
]

PENDIENTES = {"PENDIENTE", "CONFIRMADA", "POSPUESTA", "INICIADA"}
REALIZADO = {"CERRADA"}
ANULADO = {"ANULADA"}

INTERVALOS = [
    "0–2 días", "3–5 días", "6–10 días", "11–15 días",
    "16–20 días", "21–25 días", "26–30 días", "Más de 30 días"
]

ALIASES = {
    "numero_os": ["ID Orden De Servicio", "Número OS", "Nro OS", "N° OS", "OS", "NumeroOS"],
    "fecha_creacion": [
        "Fecha Creacion", "Fecha Creación", "Fecha de Creacion",
        "Fecha de Creación", "Fecha Apertura", "Fecha de Apertura"
    ],
    "estado": ["Estado", "ESTADO"],
    "sucursal": ["Sucursal", "SUCURSAL"],
    "caso": ["Caso Asociado", "Caso asociado", "Caso", "CASO ASOCIADO"],
    "localidad": ["Localidad", "Ciudad", "LOCALIDAD", "CIUDAD"],
    "tipo_os": ["Tipo de OS", "Tipo OS", "Tipo", "TIPO DE OS"],
    "fecha_cierre": [
        "Fecha Cierre", "Fecha Cierre OS", "Fecha de Cierre",
        "Fecha Cerrada", "Fecha Cerrado"
    ],
}

def norm(x):
    s = str(x).strip().lower()
    repl = str.maketrans("áéíóúüñ", "aeiouun")
    s = s.translate(repl)
    return " ".join(s.replace("_", " ").replace("-", " ").split())

def find_col(df, aliases):
    m = {norm(c): c for c in df.columns}
    for a in aliases:
        if norm(a) in m:
            return m[norm(a)]
    for c in df.columns:
        nc = norm(c)
        for a in aliases:
            na = norm(a)
            if na in nc or nc in na:
                return c
    return None

def load_file(uploaded):
    raw = uploaded.getvalue()
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        for enc in ["utf-8-sig", "cp1252", "latin1"]:
            for sep in [";", ",", "\t"]:
                try:
                    df = pd.read_csv(io.BytesIO(raw), encoding=enc, sep=sep)
                    if df.shape[1] > 1:
                        return df
                except Exception:
                    pass
        raise ValueError("No se pudo leer el CSV.")
    return pd.read_excel(io.BytesIO(raw))

def age_bucket(d):
    if pd.isna(d):
        return "Sin fecha"
    d = int(d)
    if d <= 2: return "0–2 días"
    if d <= 5: return "3–5 días"
    if d <= 10: return "6–10 días"
    if d <= 15: return "11–15 días"
    if d <= 20: return "16–20 días"
    if d <= 25: return "21–25 días"
    if d <= 30: return "26–30 días"
    return "Más de 30 días"

def fmt(n):
    return f"{int(n):,}".replace(",", ".")

def safe_div(a, b):
    return a / b if b else 0

st.title("📊 Gestión de Órdenes de Servicio")
st.caption("Análisis de trabajo real + planificación de regularización de cuadrillas")

# ============================================================
# CARGA
# ============================================================

with st.sidebar:
    st.header("📁 Archivo")
    uploaded = st.file_uploader(
        "Cargar Excel o CSV",
        type=["xlsx", "xls", "csv"]
    )

if uploaded is None:
    st.info("Cargá el Excel/CSV de órdenes de servicio para comenzar.")
    st.markdown("""
### Criterio del análisis

**Casos considerados:**
- INSTALACION
- INSTALACION TV
- TRASLADO DE SERVICIO
- CLIENTE SIN SERVICIO
- CAMBIO DE PLAN

**Estados:**
- Realizado = CERRADA
- Falta hacer = PENDIENTE + CONFIRMADA + POSPUESTA + INICIADA
- Anulada = ANULADA
- Otros estados = se identifican por separado

**Antigüedad:** desde Fecha Creación hasta la fecha final del período.

EQUIPO PASADO A STOCK y otros casos no incluidos quedan fuera del trabajo técnico.
""")
    st.stop()

try:
    raw = load_file(uploaded)
except Exception as e:
    st.error(str(e))
    st.stop()

# Detect columns
col = {k: find_col(raw, v) for k, v in ALIASES.items()}

missing = [k for k in ["fecha_creacion", "estado", "sucursal", "caso"] if col[k] is None]
if missing:
    st.error("No se pudieron identificar: " + ", ".join(missing))
    st.write("Columnas del archivo:")
    st.write(list(raw.columns))
    st.stop()

df = raw.copy()
df["_estado"] = df[col["estado"]].astype(str).str.strip().str.upper()
df["_caso"] = df[col["caso"]].astype(str).str.strip().str.upper()
df["_sucursal"] = df[col["sucursal"]].astype(str).str.strip().str.upper()
df["_fecha"] = pd.to_datetime(df[col["fecha_creacion"]], errors="coerce", dayfirst=True)

if col["fecha_cierre"]:
    df["_fecha_cierre"] = pd.to_datetime(df[col["fecha_cierre"]], errors="coerce", dayfirst=True)
else:
    df["_fecha_cierre"] = pd.NaT

valid_dates = df["_fecha"].dropna()
if valid_dates.empty:
    st.error("No hay fechas válidas en la columna de creación.")
    st.stop()

min_date = valid_dates.min().date()
max_date = valid_dates.max().date()

sucs = sorted([str(x) for x in df["_sucursal"].unique() if str(x) not in ["", "nan", "NAN", "None"]])
default_suc = "CONCORDIA" if "CONCORDIA" in sucs else sucs[0]

with st.sidebar:
    st.header("📅 Período analizado")
    fecha_desde = st.date_input("Desde", value=min_date, min_value=min_date, max_value=max_date)
    fecha_hasta = st.date_input("Hasta", value=min(max_date, date(2026, 9, 5)), min_value=min_date, max_value=max_date)

    if fecha_desde > fecha_hasta:
        st.error("La fecha Desde no puede ser posterior a Hasta.")
        st.stop()

    st.header("📍 Filtros")
    sucursal = st.selectbox(
        "Sucursal",
        sucs,
        index=sucs.index(default_suc) if default_suc in sucs else 0
    )

    casos = st.multiselect(
        "Casos de trabajo",
        CASOS,
        default=CASOS
    )

# ============================================================
# BASE AL FINAL DEL PERÍODO
# ============================================================

end = pd.Timestamp(fecha_hasta)
start = pd.Timestamp(fecha_desde)

base = df[
    (df["_sucursal"] == sucursal) &
    (df["_fecha"].notna()) &
    (df["_fecha"] <= end) &
    (df["_caso"].isin(casos))
].copy()

base["antiguedad"] = (end - base["_fecha"]).dt.days
base["situacion"] = base["_estado"].apply(
    lambda x:
        "Realizado" if x in REALIZADO else
        "Falta hacer" if x in PENDIENTES else
        "Anulado" if x in ANULADO else
        "Otro estado"
)

realizados = base[base["situacion"] == "Realizado"].copy()
pendientes = base[base["situacion"] == "Falta hacer"].copy()
anulados = base[base["situacion"] == "Anulado"].copy()
otros = base[base["situacion"] == "Otro estado"].copy()

pendientes["intervalo"] = pendientes["antiguedad"].apply(age_bucket)

# OS creadas durante el período: sirve para medir ingreso de nuevas órdenes
entradas_periodo = base[
    (base["_fecha"] >= start) & (base["_fecha"] <= end)
].copy()

# Si existe fecha de cierre, calculamos cierres dentro del período como indicador adicional
if col["fecha_cierre"]:
    cierres_periodo = base[
        (base["_fecha_cierre"].notna()) &
        (base["_fecha_cierre"] >= start) &
        (base["_fecha_cierre"] <= end) &
        (base["_estado"].isin(REALIZADO))
    ].copy()
else:
    cierres_periodo = pd.DataFrame()

# ============================================================
# CABECERA
# ============================================================

st.info(
    f"**Período analizado:** {fecha_desde.strftime('%d/%m/%Y')} al "
    f"{fecha_hasta.strftime('%d/%m/%Y')} | **Sucursal:** {sucursal}"
)

tabs = st.tabs([
    "📊 Situación actual",
    "📅 Antigüedad",
    "🔎 Detalle",
    "👷 Planificación de cuadrillas",
    "📈 Proyección día a día",
    "📥 Exportar"
])

# ============================================================
# TAB 1
# ============================================================

with tabs[0]:
    st.subheader("Situación del trabajo técnico al final del período")

    a,b,c,d,e = st.columns(5)
    a.metric("✅ Realizado", fmt(len(realizados)))
    b.metric("🔴 Falta hacer", fmt(len(pendientes)))
    c.metric("❌ Anulado", fmt(len(anulados)))
    d.metric("⚠️ Otros estados", fmt(len(otros)))
    e.metric("📥 Entradas en período", fmt(len(entradas_periodo)))

    tabla = pd.crosstab(base["_caso"], base["situacion"])
    for x in ["Realizado", "Falta hacer", "Anulado", "Otro estado"]:
        if x not in tabla.columns:
            tabla[x] = 0
    tabla["Total"] = tabla.sum(axis=1)
    tabla = tabla.reset_index().rename(columns={"_caso": "Caso"})
    st.dataframe(
        tabla[["Caso","Realizado","Falta hacer","Anulado","Otro estado","Total"]],
        use_container_width=True, hide_index=True
    )

    st.subheader("Comparación visual")
    graf = tabla.set_index("Caso")[["Realizado","Falta hacer"]]
    st.bar_chart(graf)

    if col["fecha_cierre"]:
        st.subheader("Cierres dentro del período")
        st.metric("OS cerradas dentro del período", fmt(len(cierres_periodo)))

# ============================================================
# TAB 2
# ============================================================

with tabs[1]:
    st.subheader("🔴 Pendientes por antigüedad")

    cruz = pd.crosstab(pendientes["intervalo"], pendientes["_caso"])
    cruz = cruz.reindex(INTERVALOS, fill_value=0)
    for caso in casos:
        if caso not in cruz.columns:
            cruz[caso] = 0
    cruz = cruz[casos]
    cruz["TOTAL"] = cruz.sum(axis=1)

    total = cruz.sum(axis=0).to_frame().T
    total.index = ["TOTAL"]
    cruz_final = pd.concat([cruz, total])

    st.dataframe(cruz_final, use_container_width=True)

    st.bar_chart(cruz["TOTAL"])

    x1,x2,x3 = st.columns(3)
    x1.metric("> 30 días", fmt((pendientes["antiguedad"] > 30).sum()))
    x2.metric("11–30 días", fmt(((pendientes["antiguedad"] >= 11) & (pendientes["antiguedad"] <= 30)).sum()))
    x3.metric("0–10 días", fmt((pendientes["antiguedad"] <= 10).sum()))

# ============================================================
# TAB 3
# ============================================================

with tabs[2]:
    st.subheader("🔎 Detalle de órdenes pendientes")

    if pendientes.empty:
        st.success("No hay pendientes según los criterios seleccionados.")
    else:
        filtro_caso = st.selectbox("Ver caso", ["TODOS"] + casos)
        detalle = pendientes.copy()
        if filtro_caso != "TODOS":
            detalle = detalle[detalle["_caso"] == filtro_caso]

        cols_out = []
        if col["numero_os"]: cols_out.append(col["numero_os"])
        cols_out += [col["fecha_creacion"], col["estado"], col["sucursal"], col["caso"]]
        if col["localidad"]: cols_out.append(col["localidad"])
        if col["tipo_os"]: cols_out.append(col["tipo_os"])
        cols_out = list(dict.fromkeys(cols_out))

        out = detalle[cols_out].copy()
        out["Antigüedad días"] = detalle["antiguedad"].values
        out["Intervalo"] = detalle["intervalo"].values
        st.dataframe(
            out.sort_values("Antigüedad días", ascending=False),
            use_container_width=True, hide_index=True
        )

# ============================================================
# TAB 4 - PLANIFICACIÓN
# ============================================================

with tabs[3]:
    st.subheader("👷 Etapa 2 — Planificación de cuadrillas")
    st.write(
        "Esta sección transforma la cartera pendiente en un plan de regularización. "
        "Los parámetros son editables para probar distintos escenarios."
    )

    q1,q2,q3,q4 = st.columns(4)
    with q1:
        cuadrillas = st.number_input("Cantidad de cuadrillas", min_value=1, max_value=50, value=5)
    with q2:
        trabajos_dia = st.number_input(
            "Trabajos por cuadrilla/día", min_value=1, max_value=30, value=5
        )
    with q3:
        dias_trabajo_semana = st.number_input(
            "Días de trabajo por semana", min_value=1, max_value=7, value=6
        )
    with q4:
        ingreso_diario = st.number_input(
            "Nuevas OS por día", min_value=0.0, max_value=10000.0, value=0.0, step=1.0
        )

    capacidad = cuadrillas * trabajos_dia
    saldo_neto = capacidad - ingreso_diario

    st.markdown("### Capacidad")
    c1,c2,c3 = st.columns(3)
    c1.metric("Cuadrillas", cuadrillas)
    c2.metric("Capacidad diaria", fmt(capacidad))
    c3.metric("Saldo diario de reducción", fmt(saldo_neto))

    if ingreso_diario >= capacidad:
        st.warning(
            "⚠️ Con estos parámetros las nuevas OS igualan o superan la capacidad. "
            "El atraso no se elimina."
        )
    else:
        pendientes_n = len(pendientes)
        dias_teoricos = pendientes_n / saldo_neto if saldo_neto > 0 else 0
        st.success(
            f"Con {cuadrillas} cuadrillas a {trabajos_dia} trabajos/día, "
            f"y {ingreso_diario:g} nuevas OS/día, el atraso de {fmt(pendientes_n)} "
            f"se eliminaría en aproximadamente **{dias_teoricos:.1f} días operativos**."
        )

    st.markdown("### Escenarios")
    escenarios = []
    for q in [4,5,6]:
        cap = q * trabajos_dia
        net = cap - ingreso_diario
        dias = pendientes_n / net if net > 0 else None
        escenarios.append({
            "Cuadrillas": q,
            "Capacidad/día": cap,
            "Ingreso/día": ingreso_diario,
            "Reducción neta/día": max(net, 0),
            "Días para eliminar atraso": round(dias, 1) if dias is not None else "No se elimina"
        })
    st.dataframe(pd.DataFrame(escenarios), use_container_width=True, hide_index=True)

    st.markdown("### Objetivos de antigüedad")
    objetivos = []
    for limite in [30, 10, 7, 5, 2]:
        cantidad = int((pendientes["antiguedad"] > limite).sum())
        net = saldo_neto
        dias = cantidad / net if net > 0 else None
        objetivos.append({
            "Objetivo": f"≤ {limite} días",
            "OS que deben atacarse": cantidad,
            "Días operativos estimados": round(dias,1) if dias is not None else "No se elimina"
        })
    st.dataframe(pd.DataFrame(objetivos), use_container_width=True, hide_index=True)

    st.caption(
        "La proyección es un escenario matemático. No asigna una productividad diferente "
        "por tipo de trabajo ni considera feriados, ausencias, zonas, tiempos de viaje o "
        "capacidad diferenciada, salvo que se incorporen como parámetros."
    )

# ============================================================
# TAB 5 - PROYECCIÓN
# ============================================================

with tabs[4]:
    st.subheader("📈 Proyección día a día")

    pendientes_n = len(pendientes)

    p1,p2,p3 = st.columns(3)
    with p1:
        q = st.number_input("Cuadrillas para proyección", 1, 50, 5, key="pq")
    with p2:
        prod = st.number_input("Trabajos/cuadrilla/día", 1, 30, 5, key="pp")
    with p3:
        nuevos = st.number_input("Nuevas OS/día", 0.0, 10000.0, 0.0, step=1.0, key="pn")

    max_dias = st.number_input("Máximo de días a proyectar", 7, 3650, 180)

    capacidad = q * prod
    saldo = capacidad - nuevos

    rows = []
    backlog = float(pendientes_n)
    fecha = fecha_hasta

    for i in range(1, int(max_dias)+1):
        if backlog <= 0:
            break

        inicio = backlog
        realizadas_plan = min(capacidad, backlog)
        backlog = max(0, backlog - realizadas_plan + nuevos)

        fecha = fecha + timedelta(days=1)
        rows.append({
            "Día": i,
            "Fecha": fecha,
            "Backlog inicio": round(inicio, 1),
            "Trabajos realizados": round(realizadas_plan, 1),
            "Nuevas OS": round(nuevos, 1),
            "Backlog final": round(backlog, 1)
        })

    proj = pd.DataFrame(rows)

    if saldo <= 0:
        st.warning("La capacidad no supera el ingreso diario; el backlog no llega a cero.")
    elif not proj.empty:
        st.dataframe(proj, use_container_width=True, hide_index=True)
        st.line_chart(proj.set_index("Fecha")["Backlog final"])

        fin = proj.iloc[-1]
        if fin["Backlog final"] <= 0:
            st.success(
                f"🎯 El backlog llega a cero el **{fin['Fecha'].strftime('%d/%m/%Y')}**."
            )
        else:
            st.info(
                f"Después de {int(fin['Día'])} días quedan aproximadamente "
                f"**{fmt(fin['Backlog final'])} OS**."
            )

# ============================================================
# TAB 6 - EXPORTAR
# ============================================================

with tabs[5]:
    st.subheader("📥 Exportar resultados")

    ant_export = cruz_final.copy()
    resumen_export = tabla.copy()

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        resumen_export.to_excel(writer, sheet_name="Resumen", index=False)
        ant_export.to_excel(writer, sheet_name="Antiguedad")
        if not pendientes.empty:
            det = pendientes.copy()
            export_cols = []
            if col["numero_os"]: export_cols.append(col["numero_os"])
            export_cols += [
                col["fecha_creacion"], col["estado"],
                col["sucursal"], col["caso"]
            ]
            if col["localidad"]: export_cols.append(col["localidad"])
            if col["tipo_os"]: export_cols.append(col["tipo_os"])
            export_cols = list(dict.fromkeys(export_cols))
            det[export_cols + ["antiguedad", "intervalo"]].to_excel(
                writer, sheet_name="Pendientes", index=False
            )
        if not realizados.empty:
            realizados.to_excel(writer, sheet_name="Realizados", index=False)

    st.download_button(
        "⬇️ Descargar análisis completo en Excel",
        data=buffer.getvalue(),
        file_name=f"analisis_OS_{sucursal}_{fecha_hasta.strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ============================================================
# CONTROL
# ============================================================

with st.expander("🔧 Control técnico / columnas detectadas"):
    st.write(col)
    st.write("Filas originales:", len(raw))
    st.write("Filas de los casos seleccionados:", len(base))
    st.write("Realizadas:", len(realizados))
    st.write("Pendientes:", len(pendientes))
    st.write("Anuladas:", len(anulados))
    st.write("Otros estados:", len(otros))
    st.write("Estados encontrados:")
    st.dataframe(
        df["_estado"].value_counts().rename_axis("Estado").reset_index(name="Cantidad"),
        use_container_width=True, hide_index=True
    )
