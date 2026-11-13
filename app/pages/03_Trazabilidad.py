"""Trazabilidad: acciones, recursos, horarios y detalle de interacciones."""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import shorten

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "app"))

from helpers import cargar_datos
from src.kpis import alumnos, eventos_alumnos


DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep.", "oct.", "nov.", "dic."]


def _numero(valor, decimales=0):
    return f"{valor:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _eventos_filtrados(datos, desde, hasta, materias, solo_inscriptos=True):
    """Filtra una copia de los eventos usando las funciones compartidas existentes."""
    desde, hasta = pd.Timestamp(desde).normalize(), pd.Timestamp(hasta).normalize()
    if desde > hasta:
        raise ValueError("La fecha Desde debe ser anterior o igual a la fecha Hasta.")
    eventos = eventos_alumnos(datos, hasta)
    eventos = eventos.loc[eventos["fecha"].ge(desde) & eventos["materia"].isin(materias)].copy()
    identidad = alumnos(datos)[["materia", "usuario", "apellido", "nombre", "inscripto"]]
    eventos = eventos.merge(identidad, on=["materia", "usuario"], how="left", validate="many_to_one")
    eventos["inscripto"] = eventos["inscripto"].eq(True)
    if solo_inscriptos:
        eventos = eventos.loc[eventos["inscripto"]].copy()
    nombres = (eventos["apellido"].fillna("") + " " + eventos["nombre"].fillna("")).str.strip()
    eventos["estudiante"] = nombres.where(nombres.ne(""), eventos["usuario"])
    eventos["recurso_visible"] = eventos["recurso"].fillna("Sin recurso identificado").replace("", "Sin recurso identificado")
    return eventos


def _matriz_horaria(eventos):
    """Siete días y 24 horas, incluidos los intervalos sin interacciones."""
    dias = eventos["fecha"].dt.day_of_week.map(dict(enumerate(DIAS)))
    horas = eventos["fecha"].dt.hour
    return pd.crosstab(dias, horas).reindex(index=DIAS, columns=range(24), fill_value=0)


def _evolucion(eventos, desde, hasta, materias, frecuencia):
    """Conserva todos los períodos y materias, también cuando el conteo es cero."""
    periodos = pd.period_range(desde, hasta, freq=frecuencia)
    indice = pd.MultiIndex.from_product([materias, periodos], names=["materia", "periodo"])
    tabla = (
        eventos.assign(periodo=eventos["fecha"].dt.to_period(frecuencia))
        .groupby(["materia", "periodo"]).size().reindex(indice, fill_value=0)
        .rename("interacciones").reset_index()
    )
    tabla["inicio"] = tabla["periodo"].dt.start_time
    etiquetas = {}
    for periodo in periodos:
        inicio = max(periodo.start_time, desde)
        fin = min(periodo.end_time.normalize(), hasta)
        parcial = inicio != periodo.start_time or fin != periodo.end_time.normalize()
        if frecuencia == "M":
            etiqueta = f"{MESES[inicio.month - 1]} {inicio.year}"
        elif inicio.month == fin.month and inicio.year == fin.year:
            etiqueta = f"{inicio.day}–{fin.day} {MESES[fin.month - 1]}"
        else:
            etiqueta = f"{inicio.day} {MESES[inicio.month - 1]}–{fin.day} {MESES[fin.month - 1]}"
        etiquetas[periodo] = etiqueta + (" (parcial)" if parcial else "")
    tabla["etiqueta"] = tabla["periodo"].map(etiquetas)
    return tabla


st.set_page_config(page_title="Trazabilidad · Seguimiento Académico LMS", layout="wide")
st.title("Dashboard de Trazabilidad")
st.caption("Qué acciones realizaron los estudiantes, sobre qué contenidos y cuándo.")

datos = cargar_datos()
fechas = datos["trazabilidad"].loc[datos["trazabilidad"]["perfil"].eq("Alumnos"), "fecha"].dropna()
if fechas.empty:
    st.info("No hay interacciones de estudiantes para consultar.")
    st.stop()

primera_fecha = fechas.min().normalize()
ultimo_dia = fechas.max().normalize()
materias = sorted(datos["participacion"]["materia"].dropna().unique())
colores = {nombre: ["#4C78A8", "#F28E2B", "#59A14F"][i % 3] for i, nombre in enumerate(materias)}

st.sidebar.header("Filtros de trazabilidad")
seleccion = st.sidebar.selectbox(
    "Materia", ["Todas las materias", *materias], key="traz_materia"
)
materias_seleccionadas = materias if seleccion == "Todas las materias" else [seleccion]
poblacion = st.sidebar.selectbox(
    "Estudiantes", ["Solo inscriptos", "Todos los alumnos del LMS"], key="traz_poblacion"
)
desde = st.sidebar.date_input(
    "Desde", value=primera_fecha.date(), min_value=primera_fecha.date(),
    max_value=ultimo_dia.date(), format="DD/MM/YYYY", key="traz_desde",
)
hasta = st.sidebar.date_input(
    "Hasta", value=ultimo_dia.date(), min_value=primera_fecha.date(),
    max_value=ultimo_dia.date(), format="DD/MM/YYYY", key="traz_hasta",
)
desde, hasta = pd.Timestamp(desde), pd.Timestamp(hasta)
if desde > hasta:
    st.error("La fecha Desde debe ser anterior o igual a la fecha Hasta.")
    st.stop()

eventos = _eventos_filtrados(
    datos, desde, hasta, materias_seleccionadas,
    solo_inscriptos=poblacion == "Solo inscriptos",
)
st.subheader(seleccion)
st.caption(f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y} · {poblacion}")
c1, c2, c3 = st.columns(3)
c1.metric("Interacciones totales", _numero(len(eventos)))
c2.metric("Estudiantes con interacciones", _numero(eventos["usuario"].nunique()))
c3.metric(
    "Interacciones por día", _numero(len(eventos) / ((hasta - desde).days + 1), 1),
    help="Promedio de interacciones por día del período seleccionado, incluidos los días sin actividad.",
)
if eventos.empty:
    st.info("No hay interacciones para los filtros seleccionados.")
    st.stop()

st.subheader("Interacciones más frecuentes")
modo_col, cantidad_col = st.columns([3, 1])
modo = modo_col.radio(
    "Agrupar interacciones", ["Por acción", "Por recurso"], horizontal=True,
    key="traz_ranking_tipo",
    help="Por recurso muestra contenidos identificados. Las entradas a secciones como Inicio o Programa quedan en Por acción.",
)
limite = cantidad_col.selectbox("Elementos a mostrar", [5, 10, 15, 20], index=1, key="traz_top")
if modo == "Por acción":
    ranking = (
        eventos.groupby("accion", as_index=False)
        .agg(interacciones=("fecha", "size"), estudiantes=("usuario", "nunique"))
        .sort_values(["interacciones", "accion"], ascending=[False, True]).head(limite)
        .sort_values("interacciones").reset_index(drop=True)
    )
    ranking["detalle"] = ranking["accion"]
    etiquetas = ranking["accion"].map(lambda texto: shorten(texto, width=48, placeholder="…"))
    alto = max(320, len(ranking) * 30 + 90)
    nombre_eje = "Tipo de acción"
else:
    es_seccion = pd.Series(
        [recurso in seccion.split(" > ") for recurso, seccion in zip(
            eventos["recurso"].fillna(""), eventos["seccion"].fillna("")
        )], index=eventos.index,
    )
    recursos = eventos.loc[eventos["recurso"].notna() & eventos["recurso"].ne("") & ~es_seccion]
    ranking = (
        recursos.groupby(["materia", "recurso_visible"], as_index=False)
        .agg(interacciones=("fecha", "size"), estudiantes=("usuario", "nunique"))
        .sort_values(["interacciones", "materia", "recurso_visible"], ascending=[False, True, True])
        .head(limite).sort_values("interacciones").reset_index(drop=True)
    )
    ranking["detalle"] = ranking["recurso_visible"] + "<br>" + ranking["materia"]
    etiquetas = ranking["recurso_visible"].map(lambda texto: shorten(texto, width=44, placeholder="…"))
    if len(materias_seleccionadas) > 1:
        etiquetas = etiquetas + "<br>" + ranking["materia"]
    alto = max(360, len(ranking) * 44 + 90)
    nombre_eje = "Recurso"
if ranking.empty:
    st.info("No hay recursos identificados para los filtros seleccionados.")
else:
    ranking["posicion"] = range(len(ranking))
    ranking["cantidad_visible"] = ranking["interacciones"].map(_numero)
    fig_ranking = px.bar(
        ranking, x="interacciones", y="posicion", orientation="h", text="cantidad_visible",
        custom_data=["detalle", "estudiantes"], color_discrete_sequence=["#4C78A8"],
        labels={"interacciones": "Cantidad de interacciones", "posicion": nombre_eje},
    )
    fig_ranking.update_traces(
        textposition="outside", cliponaxis=False,
        hovertemplate="%{customdata[0]}<br>Interacciones: %{x}<br>Estudiantes: %{customdata[1]}<extra></extra>",
    )
    fig_ranking.update_yaxes(tickmode="array", tickvals=ranking["posicion"], ticktext=etiquetas)
    fig_ranking.update_xaxes(rangemode="tozero")
    fig_ranking.update_layout(height=alto, showlegend=False, margin=dict(t=15, b=45))
    st.plotly_chart(fig_ranking, width="stretch")

st.subheader("Días y horarios con más interacciones")
matriz = _matriz_horaria(eventos)
fig_horarios = px.imshow(
    matriz, aspect="auto", color_continuous_scale="Blues", zmin=0,
    labels={"x": "Hora", "y": "Día de la semana", "color": "Interacciones"},
)
fig_horarios.update_traces(
    customdata=[[f"{hora:02d}:00–{hora:02d}:59" for hora in range(24)] for _ in DIAS],
    hovertemplate="%{y}<br>%{customdata}<br>Interacciones: %{z}<extra></extra>",
)
fig_horarios.update_xaxes(
    tickmode="array", tickvals=list(range(0, 24, 2)),
    ticktext=[f"{hora:02d}:00" for hora in range(0, 24, 2)],
)
fig_horarios.update_layout(height=350, margin=dict(t=15, b=45))
st.plotly_chart(fig_horarios, width="stretch")

with st.expander("Ver evolución temporal"):
    agrupacion = st.radio(
        "Agrupar por", ["Semana", "Mes"], horizontal=True, key="traz_temporal"
    )
    frecuencia = "W-SUN" if agrupacion == "Semana" else "M"
    evolucion = _evolucion(eventos, desde, hasta, materias_seleccionadas, frecuencia)
    fig_temporal = px.line(
        evolucion, x="inicio", y="interacciones", color="materia", markers=True,
        custom_data=["etiqueta", "materia"], color_discrete_map=colores,
        category_orders={"materia": materias_seleccionadas},
        labels={"inicio": agrupacion, "interacciones": "Cantidad de interacciones", "materia": "Materia"},
    )
    fig_temporal.update_traces(
        hovertemplate="%{customdata[1]}<br>%{customdata[0]}<br>Interacciones: %{y}<extra></extra>"
    )
    periodos_visibles = evolucion.drop_duplicates("inicio")
    fig_temporal.update_xaxes(
        tickmode="array", tickvals=periodos_visibles["inicio"], ticktext=periodos_visibles["etiqueta"]
    )
    fig_temporal.update_yaxes(rangemode="tozero")
    fig_temporal.update_layout(
        height=360, showlegend=len(materias_seleccionadas) > 1,
        legend=dict(orientation="h", y=1.15, x=0, title_text=""), margin=dict(t=25, b=60),
    )
    st.plotly_chart(fig_temporal, width="stretch")

st.subheader("Detalle de interacciones")
busqueda_col, accion_col = st.columns([3, 2])
busqueda = busqueda_col.text_input(
    "Buscar en la tabla por estudiante, usuario o recurso", key="traz_busqueda"
)
accion = accion_col.selectbox(
    "Acción en la tabla", ["Todas las acciones", *sorted(eventos["accion"].dropna().unique())],
    key="traz_detalle_accion",
)
detalle = eventos
if accion != "Todas las acciones":
    detalle = detalle.loc[detalle["accion"].eq(accion)]
if busqueda.strip():
    coincide = pd.Series(False, index=detalle.index)
    for campo in ["usuario", "estudiante", "recurso_visible"]:
        coincide |= detalle[campo].astype("string").str.contains(busqueda.strip(), case=False, regex=False, na=False)
    detalle = detalle.loc[coincide]
detalle = detalle.sort_values(["fecha", "materia", "usuario"], ascending=[False, True, True])
columnas = ["fecha", "materia", "usuario", "estudiante", "accion", "seccion", "recurso_visible"]
if poblacion == "Todos los alumnos del LMS":
    columnas.append("inscripto")
mostrar = detalle[columnas].rename(columns={
    "fecha": "Fecha y hora", "materia": "Materia", "usuario": "Usuario",
    "estudiante": "Estudiante", "accion": "Acción", "seccion": "Sección",
    "recurso_visible": "Recurso", "inscripto": "Inscripto",
})
st.caption(f"Mostrando {_numero(len(mostrar))} de {_numero(len(eventos))} interacciones.")
st.dataframe(
    mostrar, width="stretch", height=440, hide_index=True,
    column_config={"Fecha y hora": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm:ss")},
)
