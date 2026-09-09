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

end = pd.Timestamp(fecha_hasta)
start = pd.Timestamp(fecha_desde)

if not sucursal:
    st.warning("Seleccioná al menos una sucursal.")
    st.stop()

base = df[
    (df["_sucursal"].isin(sucursal)) &
    (df["_fecha"].notna()) &
    (df["_fecha"] >= start) &
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
    # Selector de período PROPIO de Productividad
    # ---------------------------------------------------------
    st.markdown("### 📅 Período de productividad")

    tipo_periodo = st.radio(
        "Seleccionar período",
        ["Día", "Semana", "Mes", "Período personalizado"],
        horizontal=True,
        key="productividad_tipo_periodo"
    )

    prod_desde = None
    prod_hasta = None

    if tipo_periodo == "Día":
        fecha_elegida = st.date_input(
            "Elegir día",
            value=(fecha_hasta if min_prod_date <= fecha_hasta <= max_prod_date else max_prod_date),
            min_value=min_prod_date,
            max_value=max_prod_date,
            key="productividad_dia"
        )
        prod_desde = fecha_elegida
        prod_hasta = fecha_elegida

    elif tipo_periodo == "Semana":
        fecha_elegida = st.date_input(
            "Elegir cualquier día de la semana",
            value=(fecha_hasta if min_prod_date <= fecha_hasta <= max_prod_date else max_prod_date),
            min_value=min_prod_date,
            max_value=max_prod_date,
            key="productividad_semana"
        )
        prod_desde = fecha_elegida - timedelta(days=fecha_elegida.weekday())
        prod_hasta = prod_desde + timedelta(days=6)

        st.info(
            f"Semana seleccionada: **{prod_desde.strftime('%d/%m/%Y')}** "
            f"al **{prod_hasta.strftime('%d/%m/%Y')}**"
        )

    elif tipo_periodo == "Mes":
        fecha_elegida = st.date_input(
            "Elegir cualquier día del mes",
            value=(fecha_hasta if min_prod_date <= fecha_hasta <= max_prod_date else max_prod_date),
            min_value=min_prod_date,
            max_value=max_prod_date,
            key="productividad_mes"
        )
        prod_desde = fecha_elegida.replace(day=1)
        siguiente_mes = pd.Timestamp(prod_desde) + pd.offsets.MonthBegin(1)
        prod_hasta = (siguiente_mes - pd.Timedelta(days=1)).date()

        st.info(
            f"Mes seleccionado: **{fecha_elegida.strftime('%m/%Y')}** "
            f"({prod_desde.strftime('%d/%m/%Y')} al {prod_hasta.strftime('%d/%m/%Y')})"
        )

    else:
        pc1, pc2 = st.columns(2)

        with pc1:
            prod_desde = st.date_input(
                "Desde",
                value=(fecha_desde if min_prod_date <= fecha_desde <= max_prod_date else min_prod_date),
                min_value=min_prod_date,
                max_value=max_prod_date,
                key="productividad_desde"
            )

        with pc2:
            prod_hasta = st.date_input(
                "Hasta",
                value=(fecha_hasta if min_prod_date <= fecha_hasta <= max_prod_date else max_prod_date),
                min_value=min_prod_date,
                max_value=max_prod_date,
                key="productividad_hasta"
            )

        if prod_desde > prod_hasta:
            st.error("La fecha Desde no puede ser posterior a Hasta.")
            st.stop()

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

    if df_prod_cerradas.empty:
        st.info("No hay cierres para mostrar día por día.")
    else:
        df_prod_cerradas["_dia"] = (
            df_prod_cerradas["_fecha_productividad"].dt.normalize()
        )

        rango_dias = pd.date_range(
            fecha_inicio_prod,
            fecha_fin_exclusiva_prod - pd.Timedelta(days=1),
            freq="D"
        )

        diario = (
            df_prod_cerradas.groupby("_dia")
            .size()
            .reindex(rango_dias, fill_value=0)
            .rename("Órdenes Cerradas")
            .reset_index()
        )

        # Si el DatetimeIndex creado por reindex no tiene nombre,
        # pandas genera la primera columna como "index".
        # La convertimos siempre en "Fecha".
        if "Fecha" not in diario.columns:
            diario = diario.rename(columns={
                diario.columns[0]: "Fecha"
            })

        diario["Fecha"] = pd.to_datetime(
            diario["Fecha"],
            errors="coerce"
        )

        diario_mostrar = diario.copy()
        diario_mostrar["Fecha"] = diario_mostrar["Fecha"].dt.strftime(
            "%d/%m/%Y"
        )

        st.dataframe(
            diario_mostrar,
            use_container_width=True,
            hide_index=True
        )

        st.bar_chart(
            diario.set_index("Fecha")["Órdenes Cerradas"]
        )

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
# GENERADOR DE PDF - INFORME EJECUTIVO
# ============================================================
def generar_pdf_informe():
    """Genera un informe PDF dinámico con el mismo enfoque visual
    del informe de planificación: título, resumen ejecutivo,
    indicadores, tablas y gráficos simples."""
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
    periodo_txt = f"{fecha_desde.strftime('%d/%m/%Y')} al {fecha_hasta.strftime('%d/%m/%Y')}"
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

    # Productividad histórica del período seleccionado.
    prod_cierres = int(total_cerradas) if "total_cerradas" in globals() else 0
    prod_prom_dia = float(promedio_dia) if "promedio_dia" in globals() else 0

    capacidad_actual = None
    saldo_actual = None
    if "q" in globals() and "prod" in globals() and "nuevos" in globals():
        capacidad_actual = q * prod
        saldo_actual = capacidad_actual - nuevos

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
        f"<b>Productividad.</b> Para el período de productividad seleccionado se registraron "
        f"<b>{moneyless(prod_cierres)}</b> cierres, con un promedio de <b>{prod_prom_dia:.1f} cierres/día</b>. "
        f"La medición utiliza la fecha de calendario y el estado CERRADA."
    ))
    if capacidad_actual is not None:
        story.append(P(
            f"<b>Proyección.</b> Con {q} cuadrillas a {prod} trabajos por cuadrilla/día y "
            f"{nuevos:g} nuevas OS/día, la capacidad calculada es de <b>{moneyless(capacidad_actual)}</b> trabajos/día "
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
        f"Período de productividad: <b>{prod_desde.strftime('%d/%m/%Y')}</b> al "
        f"<b>{prod_hasta.strftime('%d/%m/%Y')}</b>. Sucursal/es: <b>{suc_txt}</b>. "
        f"Fecha utilizada: <b>{col_fecha_medicion}</b>."
    ))
    if "prod_data" in globals() and not prod_data.empty:
        rows_prod = [["Confeccionada Por", "Total Órdenes", "Órdenes Cerradas", "Efectividad Cierre (%)"]]
        for _, r in prod_data.iterrows():
            rows_prod.append([
                r.get("Confeccionada Por", ""),
                moneyless(r.get("Total Órdenes", 0)),
                moneyless(r.get("Órdenes Cerradas", 0)),
                f"{float(r.get('Efectividad Cierre (%)', 0)):.1f}",
            ])
        story.append(table_pdf(rows_prod, widths=[6.4*cm, 3.0*cm, 3.2*cm, 4.0*cm], font_size=7.4))
        try:
            top_prod = prod_data.head(12)
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
    if "matriz" in globals() and not matriz.empty:
        mat = matriz.copy()
        # Limitar la matriz a un máximo razonable para el PDF; la app conserva todos los datos.
        cols = list(mat.columns)
        if len(cols) > 15:
            cols = [cols[0]] + cols[1:15] + (["TOTAL"] if "TOTAL" in cols else [])
            mat = mat[cols]
        story.append(table_pdf([list(mat.columns)] + mat.astype(str).values.tolist(), font_size=6.2))
    else:
        story.append(P("No hay cierres para mostrar."))

    story += [PageBreak(), P("6. Casos de trabajo cerrados por operador", "SeccionInforme")]
    if "casos_operador" in globals() and not casos_operador.empty:
        rows_casos = [list(casos_operador.columns)] + casos_operador.astype(str).values.tolist()
        story.append(table_pdf(rows_casos, font_size=6.8))
    else:
        story.append(P("No hay casos de trabajo cerrados para el período seleccionado."))

    story += [Spacer(1, 10), P("7. Productividad día por día", "SeccionInforme")]
    if "diario" in globals() and not diario.empty:
        diario_pdf = diario.copy()
        diario_pdf["Fecha"] = pd.to_datetime(diario_pdf["Fecha"], errors="coerce").dt.strftime("%d/%m/%Y")
        story.append(table_pdf([list(diario_pdf.columns)] + diario_pdf.astype(str).values.tolist(), widths=[5*cm, 3.5*cm], font_size=7.2))
    else:
        story.append(P("No hay cierres para mostrar día por día."))

    story += [PageBreak(), P("8. Proyección operativa", "SeccionInforme")]
    story.append(P(
        f"La proyección parte de <b>{moneyless(total_pendientes)}</b> OS pendientes al final del período. "
        f"Los parámetros utilizados en la pestaña de proyección son editables desde la aplicación."
    ))
    if "proj" in globals() and isinstance(proj, pd.DataFrame) and not proj.empty:
        filas = [["Día", "Fecha", "Backlog inicio", "Trabajos realizados", "Nuevas OS", "Backlog final"]]
        # Mostrar una muestra representativa si son demasiadas filas.
        proj_pdf = proj.copy()
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
        fin = proj.iloc[-1]
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

    story += [Spacer(1, 12), P("9. Observaciones", "SeccionInforme")]
    story.append(P(
        "Este documento es una fotografía de los datos disponibles en la aplicación y respeta los filtros "
        "seleccionados al momento de exportar. La productividad se calcula sobre órdenes CERRADA según la "
        "fecha de calendario. La categoría <b>OS POR REPARACIONES/INTERNAS</b> se identifica desde la columna "
        "<b>Tipo de OS</b> cuando contiene <b>OS POR REPARACIONES/INSTALACIONES INTERNAS</b>."
    ))
    story.append(P(
        "La proyección es un escenario matemático y no incorpora automáticamente feriados, ausencias, zonas, "
        "tiempos de viaje o diferencias de productividad entre cuadrillas.",
    ))

    doc.build(story, onFirstPage=pie_pagina, onLaterPages=pie_pagina)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


# ============================================================
# TAB 7 - EXPORTAR
# ============================================================

with tabs[6]:
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
        file_name=f"analisis_OS_{'_'.join(sucursal)}_{fecha_hasta.strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("---")
    st.subheader("📄 Informe ejecutivo en PDF")
    st.write(
        "Genera un informe PDF con el período y filtros actuales, siguiendo el estilo del "
        "informe de planificación compartido: resumen ejecutivo, indicadores, tablas, "
        "productividad, cierres por operador y proyección."
    )

    try:
        pdf_bytes = generar_pdf_informe()
        st.download_button(
            "📄 Descargar informe ejecutivo en PDF",
            data=pdf_bytes,
            file_name=(
                f"informe_OS_{'_'.join(sucursal)}_"
                f"{fecha_desde.strftime('%Y%m%d')}_"
                f"{fecha_hasta.strftime('%Y%m%d')}.pdf"
            ),
            mime="application/pdf",
            key="download_pdf_informe"
        )
    except Exception as e:
        st.error(f"No se pudo generar el PDF: {e}")

