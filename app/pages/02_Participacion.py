"""Participación: accesos, días con actividad y detalle del período elegido."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "app"))

from helpers import cargar_datos, filtrar_materias
from src.kpis import MINUTOS_SESION, alumnos, dia_de_corte, eventos_alumnos, sesiones


MESES = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep.", "oct.", "nov.", "dic."]


def _participacion_periodo(datos, fecha_desde, fecha_corte=None):
    """Prepara esta vista reutilizando los KPIs compartidos sin modificarlos.

    El padrón disponible es la base fija, incluidos los inscriptos sin actividad.
    Solo la copia local de trazabilidad se limita al período antes de calcular
    sesiones, para excluir tiempo anterior al inicio sin cambiar su definición.
    """
    desde = pd.Timestamp(fecha_desde).normalize()
    corte = dia_de_corte(datos, fecha_corte)
    if desde > corte:
        raise ValueError("La fecha de inicio no puede ser posterior a la fecha de corte.")

    claves = ["materia", "usuario"]
    inscriptos = alumnos(datos).query("inscripto").copy()
    eventos = eventos_alumnos(datos, corte)
    eventos = eventos.loc[eventos["fecha"] >= desde].merge(
        inscriptos[claves], on=claves, how="inner", validate="many_to_one"
    )
    datos_periodo = {**datos, "trazabilidad": eventos}
    por_sesion = sesiones(datos_periodo, corte)

    actividad = (
        eventos.assign(dia=eventos["fecha"].dt.normalize())
        .groupby(claves)
        .agg(
            eventos=("fecha", "size"),
            dias_con_actividad=("dia", "nunique"),
            ultima_actividad=("fecha", "max"),
        )
        .reset_index()
    )
    uso = (
        por_sesion.groupby(claves)
        .agg(sesiones=("inicio", "size"), tiempo_min=("duracion_min", "sum"))
        .reset_index()
    )
    resumen = inscriptos.merge(actividad, on=claves, how="left", validate="one_to_one")
    resumen = resumen.merge(uso, on=claves, how="left", validate="one_to_one")
    enteros = ["eventos", "dias_con_actividad", "sesiones"]
    resumen[enteros] = resumen[enteros].fillna(0).astype(int)
    resumen["tiempo_min"] = resumen["tiempo_min"].fillna(0)
    resumen["con_actividad"] = resumen["eventos"].gt(0)
    return {"alumnos": resumen, "sesiones": por_sesion}


def numero(valor, decimales=0):
    return f"{valor:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def fecha_corta(fecha):
    return f"{fecha.day} {MESES[fecha.month - 1]}"


def etiqueta_semana(inicio, fin):
    if inicio == fin:
        return f"{inicio.day}<br>{MESES[inicio.month - 1]}"
    if inicio.month == fin.month and inicio.year == fin.year:
        return f"{inicio.day}–{fin.day}<br>{MESES[fin.month - 1]}"
    return f"{fecha_corta(inicio)}<br>–{fecha_corta(fin)}"


st.set_page_config(page_title="Participación · Seguimiento Académico LMS", layout="wide")
st.title("Dashboard de Participación")
st.caption("Accesos y frecuencia de participación de los estudiantes inscriptos.")

datos = cargar_datos()
fechas = datos["trazabilidad"].loc[
    datos["trazabilidad"]["perfil"].eq("Alumnos"), "fecha"
].dropna()
if fechas.empty:
    st.info("No hay actividad de estudiantes para consultar.")
    st.stop()

primera_fecha = fechas.min().normalize()
ultima_fecha = fechas.max()
ultimo_dia = ultima_fecha.normalize()
materias = sorted(datos["participacion"]["materia"].dropna().unique())
colores = {
    nombre: ["#4C78A8", "#F28E2B", "#59A14F"][i % 3]
    for i, nombre in enumerate(materias)
}

st.sidebar.header("Filtros de participación")
seleccion = st.sidebar.selectbox(
    "Materia", ["Todas las materias", *materias],
    key="vista_materia_participacion",
)
materias_seleccionadas = materias if seleccion == "Todas las materias" else [seleccion]
vista_conjunta = len(materias_seleccionadas) > 1
desde = st.sidebar.date_input(
    "Desde", value=primera_fecha.date(), min_value=primera_fecha.date(),
    max_value=ultimo_dia.date(), format="DD/MM/YYYY", key="desde_participacion",
)
hasta = st.sidebar.date_input(
    "Hasta", value=ultimo_dia.date(), min_value=primera_fecha.date(),
    max_value=ultimo_dia.date(), format="DD/MM/YYYY", key="hasta_participacion",
)
desde, hasta = pd.Timestamp(desde), pd.Timestamp(hasta)
if desde > hasta:
    st.error("La fecha Desde debe ser anterior o igual a la fecha Hasta.")
    st.stop()

periodo = _participacion_periodo(datos, desde, hasta)
inscriptos = filtrar_materias(periodo["alumnos"], materias_seleccionadas)
ses = filtrar_materias(periodo["sesiones"], materias_seleccionadas)
if inscriptos.empty:
    st.warning("No hay estudiantes inscriptos para la materia seleccionada.")
    st.stop()

por_estudiante = inscriptos.groupby("usuario").agg(
    con_actividad=("con_actividad", "any"),
    sesiones=("sesiones", "sum"),
    tiempo_min=("tiempo_min", "sum"),
)
n = len(por_estudiante)
dias_periodo = (hasta - desde).days + 1
con_actividad = int(por_estudiante["con_actividad"].sum())
st.subheader(seleccion)
st.caption(
    f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y} · {numero(n)} estudiantes inscriptos"
    + (f" en {len(materias_seleccionadas)} materias." if vista_conjunta else " en el padrón de referencia.")
)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Con actividad", numero(con_actividad), help="Estudiantes con al menos una acción en alguna de las materias seleccionadas durante el período.")
k2.metric("Sin actividad", numero(n - con_actividad), help="Inscriptos sin acciones registradas durante el período elegido.")
k3.metric("Sesiones por inscripto", numero(por_estudiante["sesiones"].mean(), 1))
k4.metric(
    "Tiempo medio estimado", f"{numero(por_estudiante['tiempo_min'].mean(), 1)} min",
    help="Promedio de minutos estimados por inscripto, incluyendo a quienes no registraron actividad.",
)
st.subheader("Evolución de accesos")
agrupacion = st.radio(
    "Ver sesiones por", ["Semana", "Día"], horizontal=True,
    key="agrupacion_participacion",
)
calendario = pd.date_range(desde, hasta, freq="D")
evoluciones = []
for nombre in materias_seleccionadas:
    sesiones_materia = ses[ses["materia"].eq(nombre)]
    sesiones_diarias = (
        sesiones_materia.groupby(sesiones_materia["inicio"].dt.normalize()).size()
        .reindex(calendario, fill_value=0).rename("sesiones")
    )
    if agrupacion == "Semana":
        semanales = sesiones_diarias.groupby(sesiones_diarias.index.to_period("W-SUN")).sum()
        filas = []
        for semana, cantidad in semanales.items():
            inicio = max(semana.start_time, desde)
            fin = min(semana.end_time.normalize(), hasta)
            parcial = inicio != semana.start_time or fin != semana.end_time.normalize() or fin == ultimo_dia
            etiqueta = etiqueta_semana(inicio, fin)
            filas.append({
                "periodo": etiqueta + ("<br>(parcial)" if parcial else ""),
                "detalle": f"{inicio:%d/%m/%Y} al {fin:%d/%m/%Y}" + (" · período parcial" if parcial else ""),
                "sesiones": int(cantidad),
            })
        evolucion_materia = pd.DataFrame(filas)
    else:
        evolucion_materia = sesiones_diarias.rename_axis("fecha").reset_index()
        evolucion_materia["periodo"] = evolucion_materia["fecha"].map(fecha_corta)
        evolucion_materia["detalle"] = evolucion_materia["fecha"].dt.strftime("%d/%m/%Y")
        ultimo = evolucion_materia["fecha"].eq(ultimo_dia)
        evolucion_materia.loc[ultimo, "periodo"] += "<br>(parcial)"
        evolucion_materia.loc[ultimo, "detalle"] += " · día parcial"
    evoluciones.append(evolucion_materia.assign(materia=nombre))
evolucion = pd.concat(evoluciones, ignore_index=True)
eje_temporal = "Semana" if agrupacion == "Semana" else "Día"

fig_accesos = px.bar(
    evolucion, x="periodo", y="sesiones", color="materia", barmode="group",
    text="sesiones" if evolucion["periodo"].nunique() <= 31 else None,
    custom_data=["detalle", "materia"], color_discrete_map=colores,
    category_orders={"materia": materias_seleccionadas},
    labels={"periodo": eje_temporal, "sesiones": "Cantidad de sesiones", "materia": "Materia"},
)
fig_accesos.update_traces(
    textposition="outside", cliponaxis=False,
    hovertemplate="%{customdata[1]}<br>%{customdata[0]}<br>Sesiones: %{y}<extra></extra>",
)
fig_accesos.update_layout(
    height=400 if vista_conjunta else 350, showlegend=vista_conjunta,
    margin=dict(t=30, b=80), legend=dict(orientation="h", y=1.15, x=0, title_text=""),
)
fig_accesos.update_xaxes(tickangle=0, nticks=14)
fig_accesos.update_yaxes(rangemode="tozero")
st.plotly_chart(fig_accesos, width="stretch")
st.caption(
    f"Una sesión agrupa acciones separadas por pausas de hasta {MINUTOS_SESION} minutos. "
    "Los días sin sesiones se muestran con valor cero."
)
st.subheader("Cuántos días participaron los estudiantes")
bordes = sorted(set([-1, 0, 1] + [min(b, dias_periodo) for b in [3, 7, 14, 30, 60, 90, 180]] + [dias_periodo]))
etiquetas = []
for inferior, superior in zip(bordes, bordes[1:]):
    primero = inferior + 1
    etiquetas.append(
        "0 días" if superior == 0 else
        "1 día" if primero == superior == 1 else
        f"{primero} días" if primero == superior else f"{primero}–{superior} días"
    )
frecuencias = []
for nombre in materias_seleccionadas:
    rangos = pd.cut(
        inscriptos.loc[inscriptos["materia"].eq(nombre), "dias_con_actividad"],
        bins=bordes, labels=etiquetas,
    )
    frecuencia_materia = rangos.value_counts(sort=False).rename_axis("dias").reset_index(name="estudiantes")
    frecuencias.append(frecuencia_materia.assign(materia=nombre))
frecuencia = pd.concat(frecuencias, ignore_index=True)
fig_frecuencia = px.bar(
    frecuencia, x="dias", y="estudiantes", text="estudiantes", color="materia", barmode="group",
    category_orders={"dias": etiquetas, "materia": materias_seleccionadas}, color_discrete_map=colores,
    custom_data=["materia"],
    labels={"dias": "Días con actividad dentro del período", "estudiantes": "Cantidad de estudiantes", "materia": "Materia"},
)
fig_frecuencia.update_traces(
    textposition="outside", cliponaxis=False,
    hovertemplate="%{customdata[0]}<br>%{x}<br>Estudiantes: %{y}<extra></extra>",
)
fig_frecuencia.update_layout(
    height=380 if vista_conjunta else 330, showlegend=vista_conjunta,
    margin=dict(t=30, b=45), legend=dict(orientation="h", y=1.15, x=0, title_text=""),
)
fig_frecuencia.update_yaxes(rangemode="tozero")
st.plotly_chart(fig_frecuencia, width="stretch")
st.caption(
    "Cada estudiante aparece en una sola barra por materia. Un día cuenta una vez, aunque haya ingresado varias veces. "
    "La barra de 0 días incluye a quienes no tuvieron actividad en el período."
)

st.subheader("Detalle por estudiante")
busqueda = st.text_input(
    "Buscar en la tabla por usuario, apellido o nombre", key="buscar_usuario_participacion"
)
vista = inscriptos.copy()
if busqueda.strip():
    coincide = pd.Series(False, index=vista.index)
    for columna in ["usuario", "apellido", "nombre"]:
        coincide |= vista[columna].astype("string").str.contains(busqueda.strip(), case=False, regex=False, na=False)
    vista = vista[coincide]
vista = vista.sort_values(["dias_con_actividad", "sesiones", "apellido", "nombre"], ascending=[False, False, True, True])
columnas = (["materia"] if vista_conjunta else []) + [
    "usuario", "apellido", "nombre", "dias_con_actividad", "sesiones", "tiempo_min", "ultima_actividad"
]
mostrar = vista[columnas].rename(columns={
    "materia": "Materia",
    "usuario": "Usuario", "apellido": "Apellido", "nombre": "Nombre",
    "dias_con_actividad": "Días con actividad", "sesiones": "Sesiones",
    "tiempo_min": "Tiempo estimado (min)", "ultima_actividad": "Última actividad del período",
})
st.caption(
    f"Mostrando {numero(len(mostrar))} de {numero(len(inscriptos))} "
    + ("inscripciones (una fila por estudiante y materia). " if vista_conjunta else "inscriptos. ")
    + "La búsqueda solo filtra esta tabla."
)
st.dataframe(
    mostrar, width="stretch", hide_index=True,
    column_config={
        "Tiempo estimado (min)": st.column_config.NumberColumn(format="%.1f"),
        "Última actividad del período": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
    },
)
st.caption(
    "El tiempo estimado suma los intervalos entre la primera y la última acción de cada sesión, "
    "usando solo eventos del período. Una sesión de una sola acción aporta 0 minutos; no equivale a tiempo de estudio. "
    "La base es el padrón disponible, sin reconstruir cambios históricos de matrícula."
)
