"""Dashboard de Participación: actividad, evolución y niveles."""

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
from src.kpis import eventos_alumnos, resumen_alumnos, sesiones

st.title("Dashboard de Participación")
st.caption("Actividad en la plataforma por fecha, asignatura y estudiante.")

datos = cargar_datos()
fecha_corte, materias = filtros_sidebar(datos, clave="participacion")

resumen = filtrar_materias(resumen_alumnos(datos, fecha_corte), materias)
inscriptos = resumen[resumen["inscripto"]].copy()
ses = filtrar_materias(sesiones(datos, fecha_corte), materias)
eventos = filtrar_materias(eventos_alumnos(datos, fecha_corte), materias)

if inscriptos.empty:
    st.warning("No hay alumnos inscriptos para los filtros seleccionados.")
    st.stop()

busqueda = st.sidebar.text_input("Buscar usuario", key="buscar_usuario_participacion")
top_n = st.sidebar.slider("Top alumnos (por tiempo)", min_value=10, max_value=100, value=25, step=5)

vista = inscriptos
if busqueda.strip():
    q = busqueda.strip().upper()
    vista = vista[
        vista["usuario"].str.upper().str.contains(q, na=False)
        | vista["apellido"].fillna("").str.upper().str.contains(q, na=False)
        | vista["nombre"].fillna("").str.upper().str.contains(q, na=False)
    ]

st.subheader("Evolución de accesos")
if ses.empty:
    st.info("No hay sesiones registradas hasta la fecha de corte.")
else:
    ses = ses.copy()
    ses["dia"] = ses["inicio"].dt.normalize()
    evol_ses = ses.groupby(["dia", "materia"], as_index=False).size().rename(columns={"size": "sesiones"})
    fig_ses = px.line(
        evol_ses,
        x="dia",
        y="sesiones",
        color="materia",
        markers=True,
        labels={"dia": "Fecha", "sesiones": "Sesiones", "materia": "Materia"},
    )
    st.plotly_chart(fig_ses, use_container_width=True)

    if not eventos.empty:
        ev = eventos.copy()
        ev["dia"] = ev["fecha"].dt.normalize()
        evol_ev = ev.groupby(["dia", "materia"], as_index=False).size().rename(columns={"size": "eventos"})
        with st.expander("Ver también evolución de eventos (clics / acciones)"):
            fig_ev = px.line(
                evol_ev,
                x="dia",
                y="eventos",
                color="materia",
                markers=True,
                labels={"dia": "Fecha", "eventos": "Eventos", "materia": "Materia"},
            )
            st.plotly_chart(fig_ev, use_container_width=True)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Nivel de participación por materia")
    niveles = (
        inscriptos.dropna(subset=["nivel_participacion"])
        .groupby(["materia", "nivel_participacion"], as_index=False)
        .size()
        .rename(columns={"size": "alumnos"})
    )
    orden_nivel = ["Baja", "Media", "Alta"]
    niveles["nivel_participacion"] = pd.Categorical(
        niveles["nivel_participacion"], categories=orden_nivel, ordered=True
    )
    fig_niv = px.bar(
        niveles.sort_values(["materia", "nivel_participacion"]),
        x="materia",
        y="alumnos",
        color="nivel_participacion",
        barmode="stack",
        category_orders={"nivel_participacion": orden_nivel},
        color_discrete_map={"Baja": "#d62728", "Media": "#ff7f0e", "Alta": "#2ca02c"},
        labels={
            "alumnos": "Alumnos",
            "materia": "Materia",
            "nivel_participacion": "Nivel",
        },
    )
    st.plotly_chart(fig_niv, use_container_width=True)

with col2:
    st.subheader("Duración media de sesión")
    if ses.empty:
        st.info("Sin datos de sesiones.")
    else:
        dur_mat = ses.groupby("materia", as_index=False)["duracion_min"].mean()
        dur_mat = dur_mat.rename(columns={"duracion_min": "duracion_media_min"})
        fig_dur = px.bar(
            dur_mat,
            x="materia",
            y="duracion_media_min",
            labels={"materia": "Materia", "duracion_media_min": "Minutos"},
            text_auto=".1f",
        )
        st.plotly_chart(fig_dur, use_container_width=True)

        ses_dia = ses.copy()
        ses_dia["dia"] = ses_dia["inicio"].dt.normalize()
        dur_dia = ses_dia.groupby("dia", as_index=False)["duracion_min"].mean()
        fig_dur_dia = px.line(
            dur_dia,
            x="dia",
            y="duracion_min",
            markers=True,
            labels={"dia": "Fecha", "duracion_min": "Duración media (min)"},
        )
        st.plotly_chart(fig_dur_dia, use_container_width=True)

st.subheader("Actividad por alumno")
ranking = vista.sort_values("tiempo_min", ascending=False).head(top_n)
mostrar = ranking[
    [
        "materia",
        "usuario",
        "apellido",
        "nombre",
        "sesiones",
        "tiempo_min",
        "nivel_participacion",
        "dias_sin_acceso",
        "activo",
    ]
].copy()
mostrar["tiempo_min"] = mostrar["tiempo_min"].round(1)
st.dataframe(mostrar, use_container_width=True, hide_index=True)
