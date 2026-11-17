import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.kpis import (
    DIAS_INACTIVO,
    NOTA_REGULAR_BAJA,
    cargar_datos,
    dia_de_corte,
    eventos_alumnos,
    notas_por_evaluacion,
    resumen_alumnos,
)

# Cada color del semáforo se muestra con el cuadro de Streamlit del mismo color
MOSTRAR_SEMAFORO = {"Verde": st.success, "Amarillo": st.warning, "Rojo": st.error}


@st.cache_data
def leer_datos():
    return cargar_datos()


@st.cache_data
def calcular_resumen(fecha_corte):
    return resumen_alumnos(leer_datos(), fecha_corte)


@st.cache_data
def calcular_notas(fecha_corte):
    return notas_por_evaluacion(leer_datos(), fecha_corte)


def formatear_minutos(minutos):
    horas = int(minutos // 60)
    resto = int(minutos % 60)
    if horas == 0:
        return f"{resto} min"
    return f"{horas} h {resto} min"


def motivos_semaforo(alumno):
    """Explica por qué el alumno tiene el color de semáforo que tiene."""
    motivos = []
    dias = alumno["dias_sin_acceso"]
    if pd.isna(dias):
        motivos.append("nunca entró al aula virtual")
    elif dias > DIAS_INACTIVO:
        motivos.append(f"{dias} días sin entrar")

    if alumno["condicion"] == "Libre":
        motivos.append("condición Libre")
    elif alumno["condicion"] == "Regular" and alumno["nota_final"] < NOTA_REGULAR_BAJA:
        motivos.append(f"Regular con nota menor a {NOTA_REGULAR_BAJA}")
    return motivos


st.title("Ficha Individual 360°")
st.write("Situación de un estudiante en una materia: actividad, notas y semáforo de riesgo.")

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
materia = st.sidebar.selectbox("Materia", sorted(resumen["materia"].unique()))

# Solo los inscriptos en el padrón de la materia elegida
alumnos_materia = resumen[(resumen["materia"] == materia) & resumen["inscripto"]]
alumnos_materia = alumnos_materia.sort_values(["apellido", "nombre"])
nombres = alumnos_materia["apellido"] + ", " + alumnos_materia["nombre"] + " (" + alumnos_materia["usuario"] + ")"
nombre_por_usuario = dict(zip(alumnos_materia["usuario"], nombres))
usuario = st.sidebar.selectbox("Estudiante", list(nombre_por_usuario), format_func=nombre_por_usuario.get)
alumno = alumnos_materia[alumnos_materia["usuario"] == usuario].iloc[0]

# Encabezado y semáforo
st.subheader(f"{alumno['nombre']} {alumno['apellido']}")
st.caption(f"{materia} · usuario {usuario} · datos al {fecha_corte:%d/%m/%Y}")

color = alumno["semaforo"]
motivos = motivos_semaforo(alumno)
mensaje = f"**Semáforo {color}**: " + (", ".join(motivos) if motivos else "sin alertas")
MOSTRAR_SEMAFORO[color](mensaje)

# Indicadores
st.write("")
col1, col2, col3, col4 = st.columns(4)
nota = alumno["nota_final"]
col1.metric("Nota final", "—" if pd.isna(nota) else f"{nota:.1f}")
col2.metric("Condición", alumno["condicion"] or "—")
col3.metric("No rendidas","—" if pd.isna(alumno["evaluaciones_no_rendidas"]) else alumno["evaluaciones_no_rendidas"])
col4.metric(
    "Avance",
    "—" if pd.isna(alumno["avance"]) else f"{alumno['avance']:.0f} %",
    help="Del reporte de participación: es el avance al exportar los datos, no cambia con la fecha de corte.",
)

col1, col2, col3, col4 = st.columns(4)
dias = alumno["dias_sin_acceso"]
col1.metric("Días sin entrar", "Nunca entró" if pd.isna(dias) else dias)
col2.metric("Sesiones", alumno["sesiones"])
col3.metric("Tiempo total", formatear_minutos(alumno["tiempo_min"]))
col4.metric("Interacciones", alumno["eventos"])

# Notas
st.header("Notas")
notas = calcular_notas(fecha_corte)
notas_materia = notas[notas["materia"] == materia]
notas_alumno = notas_materia[notas_materia["usuario"] == usuario]

if notas_alumno.empty:
    st.info("No hay evaluaciones que cuenten para la nota a la fecha de corte.")
else:
    comparacion = pd.DataFrame({
        "Estudiante": notas_alumno.set_index("evaluacion")["nota_pct"],
        "Promedio del curso": notas_materia.groupby("evaluacion")["nota_pct"].mean(),
    })
    grafico = px.bar(
        comparacion,
        barmode="group",
        range_y=[0, 100],
        labels={"evaluacion": "Evaluación", "value": "Nota (%)", "variable": ""},
        title="Nota del estudiante vs. promedio del curso",
    )
    st.plotly_chart(grafico)

    tabla_notas = pd.DataFrame({
        "Evaluación": notas_alumno["evaluacion"],
        "Tipo": notas_alumno["tipo_evaluacion"],
        "Nota": notas_alumno["nota"],
        "Nota máxima": notas_alumno["nota_maxima"],
        "Rendida": notas_alumno["rendida"].map({True: "Sí", False: "No (cuenta 0)"}),
    })
    st.dataframe(tabla_notas, hide_index=True)

# Trazabilidad
st.header("Actividad en el aula virtual")
eventos = eventos_alumnos(datos, fecha_corte)
eventos = eventos[(eventos["materia"] == materia) & (eventos["usuario"] == usuario)]

if eventos.empty:
    st.info("El estudiante no registra actividad hasta la fecha de corte.")
else:
    col1, col2 = st.columns(2)

    # Se muestran todas las semanas de la cursada, así las semanas sin actividad quedan en 0
    semanas = pd.period_range(primer_dia, fecha_corte, freq="W")
    por_semana = eventos["fecha"].dt.to_period("W").value_counts().reindex(semanas, fill_value=0)
    por_semana = pd.DataFrame({"Semana": semanas.start_time, "Interacciones": por_semana.values})
    grafico = px.bar(por_semana, x="Semana", y="Interacciones", title="Interacciones por semana")
    col1.plotly_chart(grafico)

    por_seccion = eventos["seccion_principal"].value_counts().rename("Interacciones")
    por_seccion = por_seccion.rename_axis("Sección").reset_index()
    grafico = px.bar(
        por_seccion, x="Interacciones", y="Sección", orientation="h", title="Interacciones por sección"
    )
    grafico.update_yaxes(categoryorder="total ascending")
    col2.plotly_chart(grafico)

    st.subheader("Últimas interacciones")
    ultimas = eventos.sort_values("fecha", ascending=False).head(15)
    st.dataframe(
        pd.DataFrame({
            "Fecha": ultimas["fecha"].dt.strftime("%d/%m/%Y %H:%M"),
            "Sección": ultimas["seccion_principal"],
            "Acción": ultimas["accion"],
            "Recurso": ultimas["recurso"],
        }),
        hide_index=True,
    )
