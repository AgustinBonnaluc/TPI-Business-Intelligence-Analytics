"""Dashboard de Trazabilidad: interacciones detalladas y patrones temporales."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "app"))

from helpers import cargar_datos, filtrar_materias, filtros_sidebar
from src.kpis import eventos_alumnos

st.title("Dashboard de Trazabilidad")
st.caption("Interacciones en el aula: acciones, mapa de calor y línea temporal.")

datos = cargar_datos()
fecha_corte, materias = filtros_sidebar(datos, clave="trazabilidad")

eventos = filtrar_materias(eventos_alumnos(datos, fecha_corte), materias)

if eventos.empty:
    st.warning("No hay eventos de alumnos para los filtros seleccionados.")
    st.stop()

top_acciones = st.sidebar.slider(
    "Top acciones a mostrar",
    min_value=5,
    max_value=20,
    value=12,
    step=1,
    key="top_acciones_traz",
)

st.subheader("Interacciones por tipo de acción")
por_accion = (
    eventos.groupby("accion", as_index=False)
    .size()
    .rename(columns={"size": "eventos"})
    .sort_values("eventos", ascending=False)
    .head(top_acciones)
)
fig_acc = px.bar(
    por_accion.sort_values("eventos"),
    x="eventos",
    y="accion",
    orientation="h",
    labels={"eventos": "Eventos", "accion": "Acción"},
)
st.plotly_chart(fig_acc, use_container_width=True)

st.subheader("Mapa de calor de actividad")
ev = eventos.copy()
dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
ev["dia_semana"] = ev["fecha"].dt.day_of_week.map(dict(enumerate(dias)))
ev["hora"] = ev["fecha"].dt.hour
heatmap = (
    ev.groupby(["dia_semana", "hora"], as_index=False)
    .size()
    .rename(columns={"size": "eventos"})
)
heatmap["dia_semana"] = pd.Categorical(heatmap["dia_semana"], categories=dias, ordered=True)
matriz = heatmap.pivot(index="dia_semana", columns="hora", values="eventos").fillna(0)
# Asegurar columnas 0-23 aunque falten horas
matriz = matriz.reindex(columns=range(24), fill_value=0)
fig_hm = px.imshow(
    matriz,
    labels={"x": "Hora", "y": "Día", "color": "Eventos"},
    aspect="auto",
    color_continuous_scale="Blues",
)
fig_hm.update_layout(xaxis=dict(dtick=1))
st.plotly_chart(fig_hm, use_container_width=True)

st.subheader("Línea temporal de actividad")
ev["dia"] = ev["fecha"].dt.normalize()
linea = ev.groupby(["dia", "materia"], as_index=False).size().rename(columns={"size": "eventos"})
fig_line = px.line(
    linea,
    x="dia",
    y="eventos",
    color="materia",
    markers=True,
    labels={"dia": "Fecha", "eventos": "Eventos", "materia": "Materia"},
)
st.plotly_chart(fig_line, use_container_width=True)

st.subheader("Resumen por materia")
resumen_mat = (
    ev.groupby("materia")
    .agg(eventos_totales=("fecha", "size"), alumnos_activos=("usuario", "nunique"))
    .reset_index()
)
resumen_mat["eventos_por_alumno"] = (
    resumen_mat["eventos_totales"] / resumen_mat["alumnos_activos"]
).round(1)

top_por_mat = (
    ev.groupby(["materia", "accion"])
    .size()
    .rename("n")
    .reset_index()
    .sort_values(["materia", "n"], ascending=[True, False])
    .groupby("materia", as_index=False)
    .first()
    .rename(columns={"accion": "accion_top", "n": "eventos_accion_top"})
)
resumen_mat = resumen_mat.merge(top_por_mat, on="materia", how="left")
st.dataframe(
    resumen_mat[
        [
            "materia",
            "eventos_totales",
            "alumnos_activos",
            "eventos_por_alumno",
            "accion_top",
            "eventos_accion_top",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)
