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
pct_inactivos = 100 - pct_activos
nota_media = inscriptos["nota_final"].mean()
cond = inscriptos["condicion"].value_counts(normalize=True).mul(100)

st.markdown("**Actividad**")
a1, a2, a3 = st.columns(3)
a1.metric("Inscriptos", f"{n:,}")
a2.metric("% activos", f"{pct_activos:.1f}%")
a3.metric("% inactivos", f"{pct_inactivos:.1f}%")

st.markdown("**Rendimiento**")
r1, r2, r3, r4 = st.columns(4)
r1.metric("Nota media", f"{nota_media:.1f}")
r2.metric("% Libre", f"{cond.get('Libre', 0):.1f}%")
r3.metric("% Regular", f"{cond.get('Regular', 0):.1f}%")
r4.metric("% Promociona", f"{cond.get('Promociona', 0):.1f}%")

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

# Materias en columnas: caben nombres largos sin scroll horizontal
tabla_materias = (
    por_materia.set_index("materia")[
        [
            "inscriptos",
            "activos",
            "inactivos",
            "pct_activos",
            "nota_media",
            "sesiones_media",
            "tiempo_medio_min",
        ]
    ]
    .rename(
        columns={
            "inscriptos": "Inscriptos",
            "activos": "Activos",
            "inactivos": "Inactivos",
            "pct_activos": "Activos (%)",
            "nota_media": "Nota media",
            "sesiones_media": "Sesiones promedio",
            "tiempo_medio_min": "Tiempo promedio (min)",
        }
    )
    .T
)
st.dataframe(tabla_materias, use_container_width=True)

st.subheader("Activos vs inactivos por materia")
estado = por_materia.melt(
    id_vars="materia",
    value_vars=["activos", "inactivos"],
    var_name="estado",
    value_name="alumnos",
)
estado["estado"] = estado["estado"].map({"activos": "Activos", "inactivos": "Inactivos"})
fig_act = px.bar(
    estado,
    x="materia",
    y="alumnos",
    color="estado",
    barmode="stack",
    text="alumnos",
    category_orders={"estado": ["Activos", "Inactivos"]},
    color_discrete_map={"Activos": "#2ca02c", "Inactivos": "#d62728"},
    labels={"alumnos": "Alumnos", "materia": "Materia", "estado": "Estado"},
)
fig_act.update_traces(textposition="inside")
fig_act.update_layout(legend_title_text="")
st.plotly_chart(fig_act, use_container_width=True)

st.subheader("Distribución de notas")
TODAS_MATERIAS = "Todas las materias"
materias_disp = [TODAS_MATERIAS] + sorted(inscriptos["materia"].dropna().unique())
materia_dist = st.selectbox("Materia", options=materias_disp, key="materia_dist_notas")
if materia_dist == TODAS_MATERIAS:
    notas_mat = inscriptos.dropna(subset=["nota_final"])
else:
    notas_mat = inscriptos[inscriptos["materia"] == materia_dist].dropna(subset=["nota_final"])

if notas_mat.empty:
    st.info(
        "No hay notas para los filtros seleccionados."
        if materia_dist == TODAS_MATERIAS
        else "No hay notas para la materia seleccionada."
    )
else:
    n_mat = len(notas_mat)
    media_mat = notas_mat["nota_final"].mean()
    mediana_mat = notas_mat["nota_final"].median()
    n_aprob = int((notas_mat["condicion"] != "Libre").sum())
    n_desaprob = int((notas_mat["condicion"] == "Libre").sum())
    pct_aprob = 100 * n_aprob / n_mat
    pct_desaprob = 100 * n_desaprob / n_mat

    k1, k2 = st.columns(2)
    k1.metric("Nota media", f"{media_mat:.1f}")
    k2.metric("Mediana", f"{mediana_mat:.1f}")

    barra = pd.DataFrame(
        {
            "eje": ["Resultado"] * 2,
            "estado": ["Aprobados", "Desaprobados"],
            "pct": [pct_aprob, pct_desaprob],
            "etiqueta": [
                f"Aprobados {pct_aprob:.1f}%",
                f"Desaprobados {pct_desaprob:.1f}%",
            ],
        }
    )
    fig_barra = px.bar(
        barra,
        x="pct",
        y="eje",
        color="estado",
        orientation="h",
        text="etiqueta",
        barmode="stack",
        category_orders={"estado": ["Aprobados", "Desaprobados"]},
        color_discrete_map={"Aprobados": "#2ca02c", "Desaprobados": "#d62728"},
        labels={"pct": "", "eje": ""},
    )
    fig_barra.update_traces(textposition="inside", insidetextanchor="middle")
    fig_barra.update_layout(
        showlegend=False,
        height=90,
        margin=dict(t=0, b=0, l=0, r=0),
        xaxis=dict(range=[0, 100], visible=False),
        yaxis=dict(visible=False),
        bargap=0.05,
    )
    st.plotly_chart(fig_barra, use_container_width=True)

    max_nota = float(notas_mat["nota_final"].max())
    paso = 10
    bordes = list(range(0, int(max_nota) + paso + 1, paso))
    notas_bin = notas_mat.copy()
    notas_bin["rango"] = pd.cut(
        notas_bin["nota_final"],
        bins=bordes,
        right=False,
        include_lowest=True,
    )
    hist_v = (
        notas_bin.groupby("rango", observed=False, as_index=False)
        .size()
        .rename(columns={"size": "alumnos"})
    )
    hist_v["rango_label"] = hist_v["rango"].apply(
        lambda r: f"{int(r.left)}–{int(r.right) - 1}"
    )
    orden_rangos = [
        f"{int(r.left)}–{int(r.right) - 1}"
        for r in sorted(hist_v["rango"].dropna().unique(), key=lambda r: r.left)
    ]
    fig_hist = px.bar(
        hist_v,
        x="rango_label",
        y="alumnos",
        text="alumnos",
        category_orders={"rango_label": orden_rangos},
        labels={"alumnos": "Cantidad de estudiantes", "rango_label": "Nota"},
        color_discrete_sequence=["#4C78A8"],
        title=f"Distribución de notas · {materia_dist}",
    )
    fig_hist.update_traces(textposition="outside", cliponaxis=False)
    fig_hist.update_layout(margin=dict(t=50, b=40), height=360, showlegend=False)
    fig_hist.update_yaxes(rangemode="tozero")
    st.plotly_chart(fig_hist, use_container_width=True)

st.subheader("Condición académica por materia")
orden_cond = ["Libre", "Regular", "Promociona"]
cond_mat = (
    inscriptos.groupby(["materia", "condicion"], as_index=False)
    .size()
    .rename(columns={"size": "alumnos"})
)
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

st.subheader("Participación semana a semana")
materias_tend = [TODAS_MATERIAS] + sorted(inscriptos["materia"].dropna().unique())
materia_tend = st.selectbox("Materia", options=materias_tend, key="materia_tendencia")
if materia_tend == TODAS_MATERIAS:
    inscriptos_mat = inscriptos
else:
    inscriptos_mat = inscriptos[inscriptos["materia"] == materia_tend]
n_inscriptos = len(inscriptos_mat)

ses = sesiones(datos, fecha_corte)
ses_mat = ses.merge(
    inscriptos_mat[["usuario", "materia"]].drop_duplicates(),
    on=["usuario", "materia"],
    how="inner",
).copy()

if ses_mat.empty or n_inscriptos == 0:
    st.info(
        "No hay sesiones registradas hasta la fecha de corte."
        if materia_tend == TODAS_MATERIAS
        else "No hay sesiones registradas para la materia hasta la fecha de corte."
    )
else:
    _MESES = {
        1: "ene.",
        2: "feb.",
        3: "mar.",
        4: "abr.",
        5: "may.",
        6: "jun.",
        7: "jul.",
        8: "ago.",
        9: "sep.",
        10: "oct.",
        11: "nov.",
        12: "dic.",
    }

    def _etiqueta_semana(inicio: pd.Timestamp) -> str:
        fin = inicio + pd.Timedelta(days=6)
        if inicio.month == fin.month:
            return f"{inicio.day}–{fin.day} {_MESES[inicio.month]}"
        return f"{inicio.day} {_MESES[inicio.month]}–{fin.day} {_MESES[fin.month]}"

    ses_mat["semana"] = ses_mat["inicio"].dt.to_period("W-SUN").dt.start_time.dt.normalize()
    # Por inscripción (usuario–materia), coherente con n_inscriptos
    activos_sem = (
        ses_mat.drop_duplicates(subset=["semana", "usuario", "materia"])
        .groupby("semana")
        .size()
        .rename("participaron")
        .reset_index()
    )
    calendario = pd.DataFrame(
        {
            "semana": pd.period_range(
                ses_mat["inicio"].min(),
                fecha_corte,
                freq="W-SUN",
            )
            .to_timestamp()
            .normalize()
        }
    )
    semanal = calendario.merge(activos_sem, on="semana", how="left")
    semanal["participaron"] = semanal["participaron"].fillna(0).astype(int)
    semanal["no_participaron"] = (n_inscriptos - semanal["participaron"]).clip(lower=0)
    semanal["etiqueta"] = semanal["semana"].map(_etiqueta_semana)

    largo = semanal.melt(
        id_vars=["etiqueta", "semana"],
        value_vars=["participaron", "no_participaron"],
        var_name="estado",
        value_name="alumnos",
    )
    largo["estado"] = largo["estado"].map(
        {"participaron": "Participaron", "no_participaron": "Sin actividad"}
    )
    # Cronológico de izquierda a derecha
    orden_sem = semanal.sort_values("semana")["etiqueta"].tolist()
    fig_trend = px.bar(
        largo,
        x="etiqueta",
        y="alumnos",
        color="estado",
        text="alumnos",
        barmode="stack",
        category_orders={
            "etiqueta": orden_sem,
            "estado": ["Participaron", "Sin actividad"],
        },
        color_discrete_map={"Participaron": "#2ca02c", "Sin actividad": "#d62728"},
        labels={"alumnos": "Alumnos", "etiqueta": "Semana", "estado": ""},
    )
    fig_trend.update_traces(textposition="inside", insidetextanchor="middle")
    fig_trend.update_layout(
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=40, b=80),
        yaxis=dict(range=[0, n_inscriptos], title="Alumnos"),
        xaxis=dict(tickangle=-35, title="Semana"),
    )
    st.plotly_chart(fig_trend, use_container_width=True)
