import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.kpis import DIAS_ALERTA_ROJA, DIAS_INACTIVO, cargar_datos, dia_de_corte, resumen_alumnos

TRAMOS = ["Activo (hasta 7 días)", "8 a 14 días", "Más de 14 días", "Nunca entró"]

GRUPOS = {
    (True, True): "Inscripto activo",
    (True, False): "Inscripto sin actividad",
    (False, True): "No inscripto con actividad",
    (False, False): "No inscripto sin actividad",
}
COLORES_GRUPOS = {
    "Inscripto activo": "#2E9E5B",
    "Inscripto sin actividad": "#E0A800",
    "No inscripto con actividad": "#D64545",
    "No inscripto sin actividad": "#B0B7C3",
}


@st.cache_data
def leer_datos():
    return cargar_datos()


@st.cache_data
def calcular_resumen(fecha_corte):
    return resumen_alumnos(leer_datos(), fecha_corte)


def tramo_sin_acceso(dias):
    if pd.isna(dias):
        return "Nunca entró"
    if dias <= DIAS_INACTIVO:
        return "Activo (hasta 7 días)"
    if dias <= DIAS_ALERTA_ROJA:
        return "8 a 14 días"
    return "Más de 14 días"


def estado_en_padron(estado):
    if estado == "Aceptada":
        return "Inscripto"
    if estado == "Baja":
        return "Dado de baja"
    return "No figura en el padrón"


st.title("Matrícula y Alertas")
st.write(
    "Compara el padrón oficial de cada materia con quienes realmente cursan en el aula virtual. "
    f"Se considera activo a quien entró en los últimos {DIAS_INACTIVO} días antes de la fecha de corte."
)

# Filtros
datos = leer_datos()
primer_dia = datos["trazabilidad"]["fecha"].min().date()
ultimo_dia = dia_de_corte(datos).date()

st.sidebar.header("Filtros")
fecha_corte = st.sidebar.date_input(
    "Fecha de corte", value=ultimo_dia, min_value=primer_dia, max_value=ultimo_dia
)
fecha_corte = pd.Timestamp(fecha_corte)

resumen = calcular_resumen(fecha_corte)
todas_las_materias = sorted(resumen["materia"].unique())
materias = st.sidebar.multiselect("Materias", todas_las_materias, default=todas_las_materias)
if not materias:
    materias = todas_las_materias

resumen = resumen[resumen["materia"].isin(materias)].copy()
resumen["grupo"] = [GRUPOS[(inscripto, activo)] for inscripto, activo in zip(resumen["inscripto"], resumen["activo"])]
resumen["tramo"] = resumen["dias_sin_acceso"].apply(tramo_sin_acceso)

padron = datos["matricula"]
padron = padron[padron["materia"].isin(materias)]

# Indicadores
inscriptos = resumen[resumen["inscripto"]]
no_inscriptos_activos = resumen[~resumen["inscripto"] & resumen["activo"]]
inscriptos_sin_actividad = inscriptos[~inscriptos["activo"]]

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Matriculados", len(inscriptos), help="Inscriptos en el padrón oficial (matrícula aceptada).")
col2.metric("Cursantes activos", int(resumen["activo"].sum()), help=f"Inscriptos o no, entraron en los últimos {DIAS_INACTIVO} días.")
col3.metric("No inscriptos activos", len(no_inscriptos_activos))
col4.metric("Inscriptos inactivos", len(inscriptos_sin_actividad))
col5.metric("Bajas", int((padron["estado"] == "Baja").sum()), help="Matrículas dadas de baja en el padrón.")

# Padrón vs. aula virtual
st.header("Padrón oficial vs. cursantes reales")
por_materia = resumen.groupby(["materia", "grupo"]).size().rename("Estudiantes").reset_index()
grafico = px.bar(
    por_materia,
    x="materia",
    y="Estudiantes",
    color="grupo",
    color_discrete_map=COLORES_GRUPOS,
    category_orders={"grupo": list(COLORES_GRUPOS)},
    text_auto=True,
    labels={"materia": "Materia", "grupo": ""},
)
st.plotly_chart(grafico)

# Alerta: no inscriptos con actividad
st.header("Alerta: estudiantes no inscriptos con actividad")
if no_inscriptos_activos.empty:
    st.success("No hay estudiantes fuera del padrón con actividad reciente.")
else:
    st.error(
        f"{len(no_inscriptos_activos)} estudiantes usan el aula virtual sin estar inscriptos. "
        "Hay que regularizar su matrícula o darles de baja del aula."
    )
    alerta = no_inscriptos_activos.sort_values(["materia", "dias_sin_acceso"])
    tabla_alerta = pd.DataFrame({
        "Materia": alerta["materia"],
        "Apellido": alerta["apellido"],
        "Nombre": alerta["nombre"],
        "Usuario": alerta["usuario"],
        "Situación en el padrón": alerta["estado_matricula"].apply(estado_en_padron),
        "Último acceso": alerta["ultimo_acceso"].dt.strftime("%d/%m/%Y"),
        "Interacciones": alerta["eventos"],
    })
    st.dataframe(tabla_alerta, hide_index=True)
    st.download_button(
        "Descargar lista (CSV)",
        tabla_alerta.to_csv(index=False).encode("utf-8-sig"),
        file_name="no_inscriptos_con_actividad.csv",
        mime="text/csv",
    )

# Mapa de inscriptos sin participación
st.header("Mapa de inscriptos sin participación")
st.write(f"Inscriptos que no entraron en los últimos {DIAS_INACTIVO} días, según cuánto tiempo llevan sin entrar.")

tramos_sin_actividad = TRAMOS[1:]
mapa = pd.crosstab(inscriptos["materia"], inscriptos["tramo"]).reindex(columns=tramos_sin_actividad, fill_value=0)
grafico = px.imshow(
    mapa,
    text_auto=True,
    color_continuous_scale="Reds",
    aspect="auto",
    labels={"x": "Días sin entrar", "y": "Materia", "color": "Inscriptos"},
)
st.plotly_chart(grafico)

st.subheader("Inscriptos sin actividad reciente")
sin_actividad = inscriptos_sin_actividad.sort_values(["materia", "dias_sin_acceso"], ascending=[True, False])
st.dataframe(
    pd.DataFrame({
        "Materia": sin_actividad["materia"],
        "Apellido": sin_actividad["apellido"],
        "Nombre": sin_actividad["nombre"],
        "Usuario": sin_actividad["usuario"],
        "Días sin entrar": sin_actividad["dias_sin_acceso"],
        "Último acceso": sin_actividad["ultimo_acceso"].dt.strftime("%d/%m/%Y").fillna("Nunca"),
        "Semáforo": sin_actividad["semaforo"],
    }),
    hide_index=True,
)
