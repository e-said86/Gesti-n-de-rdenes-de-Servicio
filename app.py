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
    "OS POR REPARACIONES/INTERNAS",
]

CASO_REPARACIONES = "OS POR REPARACIONES/INTERNAS"
TIPO_OS_REPARACIONES = "OS POR REPARACIONES/INSTALACIONES INTERNAS"

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
    "fecha_calendario": [
        "Fecha Calendario", "Fecha calendario", "FECHA CALENDARIO",
        "Calendario", "Fecha de Calendario"
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
    "confeccionado_por": [
        "Confeccionada por", "Confeccionada por..", "Confeccionado por"
    ]
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

st.title("📊 Análisis y Gestión de Órdenes de Servicio")
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
- OS POR REPARACIONES/INTERNAS (identificado desde Tipo de OS)

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
    if raw.columns.duplicated().any():
        cols_unicos = []
        vistos = {}
        for c in raw.columns:
            nombre = str(c)
            vistos[nombre] = vistos.get(nombre, 0) + 1
            cols_unicos.append(nombre if vistos[nombre] == 1 else f"{nombre}__dup{vistos[nombre]}")
        raw.columns = cols_unicos
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

# OS por Reparaciones/instalaciones internas se identifica por TIPO DE OS,
# no por la columna Caso Asociado. Para el análisis se presenta como una
# categoría adicional dentro de "Caso asociado".
if col.get("tipo_os"):
    # Normalizamos el valor de Tipo de OS para que la detección no dependa
    # de mayúsculas/minúsculas, espacios, guiones o acentos.
    _tipo_os_norm = (
        df[col["tipo_os"]]
        .fillna("")
        .astype(str)
        .map(norm)
    )
    _tipo_reparaciones_norm = norm(TIPO_OS_REPARACIONES)
    df.loc[
        _tipo_os_norm == _tipo_reparaciones_norm,
        "_caso"
    ] = CASO_REPARACIONES

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
    # Por defecto: desde el primer día del mes anteúltimo al último mes
    # disponible en el archivo, hasta la fecha más actual disponible.
    ultimo_mes = pd.Timestamp(max_date).replace(day=1)
    mes_anteultimo = (ultimo_mes - pd.DateOffset(months=2)).date()
    desde_default = max(min_date, mes_anteultimo)

    fecha_desde = st.date_input(
        "Desde",
        value=desde_default,
        min_value=min_date,
        max_value=max_date
    )
    fecha_hasta = st.date_input(
        "Hasta",
        value=max_date,
        min_value=min_date,
        max_value=max_date
    )

    if fecha_desde > fecha_hasta:
        st.error("La fecha Desde no puede ser posterior a Hasta.")
        st.stop()

    st.header("📍 Filtros")
    sucursal = st.multiselect(
        "Sucursal",
        sucs,
        default=[default_suc] if default_suc in sucs else sucs
    )

    casos = st.multiselect(
        "Caso asociado",
        CASOS,
        default=CASOS
    )

# ============================================================
# BASE AL FINAL DEL PERÍODO
# ============================================================

start = pd.Timestamp(fecha_desde).normalize()
end = pd.Timestamp(fecha_hasta).normalize()
end_exclusive = end + pd.Timedelta(days=1)

if not sucursal:
    st.warning("Seleccioná al menos una sucursal.")
    st.stop()

base = df[
    (df["_sucursal"].isin(sucursal)) &
    (df["_fecha"].notna()) &
    (df["_fecha"] >= start) &
    (df["_fecha"] < end_exclusive) &
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
    (base["_fecha"] >= start) & (base["_fecha"] < end_exclusive)
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
    f"{fecha_hasta.strftime('%d/%m/%Y')} | **Sucursal:** {', '.join(sucursal)}"
)

tabs = st.tabs([
    "📊 Situación actual",
    "⏳ Antigüedad",
    "📝 Detalle",
    "👷‍♂️ Planificación de cuadrillas",
    "👷‍♂️ Productividad",
    "📈 Proyección día a día",
    "📥 Exportar",
    
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
    st.subheader("👷 Planificación de cuadrillas")
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


# =========================================================================
# TAB 5 - PRODUCTIVIDAD
# =========================================================================
with tabs[4]:
    st.subheader("👤 Productividad por Personal")
    st.write(
        "Medición de órdenes según la columna 'Fecha Calendario', "
        "independiente del período general de la barra lateral."
    )

    # ---------------------------------------------------------
    # Columnas reales detectadas
    # ---------------------------------------------------------
    col_usuario = col.get("confeccionado_por") or find_col(
        df, ["Confeccionada Por", "Confeccionada por", "Confeccionado Por"]
    )
    col_fecha_medicion = col.get("fecha_calendario") or find_col(
        df, ["Fecha Calendario", "Calendario", "Fecha de Calendario"]
    )
    col_estado_prod = col.get("estado") or find_col(df, ["Estado", "ESTADO"])
    col_sucursal_prod = col.get("sucursal") or find_col(df, ["Sucursal", "SUCURSAL"])

    if not col_fecha_medicion:
        st.error(
            "No se encontró la columna 'Fecha Calendario'. "
            "Columnas detectadas: " + ", ".join(map(str, df.columns))
        )
        st.stop()

    if not col_usuario:
        st.error("No se encontró la columna 'Confeccionada Por'.")
        st.stop()

    if not col_estado_prod:
        st.error("No se encontró la columna 'Estado'.")
        st.stop()

    if not col_sucursal_prod:
        st.error("No se encontró la columna 'Sucursal'.")
        st.stop()

    # ---------------------------------------------------------
    # Preparar base exclusiva de productividad
    # ---------------------------------------------------------
    df_prod_base = df.copy()

    df_prod_base["_fecha_productividad"] = pd.to_datetime(
        df_prod_base[col_fecha_medicion],
        errors="coerce",
        dayfirst=True
    )

    df_prod_base["_usuario_productividad"] = (
        df_prod_base[col_usuario]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df_prod_base["_estado_productividad"] = (
        df_prod_base[col_estado_prod]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df_prod_base["_sucursal_productividad"] = (
        df_prod_base[col_sucursal_prod]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    fechas_prod_validas = df_prod_base["_fecha_productividad"].dropna()

    if fechas_prod_validas.empty:
        st.error("La columna 'Fecha Calendario' no contiene fechas válidas.")
        st.stop()

    min_prod_date = fechas_prod_validas.min().date()
    max_prod_date = fechas_prod_validas.max().date()

    # ---------------------------------------------------------
    # Productividad SIEMPRE sobre el período general elegido.
    # ---------------------------------------------------------
    prod_desde = fecha_desde
    prod_hasta = fecha_hasta

    st.markdown("### 📅 Período de productividad")
    st.info(
        f"La productividad se calcula **exclusivamente sobre el período general seleccionado**: "
        f"**{prod_desde.strftime('%d/%m/%Y')} al {prod_hasta.strftime('%d/%m/%Y')}**. "
        f"Se utiliza **{col_fecha_medicion}** y el estado **CERRADA**."
    )

    # ---------------------------------------------------------
    # Límites correctos: incluye TODO el último día aunque tenga hora
    # ---------------------------------------------------------
    fecha_inicio_prod = pd.Timestamp(prod_desde).normalize()
    fecha_fin_exclusiva_prod = (
        pd.Timestamp(prod_hasta).normalize() + pd.Timedelta(days=1)
    )

    # ---------------------------------------------------------
    # Filtro de Productividad
    # IMPORTANTE: NO usa start/end del período general.
    # Usa exclusivamente prod_desde/prod_hasta.
    # ---------------------------------------------------------
    criterio_prod = (
        df_prod_base["_fecha_productividad"].notna()
        & (df_prod_base["_fecha_productividad"] >= fecha_inicio_prod)
        & (df_prod_base["_fecha_productividad"] < fecha_fin_exclusiva_prod)
    )

    if sucursal:
        sucursales_norm = [str(x).strip().upper() for x in sucursal]
        criterio_prod = criterio_prod & (
            df_prod_base["_sucursal_productividad"].isin(sucursales_norm)
        )

    criterio_prod = criterio_prod & df_prod_base["_caso"].isin(casos)
    df_prod = df_prod_base.loc[criterio_prod].copy()

    # ---------------------------------------------------------
    # Conteo por operador
    # ---------------------------------------------------------
    # Productividad = órdenes CERRADAS por Fecha Calendario.
    df_prod_cerradas = df_prod[
        df_prod["_estado_productividad"] == "CERRADA"
    ].copy()

    # El usuario debe existir.
    df_prod_cerradas = df_prod_cerradas[
        df_prod_cerradas["_usuario_productividad"].ne("")
        & df_prod_cerradas["_usuario_productividad"].ne("NAN")
        & df_prod_cerradas["_usuario_productividad"].ne("NONE")
    ].copy()

    # Total de órdenes y cerradas por operador.
    totales_por_usuario = (
        df_prod.groupby("_usuario_productividad")
        .size()
        .reset_index(name="Total Órdenes")
    )

    cerradas_por_usuario = (
        df_prod_cerradas.groupby("_usuario_productividad")
        .size()
        .reset_index(name="Órdenes Cerradas")
    )

    prod_data = totales_por_usuario.merge(
        cerradas_por_usuario,
        on="_usuario_productividad",
        how="left"
    )

    prod_data["Órdenes Cerradas"] = (
        prod_data["Órdenes Cerradas"].fillna(0).astype(int)
    )

    prod_data["Efectividad Cierre (%)"] = (
        prod_data["Órdenes Cerradas"]
        .div(prod_data["Total Órdenes"].replace(0, pd.NA))
        .fillna(0)
        .mul(100)
        .round(1)
    )

    prod_data = prod_data.rename(
        columns={"_usuario_productividad": "Confeccionada Por"}
    )

    prod_data = prod_data.sort_values(
        by="Órdenes Cerradas",
        ascending=False
    )

    # ---------------------------------------------------------
    # Indicadores generales
    # ---------------------------------------------------------
    total_periodo = len(df_prod)
    total_cerradas = len(df_prod_cerradas)
    operadores_activos = len(prod_data)
    dias_periodo = (prod_hasta - prod_desde).days + 1
    promedio_dia = total_cerradas / dias_periodo if dias_periodo else 0

    st.markdown("---")
    st.info(
        f"🔎 **Productividad:** {prod_desde.strftime('%d/%m/%Y')} al "
        f"{prod_hasta.strftime('%d/%m/%Y')} | **Sucursal:** {sucursal} | "
        f"**Fecha utilizada:** {col_fecha_medicion}"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Órdenes del período", fmt(total_periodo))
    c2.metric("Órdenes cerradas", fmt(total_cerradas))
    c3.metric("Operadores activos", fmt(operadores_activos))
    c4.metric("Promedio cierres/día", f"{promedio_dia:.1f}")

    # ---------------------------------------------------------
    # Rendimiento detallado
    # ---------------------------------------------------------
    st.markdown("### 📋 Rendimiento detallado")

    if prod_data.empty:
        st.warning("No se encontraron órdenes cerradas para el período seleccionado.")
    else:
        grafico_data = prod_data.set_index("Confeccionada Por")[
            ["Total Órdenes", "Órdenes Cerradas"]
        ]
        st.bar_chart(grafico_data)
        st.dataframe(
            prod_data,
            use_container_width=True,
            hide_index=True
        )

        st.success(
            f"TOTAL DE ÓRDENES CERRADAS: **{fmt(total_cerradas)}**"
        )

    # ---------------------------------------------------------
    # Productividad día por día
    # ---------------------------------------------------------
    st.markdown("### 📅 Productividad día por día")

    rango_dias = pd.date_range(
        fecha_inicio_prod,
        fecha_fin_exclusiva_prod - pd.Timedelta(days=1),
        freq="D"
    )

    if df_prod_cerradas.empty:
        diario = pd.DataFrame({"Fecha": rango_dias, "Órdenes Cerradas": [0] * len(rango_dias)})
        st.info("No hay cierres para mostrar día por día en el período seleccionado.")
    else:
        df_prod_cerradas["_dia"] = df_prod_cerradas["_fecha_productividad"].dt.normalize()
        conteos_diarios = df_prod_cerradas.groupby("_dia").size()
        diario = pd.DataFrame({"Fecha": rango_dias})
        diario["Órdenes Cerradas"] = diario["Fecha"].map(conteos_diarios).fillna(0).astype(int)

    diario_mostrar = diario.copy()
    diario_mostrar["Fecha"] = diario_mostrar["Fecha"].dt.strftime("%d/%m/%Y")
    st.dataframe(diario_mostrar, use_container_width=True, hide_index=True)
    st.bar_chart(diario.set_index("Fecha")["Órdenes Cerradas"])

    dia_max = diario.loc[diario["Órdenes Cerradas"].idxmax()] if not diario.empty else None
    dias_con_cierre = int((diario["Órdenes Cerradas"] > 0).sum()) if not diario.empty else 0
    d1, d2, d3 = st.columns(3)
    d1.metric("Días con cierres", fmt(dias_con_cierre))
    d2.metric("Promedio en días con cierre", f"{safe_div(total_cerradas, dias_con_cierre):.1f}")
    d3.metric("Mejor día", f"{int(dia_max['Órdenes Cerradas'])} OS · {dia_max['Fecha'].strftime('%d/%m/%Y')}" if dia_max is not None else "0")

    # ---------------------------------------------------------
    # Matriz operador / día
    # ---------------------------------------------------------
    st.markdown("### 👤📅 Cierres por operador por día")

    if df_prod_cerradas.empty:
        st.info("No hay datos para construir la matriz.")
    else:
        matriz = pd.pivot_table(
            df_prod_cerradas,
            index="_usuario_productividad",
            columns="_dia",
            values="_estado_productividad",
            aggfunc="count",
            fill_value=0
        )

        matriz = matriz.reindex(
            columns=rango_dias,
            fill_value=0
        )

        matriz["TOTAL"] = matriz.sum(axis=1)
        matriz = matriz.sort_values("TOTAL", ascending=False)
        matriz = matriz.reset_index()
        matriz = matriz.rename(
            columns={"_usuario_productividad": "Confeccionada Por"}
        )

        nuevas_columnas = []
        for c in matriz.columns:
            if c == "Confeccionada Por" or c == "TOTAL":
                nuevas_columnas.append(c)
            else:
                nuevas_columnas.append(pd.Timestamp(c).strftime("%d/%m"))
        matriz.columns = nuevas_columnas

        st.dataframe(
            matriz,
            use_container_width=True,
            hide_index=True
        )

    # ---------------------------------------------------------
    # Casos de trabajo cerrados por operador
    # ---------------------------------------------------------
    st.markdown("### 🧰 Casos de trabajo cerrados por operador")

    if df_prod_cerradas.empty:
        st.info("No hay casos de trabajo cerrados para el período seleccionado.")
    else:
        # Usamos exclusivamente las columnas internas de Productividad,
        # evitando depender de nombres reales duplicados del archivo.
        df_casos_cerrados = df_prod_cerradas.copy()

        # Reforzar aquí la clasificación de reparaciones desde Tipo de OS.
        # Esto garantiza que esas OS se cuenten aunque Caso Asociado venga
        # vacío o con una variante de texto en el archivo original.
        if col.get("tipo_os") and col["tipo_os"] in df_casos_cerrados.columns:
            _tipo_prod_norm = (
                df_casos_cerrados[col["tipo_os"]]
                .fillna("")
                .astype(str)
                .map(norm)
            )
            df_casos_cerrados.loc[
                _tipo_prod_norm == norm(TIPO_OS_REPARACIONES),
                "_caso"
            ] = CASO_REPARACIONES

        # Usar la categoría interna _caso ya normalizada al cargar el archivo.
        # Esto es importante porque allí se incorporan las OS por
        # Reparaciones/Instalaciones Internas detectadas desde "Tipo de OS".
        # Si se vuelve a leer col["caso"], esas órdenes pueden tener el
        # "Caso Asociado" vacío y quedan afuera del conteo.
        df_casos_cerrados["_caso_productividad"] = (
            df_casos_cerrados["_caso"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        # Solo los tipos de casos definidos para el análisis.
        df_casos_cerrados = df_casos_cerrados[
            df_casos_cerrados["_caso_productividad"].isin(CASOS)
        ].copy()

        if df_casos_cerrados.empty:
            st.info(
                "No hay casos de trabajo de los tipos seleccionados "
                "para el período de productividad."
            )
        else:
            casos_operador = pd.crosstab(
                df_casos_cerrados["_usuario_productividad"],
                df_casos_cerrados["_caso_productividad"]
            )

            # Asegurar que aparezcan siempre las columnas de CASOS
            # en el mismo orden, aunque algún caso tenga 0.
            casos_operador = casos_operador.reindex(
                columns=CASOS,
                fill_value=0
            )

            casos_operador["TOTAL"] = casos_operador.sum(axis=1)

            casos_operador = casos_operador.sort_values(
                "TOTAL",
                ascending=False
            ).reset_index()

            casos_operador = casos_operador.rename(
                columns={
                    "_usuario_productividad": "Confeccionada Por"
                }
            )

            st.dataframe(
                casos_operador,
                use_container_width=True,
                hide_index=True
            )

            st.markdown("### 🔎 Cierres detallados por operador, día y caso")
            detalle_operador_dia_caso = (
                df_casos_cerrados
                .groupby(["_usuario_productividad", "_dia", "_caso_productividad"])
                .size()
                .reset_index(name="OS Cerradas")
                .rename(columns={
                    "_usuario_productividad": "Confeccionada Por",
                    "_dia": "Fecha",
                    "_caso_productividad": "Caso asociado"
                })
                .sort_values(["Fecha", "Confeccionada Por", "Caso asociado"])
            )
            detalle_operador_dia_caso["Fecha"] = detalle_operador_dia_caso["Fecha"].dt.strftime("%d/%m/%Y")
            st.dataframe(detalle_operador_dia_caso, use_container_width=True, hide_index=True)

            st.markdown("### 📊 Distribución de cierres por operador y caso")
            grafico_casos = casos_operador.set_index("Confeccionada Por")[CASOS]
            st.bar_chart(grafico_casos)

    # ---------------------------------------------------------
    # Control técnico específico de Productividad
    # ---------------------------------------------------------
    with st.expander("🔧 Control de Productividad"):
        st.write("Columna de fecha utilizada:", col_fecha_medicion)
        st.write("Columna de usuario utilizada:", col_usuario)
        st.write("Columna de estado utilizada:", col_estado_prod)
        st.write("Columna de sucursal utilizada:", col_sucursal_prod)
        st.write("Fecha desde:", prod_desde)
        st.write("Fecha hasta:", prod_hasta)
        st.write("Inicio real del filtro:", fecha_inicio_prod)
        st.write("Fin exclusivo real del filtro:", fecha_fin_exclusiva_prod)
        st.write("Registros encontrados en período:", len(df_prod))
        st.write("Registros CERRADA:", len(df_prod_cerradas))
        st.write("Estados dentro del período:")
        st.dataframe(
            df_prod["_estado_productividad"]
            .value_counts()
            .rename_axis("Estado")
            .reset_index(name="Cantidad"),
            use_container_width=True,
            hide_index=True
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


# ============================================================
# TAB 6 - PROYECCIÓN
# ============================================================

with tabs[5]:
    st.subheader("📈 Proyección operativa del período asignado")
    st.write(
        "La proyección parte del backlog pendiente al cierre del período elegido. "
        "El ingreso diario se calcula automáticamente como el promedio de **OS de INSTALACION "
        "que ingresaron en estado pendiente** durante el mismo período."
    )

    # La referencia de ingreso siempre se calcula sobre INSTALACION pendiente,
    # aunque el filtro de casos seleccione otros tipos para el análisis general.
    base_ingreso_instalacion = df[
        (df["_sucursal"].isin(sucursal)) &
        (df["_fecha"].notna()) &
        (df["_fecha"] >= start) &
        (df["_fecha"] < end_exclusive) &
        (df["_caso"] == "INSTALACION") &
        (df["_estado"].isin(PENDIENTES))
    ].copy()

    dias_periodo_general = (fecha_hasta - fecha_desde).days + 1
    promedio_instalaciones_pendientes_dia = safe_div(
        len(base_ingreso_instalacion), dias_periodo_general
    )

    pc1, pc2, pc3 = st.columns(3)
    pc1.metric("Backlog pendiente al cierre", fmt(len(pendientes)))
    pc2.metric("Instalaciones pendientes ingresadas", fmt(len(base_ingreso_instalacion)))
    pc3.metric("Promedio ingreso diario", f"{promedio_instalaciones_pendientes_dia:.1f} OS/día")
    st.caption(
        f"Cálculo: {fmt(len(base_ingreso_instalacion))} instalaciones pendientes ingresadas / "
        f"{fmt(dias_periodo_general)} días del período seleccionado."
    )

    p1, p2, p3 = st.columns(3)
    with p1:
        q = st.number_input("Cuadrillas para proyección", 1, 50, 5, key="pq")
    with p2:
        prod = st.number_input("Trabajos/cuadrilla/día", 1, 30, 5, key="pp")
    with p3:
        nuevos = st.number_input(
            "Nuevas OS/día (promedio automático)",
            0.0, 10000.0,
            float(round(promedio_instalaciones_pendientes_dia, 1)),
            step=1.0, key="pn"
        )

    max_dias = st.number_input("Máximo de días a proyectar", 7, 3650, 180, key="max_dias_proy")
    capacidad = q * prod
    saldo = capacidad - nuevos
    pendientes_n = len(pendientes)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capacidad diaria", fmt(capacidad))
    c2.metric("Ingreso diario", f"{nuevos:.1f}")
    c3.metric("Reducción neta diaria", f"{max(saldo, 0):.1f}")
    c4.metric("Cobertura capacidad/ingreso", f"{safe_div(capacidad, nuevos):.2f}x" if nuevos else "∞")

    rows = []
    backlog = float(pendientes_n)
    fecha = fecha_hasta
    for i in range(1, int(max_dias) + 1):
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
        st.warning(
            "⚠️ La capacidad diaria no supera el ingreso promedio de instalaciones pendientes. "
            "El backlog no se reduce de forma sostenible con este escenario."
        )
    elif not proj.empty:
        st.dataframe(proj, use_container_width=True, hide_index=True)
        st.line_chart(proj.set_index("Fecha")["Backlog final"])
        fin = proj.iloc[-1]
        dias_teoricos = pendientes_n / saldo if saldo > 0 else 0
        st.info(
            f"Con los parámetros actuales, la reducción neta es de **{saldo:.1f} OS/día** y "
            f"se requieren aproximadamente **{dias_teoricos:.1f} días** para absorber el backlog "
            f"si el ingreso se mantiene en el promedio histórico."
        )
        if fin["Backlog final"] <= 0:
            st.success(f"🎯 El backlog llega a cero el **{fin['Fecha'].strftime('%d/%m/%Y')}**.")
        else:
            st.info(f"Después de {int(fin['Día'])} días quedan aproximadamente **{fmt(fin['Backlog final'])} OS**.")

    st.markdown("### 🧭 Consideraciones y propuestas")
    propuestas = []
    mayores_30 = int((pendientes["antiguedad"] > 30).sum()) if not pendientes.empty else 0
    if pendientes_n and promedio_instalaciones_pendientes_dia >= capacidad:
        propuestas.append("La capacidad no alcanza el ingreso promedio de instalaciones pendientes; se debe aumentar capacidad, productividad o ambas.")
    if mayores_30:
        propuestas.append(f"Priorizar las {fmt(mayores_30)} OS con más de 30 días con seguimiento diario hasta su cierre.")
    if total_cerradas > 0 and promedio_instalaciones_pendientes_dia > promedio_dia:
        propuestas.append("El ingreso promedio de instalaciones pendientes supera el promedio de cierres; conviene revisar capacidad y distribución del trabajo.")
    if not propuestas:
        propuestas.append("Mantener control semanal de backlog, ingreso y cierres para recalibrar la proyección con datos reales.")
    for propuesta in propuestas:
        st.markdown(f"- {propuesta}")

# ============================================================
# GENERADOR DE PDF - INFORME EJECUTIVO
# ============================================================
def generar_pdf_informe(export_desde=None, export_hasta=None):
    """Genera un informe PDF dinámico con el mismo enfoque visual.
    Si se reciben export_desde/export_hasta, el informe usa ese período
    independientemente del período general de la barra lateral.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            PageBreak, KeepTogether
        )
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
        from reportlab.graphics.charts.legends import Legend
        from reportlab.lib.colors import HexColor
    except ImportError as e:
        raise RuntimeError(
            "Para generar PDF falta la librería reportlab. "
            "Instalala con: pip install reportlab"
        ) from e

    # ---------------------------------------------------------
    # Período específico de exportación
    # ---------------------------------------------------------
    if export_desde is not None and export_hasta is not None:
        _export_start = pd.Timestamp(export_desde)
        _export_end = pd.Timestamp(export_hasta)

        # Recalculamos la base para que el PDF respete el período elegido
        # en la pestaña Exportar y no el período de la barra lateral.
        base = df[
            (df["_sucursal"].isin(sucursal)) &
            (df["_fecha"].notna()) &
            (df["_fecha"] >= _export_start.normalize()) &
            (df["_fecha"] < (_export_end.normalize() + pd.Timedelta(days=1))) &
            (df["_caso"].isin(casos))
        ].copy()

        base["antiguedad"] = (_export_end - base["_fecha"]).dt.days
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

        entradas_periodo = base[
            (base["_fecha"] >= _export_start) &
            (base["_fecha"] <= _export_end)
        ].copy()

        tabla = pd.crosstab(base["_caso"], base["situacion"])
        for _estado in ["Realizado", "Falta hacer", "Anulado", "Otro estado"]:
            if _estado not in tabla.columns:
                tabla[_estado] = 0
        tabla["Total"] = tabla.sum(axis=1)
        tabla = tabla.reset_index().rename(columns={"_caso": "Caso"})
        tabla = tabla[["Caso", "Realizado", "Falta hacer", "Anulado", "Otro estado", "Total"]]
    else:
        _export_start = pd.Timestamp(fecha_desde)
        _export_end = pd.Timestamp(fecha_hasta)

    # ---------------------------------------------------------
    # Productividad y proyección calculadas para EL MISMO período
    # que se está exportando (incluye períodos personalizados).
    # ---------------------------------------------------------
    _pdf_prod_all = df.copy()
    _pdf_prod_all["_pdf_fecha"] = pd.to_datetime(_pdf_prod_all[col_fecha_medicion], errors="coerce", dayfirst=True)
    _pdf_prod_all["_pdf_usuario"] = _pdf_prod_all[col_usuario].fillna("").astype(str).str.strip()
    _pdf_prod_all["_pdf_estado"] = _pdf_prod_all[col_estado_prod].fillna("").astype(str).str.strip().str.upper()
    _pdf_prod_all["_pdf_sucursal"] = _pdf_prod_all[col_sucursal_prod].fillna("").astype(str).str.strip().str.upper()
    _pdf_prod_all = _pdf_prod_all[
        _pdf_prod_all["_pdf_fecha"].notna()
        & (_pdf_prod_all["_pdf_fecha"] >= _export_start.normalize())
        & (_pdf_prod_all["_pdf_fecha"] < (_export_end.normalize() + pd.Timedelta(days=1)))
        & (_pdf_prod_all["_pdf_sucursal"].isin([str(x).strip().upper() for x in sucursal]))
        & (_pdf_prod_all["_caso"].isin(casos))
    ].copy()
    _pdf_prod = _pdf_prod_all[
        (_pdf_prod_all["_pdf_estado"] == "CERRADA")
        & _pdf_prod_all["_pdf_usuario"].ne("")
        & _pdf_prod_all["_pdf_usuario"].str.upper().ne("NAN")
        & _pdf_prod_all["_pdf_usuario"].str.upper().ne("NONE")
    ].copy()
    _pdf_prod["_pdf_dia"] = _pdf_prod["_pdf_fecha"].dt.normalize()

    _pdf_totales_usuario = _pdf_prod_all.groupby("_pdf_usuario").size().reset_index(name="Total Órdenes") if not _pdf_prod_all.empty else pd.DataFrame(columns=["_pdf_usuario", "Total Órdenes"])
    _pdf_cerradas_usuario = _pdf_prod.groupby("_pdf_usuario").size().reset_index(name="Órdenes Cerradas") if not _pdf_prod.empty else pd.DataFrame(columns=["_pdf_usuario", "Órdenes Cerradas"])
    _pdf_prod_data = _pdf_totales_usuario.merge(_pdf_cerradas_usuario, on="_pdf_usuario", how="left")
    if not _pdf_prod_data.empty:
        _pdf_prod_data["Órdenes Cerradas"] = _pdf_prod_data["Órdenes Cerradas"].fillna(0).astype(int)
        _pdf_prod_data["Efectividad Cierre (%)"] = (_pdf_prod_data["Órdenes Cerradas"].div(_pdf_prod_data["Total Órdenes"].replace(0, pd.NA)).fillna(0).mul(100).round(1))
        _pdf_prod_data = _pdf_prod_data.rename(columns={"_pdf_usuario": "Confeccionada Por"}).sort_values("Órdenes Cerradas", ascending=False)
    else:
        _pdf_prod_data = pd.DataFrame(columns=["Confeccionada Por", "Total Órdenes", "Órdenes Cerradas", "Efectividad Cierre (%)"])

    _pdf_rango_dias = pd.date_range(_export_start.normalize(), _export_end.normalize(), freq="D")
    _pdf_conteos_dia = _pdf_prod.groupby("_pdf_dia").size() if not _pdf_prod.empty else pd.Series(dtype=float)
    _pdf_diario = pd.DataFrame({"Fecha": _pdf_rango_dias})
    _pdf_diario["Órdenes Cerradas"] = _pdf_diario["Fecha"].map(_pdf_conteos_dia).fillna(0).astype(int)

    if not _pdf_prod.empty:
        _pdf_casos_operador = pd.crosstab(_pdf_prod["_pdf_usuario"], _pdf_prod["_caso"]).reindex(columns=casos, fill_value=0)
        _pdf_casos_operador["TOTAL"] = _pdf_casos_operador.sum(axis=1)
        _pdf_casos_operador = _pdf_casos_operador.sort_values("TOTAL", ascending=False).reset_index().rename(columns={"_pdf_usuario": "Confeccionada Por"})
        _pdf_detalle_odc = (_pdf_prod.groupby(["_pdf_usuario", "_pdf_dia", "_caso"]).size().reset_index(name="OS Cerradas").rename(columns={"_pdf_usuario": "Confeccionada Por", "_pdf_dia": "Fecha", "_caso": "Caso asociado"}).sort_values(["Fecha", "Confeccionada Por", "Caso asociado"]))
    else:
        _pdf_casos_operador = pd.DataFrame(columns=["Confeccionada Por"] + casos + ["TOTAL"])
        _pdf_detalle_odc = pd.DataFrame(columns=["Confeccionada Por", "Fecha", "Caso asociado", "OS Cerradas"])

    # Proyección: backlog del período + promedio automático de instalaciones pendientes.
    _pdf_ingreso_inst = df[
        (df["_sucursal"].isin(sucursal)) & (df["_fecha"].notna())
        & (df["_fecha"] >= _export_start.normalize())
        & (df["_fecha"] < (_export_end.normalize() + pd.Timedelta(days=1)))
        & (df["_caso"] == "INSTALACION") & (df["_estado"].isin(PENDIENTES))
    ]
    _pdf_dias_periodo = (_export_end.date() - _export_start.date()).days + 1
    _pdf_ingreso_prom = safe_div(len(_pdf_ingreso_inst), _pdf_dias_periodo)
    _pdf_q = int(q) if "q" in globals() else 5
    _pdf_prod_dia = int(prod) if "prod" in globals() else 5
    _pdf_capacidad = _pdf_q * _pdf_prod_dia
    _pdf_proj_rows = []
    _pdf_backlog = float(len(pendientes))
    _pdf_fecha = _export_end.date()
    _pdf_max_dias = int(max_dias) if "max_dias" in globals() else 180
    for _i in range(1, _pdf_max_dias + 1):
        if _pdf_backlog <= 0:
            break
        _inicio = _pdf_backlog
        _realizadas = min(_pdf_capacidad, _pdf_backlog)
        _pdf_backlog = max(0, _pdf_backlog - _realizadas + _pdf_ingreso_prom)
        _pdf_fecha += timedelta(days=1)
        _pdf_proj_rows.append({"Día": _i, "Fecha": _pdf_fecha, "Backlog inicio": round(_inicio,1), "Trabajos realizados": round(_realizadas,1), "Nuevas OS": round(_pdf_ingreso_prom,1), "Backlog final": round(_pdf_backlog,1)})
    _pdf_proj = pd.DataFrame(_pdf_proj_rows)

    pdf_buffer = io.BytesIO()

    # Paleta inspirada en el informe compartido.
    azul = colors.HexColor("#1F4E79")
    azul_claro = colors.HexColor("#D9EAF7")
    gris = colors.HexColor("#666666")
    gris_claro = colors.HexColor("#F2F2F2")
    negro = colors.HexColor("#111111")
    blanco = colors.white

    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=1.45*cm,
        leftMargin=1.45*cm,
        topMargin=1.35*cm,
        bottomMargin=1.35*cm,
        title="Análisis y gestión de Órdenes de Servicio",
        author="Gestión de Órdenes de Servicio",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="TituloInforme",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        textColor=negro,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SubtituloInforme",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        alignment=TA_CENTER,
        textColor=negro,
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="FechaInforme",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=12,
        alignment=TA_CENTER,
        textColor=gris,
        spaceAfter=16,
    ))
    styles.add(ParagraphStyle(
        name="SeccionInforme",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=azul,
        spaceBefore=5,
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="SubseccionInforme",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=azul,
        spaceBefore=5,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="TextoInforme",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=13,
        textColor=negro,
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="TextoNegrita",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=9.2,
        leading=13,
        textColor=negro,
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="PieInforme",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=gris,
    ))

    def P(text, style="TextoInforme"):
        return Paragraph(str(text), styles[style])

    def moneyless(n):
        try:
            return fmt(n)
        except Exception:
            return str(n)

    def table_pdf(data, widths=None, header=True, font_size=7.5):
        # Convertimos todo a Paragraph para que las tablas largas no se desborden.
        converted = []
        for r, row in enumerate(data):
            converted.append([
                Paragraph(str(v), ParagraphStyle(
                    name=f"cell_{r}_{i}",
                    fontName="Helvetica-Bold" if (header and r == 0) else "Helvetica",
                    fontSize=font_size,
                    leading=font_size + 2,
                    textColor=blanco if (header and r == 0) else negro,
                ))
                for i, v in enumerate(row)
            ])
        t = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands = [
            ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#888888")),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ("TOPPADDING", (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ]
        if header:
            commands += [
                ("BACKGROUND", (0,0), (-1,0), azul),
                ("TEXTCOLOR", (0,0), (-1,0), blanco),
            ]
            if len(converted) > 1:
                commands.append(("ROWBACKGROUNDS", (0,1), (-1,-1), [blanco, gris_claro]))
        t.setStyle(TableStyle(commands))
        return t

    def grafico_barras_simple(labels, valores, titulo, ancho=17*cm, alto=7*cm):
        """Gráfico de barras compacto, con estética similar al informe de referencia."""
        d = Drawing(ancho, alto)
        chart = VerticalBarChart()
        chart.x = 38
        chart.y = 28
        chart.width = ancho - 55
        chart.height = alto - 48
        chart.data = [list(map(float, valores))]
        chart.categoryAxis.categoryNames = [str(x)[:18] for x in labels]
        chart.valueAxis.valueMin = 0
        max_val = max([float(x) for x in valores], default=1)
        chart.valueAxis.valueMax = max(1, max_val * 1.18)
        chart.valueAxis.valueStep = max(1, round(chart.valueAxis.valueMax / 5))
        chart.bars[0].fillColor = azul
        chart.bars[0].strokeColor = azul
        chart.categoryAxis.labels.fontName = "Helvetica"
        chart.categoryAxis.labels.fontSize = 6.5
        chart.categoryAxis.labels.angle = 35
        chart.valueAxis.labels.fontName = "Helvetica"
        chart.valueAxis.labels.fontSize = 7
        chart.valueAxis.strokeColor = colors.HexColor("#999999")
        chart.categoryAxis.strokeColor = colors.HexColor("#999999")
        d.add(chart)
        d.add(Paragraph(str(titulo), ParagraphStyle(
            name="GraficoTitulo",
            fontName="Helvetica",
            fontSize=9,
            leading=11,
            alignment=TA_CENTER,
            textColor=negro,
        )))
        return d

    def pie_pagina(canvas, doc_obj):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D0D0D0"))
        canvas.line(doc_obj.leftMargin, 0.95*cm, A4[0]-doc_obj.rightMargin, 0.95*cm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(gris)
        canvas.drawString(doc_obj.leftMargin, 0.58*cm, "Gestión de Órdenes de Servicio")
        canvas.drawRightString(A4[0]-doc_obj.rightMargin, 0.58*cm, f"Página {doc_obj.page}")
        canvas.restoreState()

    suc_txt = ", ".join(sucursal) if sucursal else "Todas"
    periodo_txt = f"{_export_start.strftime('%d/%m/%Y')} al {_export_end.strftime('%d/%m/%Y')}"
    fecha_generacion = date.today().strftime("%d/%m/%Y")

    total_base = len(base)
    total_realizados = len(realizados)
    total_pendientes = len(pendientes)
    total_anulados = len(anulados)
    total_otros = len(otros)

    edad_prom = pendientes["antiguedad"].mean() if not pendientes.empty else 0
    edad_mediana = pendientes["antiguedad"].median() if not pendientes.empty else 0
    edad_max = pendientes["antiguedad"].max() if not pendientes.empty else 0
    pendientes_10 = int((pendientes["antiguedad"] >= 10).sum()) if not pendientes.empty else 0

    # Entradas diarias del período general.
    entradas_diarias = (
        entradas_periodo.groupby(entradas_periodo["_fecha"].dt.normalize()).size()
        if not entradas_periodo.empty else pd.Series(dtype=float)
    )
    ingreso_prom = float(entradas_diarias.mean()) if not entradas_diarias.empty else 0

    # Productividad del período realmente exportado.
    prod_cierres = int(len(_pdf_prod))
    prod_dias = (_export_end.date() - _export_start.date()).days + 1
    prod_prom_dia = safe_div(prod_cierres, prod_dias)
    ingreso_instalaciones_pendientes_pdf = float(_pdf_ingreso_prom)
    capacidad_actual = _pdf_capacidad
    saldo_actual = _pdf_capacidad - _pdf_ingreso_prom

    story = []

    story += [
        P("ANÁLISIS Y GESTIÓN DE ÓRDENES DE SERVICIO", "TituloInforme"),
        P("Situación actual, productividad y proyección operativa", "SubtituloInforme"),
        P(f"Información analizada al {fecha_generacion} | Período: {periodo_txt} | Sucursal: {suc_txt}", "FechaInforme"),
        P("1. Resumen ejecutivo", "SeccionInforme"),
    ]

    story.append(P(
        f"<b>Situación actual.</b> El período seleccionado contiene <b>{moneyless(total_base)}</b> órdenes "
        f"de servicio de los casos seleccionados. Al cierre del período hay <b>{moneyless(total_pendientes)}</b> "
        f"órdenes pendientes, <b>{moneyless(total_realizados)}</b> realizadas, <b>{moneyless(total_anulados)}</b> anuladas "
        f"y <b>{moneyless(total_otros)}</b> en otros estados."
    ))
    story.append(P(
        f"<b>Antigüedad.</b> Entre las órdenes pendientes, la antigüedad promedio es de "
        f"<b>{edad_prom:.1f} días</b>, la mediana es de <b>{edad_mediana:.0f} días</b> y la máxima es de "
        f"<b>{edad_max:.0f} días</b>. Hay <b>{moneyless(pendientes_10)}</b> órdenes con 10 días o más."
    ))
    story.append(P(
        f"<b>Productividad.</b> Para el período exportado se registraron "
        f"<b>{moneyless(prod_cierres)}</b> cierres, con un promedio de <b>{prod_prom_dia:.1f} cierres/día</b>. "
        f"La medición utiliza la fecha de calendario y el estado CERRADA, respetando sucursal/es y casos seleccionados."
    ))
    if capacidad_actual is not None:
        story.append(P(
            f"<b>Proyección.</b> Con {q} cuadrillas a {prod} trabajos por cuadrilla/día y "
            f"{ingreso_instalaciones_pendientes_pdf:.1f} nuevas OS/día (promedio histórico automático), "
            f"la capacidad calculada es de <b>{moneyless(capacidad_actual)}</b> trabajos/día "
            f"y el saldo neto es de <b>{moneyless(saldo_actual)}</b> OS/día."
        ))

    story += [Spacer(1, 4), P("2. Indicadores principales", "SeccionInforme")]
    indicadores = [
        ["Indicador", "Resultado", "Interpretación", "Fuente"],
        ["Órdenes del período", moneyless(total_base), "Cartera considerada", "Órdenes de servicio"],
        ["Órdenes pendientes", moneyless(total_pendientes), "Situación al final del período", "Órdenes de servicio"],
        ["Antigüedad promedio", f"{edad_prom:.1f} días", "Demora media de pendientes", "Cálculo"],
        ["Pendientes con 10+ días", moneyless(pendientes_10), "Grupo prioritario", "Cálculo"],
        ["Órdenes realizadas", moneyless(total_realizados), "Estado CERRADA", "Órdenes de servicio"],
        ["Cierres productividad", moneyless(prod_cierres), "Período de productividad", "Fecha Calendario"],
        ["Promedio cierres/día", f"{prod_prom_dia:.1f}", "Media del período elegido", "Cálculo"],
        ["Ingreso diario instalaciones pendientes", f"{ingreso_instalaciones_pendientes_pdf:.1f}", "Promedio automático para proyección", "Fecha Creación + Estado"],
    ]
    story.append(table_pdf(indicadores, widths=[4.1*cm, 2.6*cm, 5.0*cm, 4.0*cm], font_size=7.1))

    story += [Spacer(1, 9), P("3. Situación por caso asociado", "SeccionInforme")]
    caso_rows = [["Caso asociado", "Realizado", "Falta hacer", "Anulado", "Otros", "Total"]]
    if not tabla.empty:
        for _, r in tabla.iterrows():
            caso_rows.append([
                r.get("Caso", ""),
                moneyless(r.get("Realizado", 0)),
                moneyless(r.get("Falta hacer", 0)),
                moneyless(r.get("Anulado", 0)),
                moneyless(r.get("Otro estado", 0)),
                moneyless(r.get("Total", 0)),
            ])
    story.append(table_pdf(caso_rows, widths=[5.1*cm, 2.1*cm, 2.3*cm, 2.1*cm, 1.8*cm, 2.0*cm], font_size=7.2))

    if not tabla.empty:
        try:
            caso_labels = tabla["Caso"].astype(str).tolist()
            caso_vals = tabla["Realizado"].fillna(0).astype(float).tolist()
            story += [Spacer(1, 8), grafico_barras_simple(caso_labels, caso_vals, "Órdenes realizadas por caso asociado")]
        except Exception:
            pass

    story += [PageBreak(), P("4. Productividad por personal", "SeccionInforme")]
    story.append(P(
        f"Período de productividad: <b>{_export_start.strftime('%d/%m/%Y')}</b> al "
        f"<b>{_export_end.strftime('%d/%m/%Y')}</b>. Sucursal/es: <b>{suc_txt}</b>. "
        f"Fecha utilizada: <b>{col_fecha_medicion}</b>."
    ))
    if not _pdf_prod_data.empty:
        rows_prod = [["Confeccionada Por", "Total Órdenes", "Órdenes Cerradas", "Efectividad Cierre (%)"]]
        for _, r in _pdf_prod_data.iterrows():
            rows_prod.append([
                r.get("Confeccionada Por", ""),
                moneyless(r.get("Total Órdenes", 0)),
                moneyless(r.get("Órdenes Cerradas", 0)),
                f"{float(r.get('Efectividad Cierre (%)', 0)):.1f}",
            ])
        story.append(table_pdf(rows_prod, widths=[6.4*cm, 3.0*cm, 3.2*cm, 4.0*cm], font_size=7.4))
        try:
            top_prod = _pdf_prod_data.head(12)
            story += [Spacer(1, 8), grafico_barras_simple(
                top_prod["Confeccionada Por"].astype(str).tolist(),
                top_prod["Órdenes Cerradas"].astype(float).tolist(),
                "Órdenes cerradas por operador"
            )]
        except Exception:
            pass
    else:
        story.append(P("No se encontraron datos de productividad para el período seleccionado."))

    story += [Spacer(1, 10), P("5. Cierres por operador por día", "SeccionInforme")]
    if not _pdf_prod.empty:
        mat = pd.crosstab(_pdf_prod["_pdf_usuario"], _pdf_prod["_pdf_dia"]).reindex(columns=_pdf_rango_dias, fill_value=0)
        mat = mat.reset_index().rename(columns={"_pdf_usuario": "Confeccionada Por"})
        mat["TOTAL"] = mat.drop(columns=["Confeccionada Por"]).sum(axis=1)
        # Limitar la matriz a un máximo razonable para el PDF; la app conserva todos los datos.
        cols = list(mat.columns)
        if len(cols) > 15:
            cols = [cols[0]] + cols[1:15] + (["TOTAL"] if "TOTAL" in cols else [])
            mat = mat[cols]
        story.append(table_pdf([list(mat.columns)] + mat.astype(str).values.tolist(), font_size=6.2))
    else:
        story.append(P("No hay cierres para mostrar."))

    story += [Spacer(1, 8), P("5.1 Detalle de cierres por operador, día y caso", "SeccionInforme")]

    # En lugar de una única tabla con una fila por operador + fecha + caso,
    # se genera una tabla INDIVIDUAL para cada operador. De esta manera el
    # nombre del operador no se repite en cada fila y el informe resulta
    # mucho más compacto y fácil de leer.
    if not _pdf_prod.empty:
        _casos_pdf_orden = list(casos)

        _operadores_pdf = (
            _pdf_prod["_pdf_usuario"]
            .dropna()
            .astype(str)
            .str.strip()
        )
        _operadores_pdf = sorted(
            [x for x in _operadores_pdf.unique() if x and x.upper() not in ("NAN", "NONE")],
            key=str.lower
        )

        for _operador in _operadores_pdf:
            _op = _pdf_prod[_pdf_prod["_pdf_usuario"].astype(str).str.strip() == _operador].copy()
            if _op.empty:
                continue

            _op["_fecha_dia"] = _op["_pdf_dia"].dt.normalize()

            _tabla_op = pd.crosstab(
                _op["_fecha_dia"],
                _op["_caso"]
            ).reindex(columns=_casos_pdf_orden, fill_value=0)

            # Solo mostramos los días en los que el operador tuvo al menos
            # un cierre. Esto evita llenar el informe de filas con ceros.
            _tabla_op = _tabla_op.loc[_tabla_op.sum(axis=1) > 0].copy()

            if _tabla_op.empty:
                continue

            _tabla_op.insert(0, "Fecha", _tabla_op.index)
            _tabla_op = _tabla_op.reset_index(drop=True)
            _tabla_op["TOTAL"] = _tabla_op[_casos_pdf_orden].sum(axis=1)
            _tabla_op["Fecha"] = pd.to_datetime(
                _tabla_op["Fecha"], errors="coerce"
            ).dt.strftime("%d/%m/%Y")

            story.append(Spacer(1, 7))
            story.append(P(f"Operador: <b>{_operador}</b>", "SubseccionInforme"))
            story.append(
                table_pdf(
                    [list(_tabla_op.columns)] + _tabla_op.astype(str).values.tolist(),
                    font_size=6.5
                )
            )
    else:
        story.append(P("No hay cierres para mostrar en el detalle por operador."))

    story += [PageBreak(), P("6. Casos de trabajo cerrados por operador", "SeccionInforme")]
    if not _pdf_casos_operador.empty:
        rows_casos = [list(_pdf_casos_operador.columns)] + _pdf_casos_operador.astype(str).values.tolist()
        story.append(table_pdf(rows_casos, font_size=6.8))
    else:
        story.append(P("No hay casos de trabajo cerrados para el período seleccionado."))

    story += [Spacer(1, 10), P("7. Productividad día por día", "SeccionInforme")]
    if not _pdf_diario.empty:
        diario_pdf = _pdf_diario.copy()
        diario_pdf["Fecha"] = pd.to_datetime(diario_pdf["Fecha"], errors="coerce").dt.strftime("%d/%m/%Y")
        story.append(table_pdf([list(diario_pdf.columns)] + diario_pdf.astype(str).values.tolist(), widths=[5*cm, 3.5*cm], font_size=7.2))
    else:
        story.append(P("No hay cierres para mostrar día por día."))

    story += [PageBreak(), P("8. Proyección operativa", "SeccionInforme")]
    story.append(P(
        f"La proyección parte de <b>{moneyless(total_pendientes)}</b> OS pendientes al final del período. "
        f"Los parámetros utilizados en la pestaña de proyección son editables desde la aplicación."
    ))
    if isinstance(_pdf_proj, pd.DataFrame) and not _pdf_proj.empty:
        filas = [["Día", "Fecha", "Backlog inicio", "Trabajos realizados", "Nuevas OS", "Backlog final"]]
        # Mostrar una muestra representativa si son demasiadas filas.
        proj_pdf = _pdf_proj.copy()
        if len(proj_pdf) > 30:
            proj_pdf = pd.concat([proj_pdf.head(15), proj_pdf.tail(15)])
        for _, r in proj_pdf.iterrows():
            filas.append([
                r.get("Día", ""),
                pd.to_datetime(r.get("Fecha"), errors="coerce").strftime("%d/%m/%Y") if pd.notna(r.get("Fecha")) else "",
                r.get("Backlog inicio", ""),
                r.get("Trabajos realizados", ""),
                r.get("Nuevas OS", ""),
                r.get("Backlog final", ""),
            ])
        story.append(table_pdf(filas, widths=[1.2*cm, 3.0*cm, 3.0*cm, 3.1*cm, 2.5*cm, 3.0*cm], font_size=6.8))
        fin = _pdf_proj.iloc[-1]
        if float(fin.get("Backlog final", 1)) <= 0:
            story.append(Spacer(1, 6))
            story.append(P(
                f"<b>Conclusión:</b> el backlog llega a cero el <b>{pd.to_datetime(fin['Fecha']).strftime('%d/%m/%Y')}</b>.",
                "TextoNegrita"
            ))
        else:
            story.append(P(
                f"<b>Conclusión:</b> después de {int(fin.get('Día', 0))} días quedan aproximadamente "
                f"<b>{moneyless(fin.get('Backlog final', 0))} OS</b>.", "TextoNegrita"
            ))
    else:
        story.append(P("No hay una proyección calculada para los parámetros actuales."))

    story += [Spacer(1, 12), P("9. Observaciones y oportunidades de mejora", "SeccionInforme")]
    _obs_pdf = []
    if total_base:
        _pct_pend = safe_div(total_pendientes, total_base) * 100
        _obs_pdf.append(f"La cartera contiene {moneyless(total_base)} OS y finaliza con {moneyless(total_pendientes)} pendientes ({_pct_pend:.1f}%).")
    _mayores_30 = int((pendientes["antiguedad"] > 30).sum()) if not pendientes.empty else 0
    if _mayores_30:
        _obs_pdf.append(f"Hay {moneyless(_mayores_30)} OS con más de 30 días; deben tratarse como cartera crítica.")
    if ingreso_instalaciones_pendientes_pdf > prod_prom_dia and prod_prom_dia > 0:
        _obs_pdf.append("El ingreso promedio de instalaciones pendientes supera el promedio de cierres; sin una mejora de capacidad, el backlog tenderá a crecer.")
    if prod_cierres == 0:
        _obs_pdf.append("No se registran cierres en el período; corresponde revisar fecha de calendario, estados y asignación de responsables.")
    if not _obs_pdf:
        _obs_pdf.append("No se detectaron alertas críticas con los indicadores disponibles. Mantener seguimiento periódico.")
    for _texto in _obs_pdf:
        story.append(P("• " + _texto))

    story += [Spacer(1, 8), P("10. Consideraciones y propuestas", "SeccionInforme")]
    _propuestas_pdf = [
        "Priorizar OS envejecidas y realizar seguimiento diario hasta su cierre.",
        "Monitorear cierres por operador, día y caso para equilibrar cargas y detectar desvíos de producción.",
        "Comparar capacidad efectiva de cuadrillas contra el promedio de ingreso diario de instalaciones pendientes.",
        "Actualizar semanalmente la proyección con el comportamiento real de ingreso y cierres.",
        "Revisar causas de jornadas de baja producción: disponibilidad, asignación, tiempos de traslado, retrabajos y restricciones operativas.",
        "La proyección es un escenario de gestión y no incorpora automáticamente feriados, ausencias, zonas o diferencias de productividad entre cuadrillas."
    ]
    for _texto in _propuestas_pdf:
        story.append(P("• " + _texto))

    doc.build(story, onFirstPage=pie_pagina, onLaterPages=pie_pagina)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


# ============================================================
# TAB 7 - EXPORTAR
# ============================================================

with tabs[6]:
    st.subheader("📥 Exportar resultados")
    st.write(
        "Elegí el período que querés incluir en la exportación. "
        "Este período es independiente del período general de la barra lateral."
    )

    tipo_periodo_export = st.radio(
        "Período de exportación",
        ["Período analizado", "Período personalizado"],
        horizontal=True,
        key="tipo_periodo_export"
    )

    if tipo_periodo_export == "Período analizado":
        export_desde = fecha_desde
        export_hasta = fecha_hasta
        st.info(
            f"Se exportará el período analizado: **{export_desde.strftime('%d/%m/%Y')}** "
            f"al **{export_hasta.strftime('%d/%m/%Y')}**."
        )
    else:
        ec1, ec2 = st.columns(2)
        with ec1:
            export_desde = st.date_input(
                "Desde",
                value=fecha_desde,
                min_value=min_date,
                max_value=max_date,
                key="export_desde_personalizado"
            )
        with ec2:
            export_hasta = st.date_input(
                "Hasta",
                value=fecha_hasta,
                min_value=min_date,
                max_value=max_date,
                key="export_hasta_personalizado"
            )

        if export_desde > export_hasta:
            st.error("La fecha Desde no puede ser posterior a Hasta.")
            st.stop()

        st.success(
            f"Período personalizado seleccionado: **{export_desde.strftime('%d/%m/%Y')}** "
            f"al **{export_hasta.strftime('%d/%m/%Y')}**."
        )

    # ---------------------------------------------------------
    # Construir los datos de exportación para el período elegido
    # ---------------------------------------------------------
    export_start = pd.Timestamp(export_desde)
    export_end = pd.Timestamp(export_hasta)

    base_export = df[
        (df["_sucursal"].isin(sucursal)) &
        (df["_fecha"].notna()) &
        (df["_fecha"] >= export_start.normalize()) &
        (df["_fecha"] < (export_end.normalize() + pd.Timedelta(days=1))) &
        (df["_caso"].isin(casos))
    ].copy()

    base_export["antiguedad"] = (export_end - base_export["_fecha"]).dt.days
    base_export["situacion"] = base_export["_estado"].apply(
        lambda x:
            "Realizado" if x in REALIZADO else
            "Falta hacer" if x in PENDIENTES else
            "Anulado" if x in ANULADO else
            "Otro estado"
    )

    realizados_export = base_export[base_export["situacion"] == "Realizado"].copy()
    pendientes_export = base_export[base_export["situacion"] == "Falta hacer"].copy()
    anulados_export = base_export[base_export["situacion"] == "Anulado"].copy()
    otros_export = base_export[base_export["situacion"] == "Otro estado"].copy()
    pendientes_export["intervalo"] = pendientes_export["antiguedad"].apply(age_bucket)

    entradas_export = base_export.copy()

    tabla_export = pd.crosstab(base_export["_caso"], base_export["situacion"])
    for estado_export in ["Realizado", "Falta hacer", "Anulado", "Otro estado"]:
        if estado_export not in tabla_export.columns:
            tabla_export[estado_export] = 0
    tabla_export["Total"] = tabla_export.sum(axis=1)
    tabla_export = tabla_export.reset_index().rename(columns={"_caso": "Caso"})
    tabla_export = tabla_export[["Caso", "Realizado", "Falta hacer", "Anulado", "Otro estado", "Total"]]

    cruz_export = pd.crosstab(pendientes_export["intervalo"], pendientes_export["_caso"])
    cruz_export = cruz_export.reindex(INTERVALOS, fill_value=0)
    for caso_export in casos:
        if caso_export not in cruz_export.columns:
            cruz_export[caso_export] = 0
    cruz_export = cruz_export[casos]
    cruz_export["TOTAL"] = cruz_export.sum(axis=1)
    total_export = cruz_export.sum(axis=0).to_frame().T
    total_export.index = ["TOTAL"]
    cruz_final_export = pd.concat([cruz_export, total_export])

    # ---------------------------------------------------------
    # Productividad para el mismo período de exportación
    # ---------------------------------------------------------
    export_prod = df.copy()
    export_prod["_fecha_prod_export"] = pd.to_datetime(export_prod[col_fecha_medicion], errors="coerce", dayfirst=True)
    export_prod["_usuario_prod_export"] = export_prod[col_usuario].fillna("").astype(str).str.strip()
    export_prod["_estado_prod_export"] = export_prod[col_estado_prod].fillna("").astype(str).str.strip().str.upper()
    export_prod["_sucursal_prod_export"] = export_prod[col_sucursal_prod].fillna("").astype(str).str.strip().str.upper()
    export_prod = export_prod[
        export_prod["_fecha_prod_export"].notna()
        & (export_prod["_fecha_prod_export"] >= export_start.normalize())
        & (export_prod["_fecha_prod_export"] < export_end.normalize() + pd.Timedelta(days=1))
        & export_prod["_sucursal_prod_export"].isin([str(x).strip().upper() for x in sucursal])
        & export_prod["_caso"].isin(casos)
    ].copy()
    export_prod_cerradas = export_prod[
        (export_prod["_estado_prod_export"] == "CERRADA")
        & export_prod["_usuario_prod_export"].ne("")
        & export_prod["_usuario_prod_export"].str.upper().ne("NAN")
        & export_prod["_usuario_prod_export"].str.upper().ne("NONE")
    ].copy()
    export_prod_cerradas["_dia_prod_export"] = export_prod_cerradas["_fecha_prod_export"].dt.normalize()

    prod_export_operador = export_prod.groupby("_usuario_prod_export").size().reset_index(name="Total Órdenes") if not export_prod.empty else pd.DataFrame(columns=["_usuario_prod_export", "Total Órdenes"])
    cerradas_export_operador = export_prod_cerradas.groupby("_usuario_prod_export").size().reset_index(name="Órdenes Cerradas") if not export_prod_cerradas.empty else pd.DataFrame(columns=["_usuario_prod_export", "Órdenes Cerradas"])
    prod_export_operador = prod_export_operador.merge(cerradas_export_operador, on="_usuario_prod_export", how="left")
    if not prod_export_operador.empty:
        prod_export_operador["Órdenes Cerradas"] = prod_export_operador["Órdenes Cerradas"].fillna(0).astype(int)
        prod_export_operador["Efectividad Cierre (%)"] = prod_export_operador["Órdenes Cerradas"].div(prod_export_operador["Total Órdenes"].replace(0, pd.NA)).fillna(0).mul(100).round(1)
        prod_export_operador = prod_export_operador.rename(columns={"_usuario_prod_export": "Confeccionada Por"}).sort_values("Órdenes Cerradas", ascending=False)

    cierres_export_dia = pd.DataFrame({"Fecha": pd.date_range(export_start.normalize(), export_end.normalize(), freq="D")})
    conteos_export_dia = export_prod_cerradas.groupby("_dia_prod_export").size() if not export_prod_cerradas.empty else pd.Series(dtype=float)
    cierres_export_dia["Órdenes Cerradas"] = cierres_export_dia["Fecha"].map(conteos_export_dia).fillna(0).astype(int)

    casos_export_operador = pd.crosstab(export_prod_cerradas["_usuario_prod_export"], export_prod_cerradas["_caso"]).reindex(columns=casos, fill_value=0) if not export_prod_cerradas.empty else pd.DataFrame(columns=casos)
    if not casos_export_operador.empty:
        casos_export_operador["TOTAL"] = casos_export_operador.sum(axis=1)
        casos_export_operador = casos_export_operador.sort_values("TOTAL", ascending=False).reset_index().rename(columns={"_usuario_prod_export": "Confeccionada Por"})
    else:
        casos_export_operador = pd.DataFrame(columns=["Confeccionada Por"] + casos + ["TOTAL"])

    detalle_export_odc = (
        export_prod_cerradas.groupby(["_usuario_prod_export", "_dia_prod_export", "_caso"]).size()
        .reset_index(name="OS Cerradas")
        .rename(columns={"_usuario_prod_export": "Confeccionada Por", "_dia_prod_export": "Fecha", "_caso": "Caso asociado"})
        .sort_values(["Fecha", "Confeccionada Por", "Caso asociado"])
        if not export_prod_cerradas.empty else
        pd.DataFrame(columns=["Confeccionada Por", "Fecha", "Caso asociado", "OS Cerradas"])
    )

    # ---------------------------------------------------------
    # Excel
    # ---------------------------------------------------------
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        tabla_export.to_excel(writer, sheet_name="Resumen", index=False)
        cruz_final_export.to_excel(writer, sheet_name="Antiguedad")

        if not pendientes_export.empty:
            det = pendientes_export.copy()
            export_cols = []
            if col["numero_os"]:
                export_cols.append(col["numero_os"])
            export_cols += [
                col["fecha_creacion"], col["estado"],
                col["sucursal"], col["caso"]
            ]
            if col["localidad"]:
                export_cols.append(col["localidad"])
            if col["tipo_os"]:
                export_cols.append(col["tipo_os"])
            export_cols = list(dict.fromkeys(export_cols))
            det[export_cols + ["antiguedad", "intervalo"]].to_excel(
                writer, sheet_name="Pendientes", index=False
            )

        if not realizados_export.empty:
            realizados_export.to_excel(writer, sheet_name="Realizados", index=False)

        if not base_export.empty:
            base_export.to_excel(writer, sheet_name="Datos período", index=False)

        prod_export_operador.to_excel(writer, sheet_name="Productividad operador", index=False)
        cierres_export_dia.to_excel(writer, sheet_name="Cierres por día", index=False)
        casos_export_operador.to_excel(writer, sheet_name="Casos por operador", index=False)
        detalle_export_odc.to_excel(writer, sheet_name="Operador día caso", index=False)

    st.download_button(
        "⬇️ Descargar análisis completo en Excel",
        data=buffer.getvalue(),
        file_name=(
            f"analisis_OS_{'_'.join(sucursal)}_"
            f"{export_desde.strftime('%Y%m%d')}_"
            f"{export_hasta.strftime('%Y%m%d')}.xlsx"
        ),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_excel_export"
    )

    st.caption(
        f"Exportación preparada para {export_desde.strftime('%d/%m/%Y')} "
        f"al {export_hasta.strftime('%d/%m/%Y')} | "
        f"Sucursal/es: {', '.join(sucursal)}"
    )

    st.markdown("---")
    st.subheader("📄 Informe ejecutivo en PDF")
    st.write(
        "Genera un informe PDF con el mismo período elegido arriba, "
        "manteniendo el estilo del informe ejecutivo."
    )

    try:
        pdf_bytes = generar_pdf_informe(export_desde, export_hasta)
        st.download_button(
            "📄 Descargar informe ejecutivo en PDF",
            data=pdf_bytes,
            file_name=(
                f"informe_OS_{'_'.join(sucursal)}_"
                f"{export_desde.strftime('%Y%m%d')}_"
                f"{export_hasta.strftime('%Y%m%d')}.pdf"
            ),
            mime="application/pdf",
            key="download_pdf_informe"
        )
    except Exception as e:
        st.error(f"No se pudo generar el PDF: {e}")

