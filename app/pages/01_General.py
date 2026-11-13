"""Dashboard General: resumen consolidado por asignatura."""

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
from src.kpis import resumen_alumnos, sesiones

st.title("Dashboard General")
st.caption("Indicadores consolidados de actividad y rendimiento por asignatura.")

datos = cargar_datos()
fecha_corte, materias = filtros_sidebar(datos, clave="general")

resumen = filtrar_materias(resumen_alumnos(datos, fecha_corte), materias)
inscriptos = resumen[resumen["inscripto"]].copy()

if inscriptos.empty:
    st.warning("No hay alumnos inscriptos para los filtros seleccionados.")
    st.stop()

n = len(inscriptos)
pct_activos = 100 * inscriptos["activo"].mean()
nota_media = inscriptos["nota_final"].mean()
cond = inscriptos["condicion"].value_counts(normalize=True).mul(100)

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Inscriptos", f"{n:,}")
c2.metric("% activos", f"{pct_activos:.1f}%")
c3.metric("Nota media", f"{nota_media:.1f}")
c4.metric("% Libre", f"{cond.get('Libre', 0):.1f}%")
c5.metric("% Regular", f"{cond.get('Regular', 0):.1f}%")
c6.metric("% Promociona", f"{cond.get('Promociona', 0):.1f}%")

st.subheader("Indicadores por materia")
por_materia = (
    inscriptos.groupby("materia", as_index=False)
    .agg(
        inscriptos=("usuario", "count"),
        activos=("activo", "sum"),
        nota_media=("nota_final", "mean"),
        sesiones_media=("sesiones", "mean"),
        tiempo_medio_min=("tiempo_min", "mean"),
    )
)
por_materia["inactivos"] = por_materia["inscriptos"] - por_materia["activos"]
por_materia["pct_activos"] = 100 * por_materia["activos"] / por_materia["inscriptos"]
por_materia = por_materia.round({"nota_media": 1, "sesiones_media": 1, "tiempo_medio_min": 1, "pct_activos": 1})

st.dataframe(
    por_materia[
        [
            "materia",
            "inscriptos",
            "activos",
            "inactivos",
            "pct_activos",
            "nota_media",
            "sesiones_media",
            "tiempo_medio_min",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Distribución de notas")
    fig_hist = px.histogram(
        inscriptos,
        x="nota_final",
        color="materia",
        nbins=20,
        barmode="overlay",
        opacity=0.65,
        labels={"nota_final": "Nota final", "count": "Alumnos"},
    )
    fig_hist.update_layout(legend_title_text="Materia")
    st.plotly_chart(fig_hist, use_container_width=True)

with col_b:
    st.subheader("Condición académica por materia")
    cond_mat = (
        inscriptos.groupby(["materia", "condicion"], as_index=False)
        .size()
        .rename(columns={"size": "alumnos"})
    )
    orden_cond = ["Libre", "Regular", "Promociona"]
    cond_mat["condicion"] = pd.Categorical(cond_mat["condicion"], categories=orden_cond, ordered=True)
    fig_cond = px.bar(
        cond_mat.sort_values(["materia", "condicion"]),
        x="materia",
        y="alumnos",
        color="condicion",
        barmode="group",
        category_orders={"condicion": orden_cond},
        color_discrete_map={"Libre": "#d62728", "Regular": "#ff7f0e", "Promociona": "#2ca02c"},
        labels={"alumnos": "Alumnos", "materia": "Materia", "condicion": "Condición"},
    )
    st.plotly_chart(fig_cond, use_container_width=True)

st.subheader("Tendencia de participación")
ses = filtrar_materias(sesiones(datos, fecha_corte), materias)
if ses.empty:
    st.info("No hay sesiones registradas hasta la fecha de corte.")
else:
    ses["dia"] = ses["inicio"].dt.normalize()
    tendencia = ses.groupby(["dia", "materia"], as_index=False).size().rename(columns={"size": "sesiones"})
    fig_trend = px.line(
        tendencia,
        x="dia",
        y="sesiones",
        color="materia",
        markers=True,
        labels={"dia": "Fecha", "sesiones": "Sesiones", "materia": "Materia"},
    )
    st.plotly_chart(fig_trend, use_container_width=True)
