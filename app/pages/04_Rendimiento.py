import sys
from pathlib import Path

import streamlit as st
import plotly.express as px

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.ui_academica import (
    COLORES, cargar, descargar, detalle_estudiantes, encabezado, filtros,
    formato, grafico, medida_resultado,
)
from src.kpis_academicos import ESTADOS_PROVISORIOS, distribucion_resultados, resumen_instrumentos

st.set_page_config(page_title="Rendimiento académico", page_icon="📊", layout="wide")
encabezado(4, "Rendimiento académico", "Explorá los resultados por instrumento, la cobertura de notas y el avance académico observado.")
datos, reglas, base, catalogo = cargar()
materia, regla, notas, resumen, elegidas = filtros(datos, reglas, base, catalogo, "rendimiento")
resultado, etiqueta = medida_resultado(regla)

a, b, c, d = st.columns(4)
a.metric("Estudiantes seleccionados", len(resumen))
con_nota = int(resumen["instrumentos_con_nota"].gt(0).sum())
b.metric("Con notas registradas", con_nota, help="Estudiantes con al menos una nota en los instrumentos seleccionados.")
c.metric("Sin notas registradas", len(resumen) - con_nota, help="Estudiantes sin notas en los instrumentos seleccionados. No se consideran notas cero.")
d.metric("Puntos promedio observados" if regla and regla["calculo"] == "suma" else "Promedio observado", formato(resumen[resultado].mean()), help="Promedio entre estudiantes con resultado observado. No se incluyen estudiantes sin nota ni se imputan ceros.")

tab_instrumentos, tab_estudiantes = st.tabs(["Por instrumento", "Resultados del grupo"])
with tab_instrumentos:
    st.subheader("Comparación entre instrumentos")
    tabla = resumen_instrumentos(notas, len(resumen)).set_index("evaluacion").reindex(elegidas)
    tabla["con_nota"] = tabla["con_nota"].fillna(0).astype(int)
    tabla["sin_nota"] = len(resumen) - tabla["con_nota"]
    tabla["cobertura_pct"] = tabla["con_nota"] / len(resumen) * 100
    maximos = catalogo[catalogo["materia"].eq(materia)].set_index("evaluacion")["nota_maxima"]
    tabla["nota_maxima"] = maximos.reindex(tabla.index)
    tabla = tabla.reset_index()
    if tabla["nota_maxima"].eq(100).all():
        escala = "Puntos originales"
        st.caption("Todos estos instrumentos valen 100 puntos: los puntos y el porcentaje coinciden.")
    else:
        escala = st.radio("Escala del gráfico", ["Porcentaje del instrumento", "Puntos originales"], horizontal=True)
    y = "promedio_pct" if escala == "Porcentaje del instrumento" else "promedio"
    fig = px.bar(tabla, x="evaluacion", y=y, hover_data=["con_nota", "nota_maxima", "cobertura_pct"], labels={"evaluacion": "Instrumento", y: "Promedio (%)" if y == "promedio_pct" else "Promedio (puntos)", "con_nota": "Estudiantes con nota", "nota_maxima": "Puntos posibles", "cobertura_pct": "Cobertura (%)"})
    grafico(fig, "rendimiento_instrumentos")
    st.caption("Cada promedio usa las notas registradas, incluidos los ceros explícitos. La cantidad de estudiantes puede variar entre instrumentos; las barras no necesariamente representan al mismo grupo.")
    if regla and regla["calculo"] == "suma":
        st.caption("El porcentaje permite comparar instrumentos con distintos máximos. El resultado académico se calcula sumando los puntos originales.")
    nombres = {"evaluacion": "Instrumento", "con_nota": "Con nota", "sin_nota": "Sin nota", "promedio": "Promedio (puntos)", "promedio_pct": "Promedio (%)", "minima": "Mínima", "maxima": "Máxima", "nota_maxima": "Máximo posible", "cobertura_pct": "Cobertura (%)"}
    st.dataframe(tabla.rename(columns=nombres).round(2), hide_index=True, width="stretch")
    descargar(tabla.rename(columns=nombres), "resultados_por_instrumento.csv", "descarga_instrumentos")

with tab_estudiantes:
    st.caption(f"Esta vista incluye a los {len(resumen)} estudiantes seleccionados. La distribución de notas usa los {con_nota} con resultado registrado; la situación académica y la tabla incluyen también a quienes no tienen notas. Buscar una persona filtra solo la tabla.")
    izquierda, derecha = st.columns(2)
    with izquierda:
        st.subheader("Distribución de resultados parciales")
        observados = resumen[resumen[resultado].notna()]
        if observados.empty:
            st.info("No hay resultados observados en la selección.")
        else:
            if resultado == "promedio_instrumentos_pct":
                maximo = 100
            elif regla["calculo"] == "suma":
                maximo = max(regla.get("puntos_plan", 0), catalogo.loc[catalogo["materia"].eq(materia), "nota_maxima"].sum())
            else:
                maximo = maximos.reindex(elegidas).max()
            distribucion = distribucion_resultados(observados[resultado], maximo)
            fig = px.bar(distribucion, x="Intervalo", y="Estudiantes")
            fig.update_xaxes(title=etiqueta, categoryorder="array", categoryarray=distribucion["Intervalo"].tolist())
            grafico(fig, "rendimiento_distribucion")
            st.caption("El símbolo < excluye el extremo superior del intervalo. El último grupo sí incluye el máximo de la escala.")
    with derecha:
        st.subheader("Situación académica provisoria")
        conteos = resumen["situacion_provisoria"].value_counts().reindex(ESTADOS_PROVISORIOS, fill_value=0).rename_axis("Situación").reset_index(name="Estudiantes")
        conteos = conteos[conteos["Estudiantes"].gt(0)]
        fig = px.bar(conteos, x="Situación", y="Estudiantes", color="Situación", color_discrete_map=COLORES, text="Estudiantes")
        fig.update_layout(showlegend=False)
        grafico(fig, "rendimiento_condiciones")
        st.caption("Se calcula con las notas disponibles de los instrumentos seleccionados y se actualiza al incorporar notas. No es una condición final.")
        if regla and regla["calculo"] == "suma":
            st.caption("En curso: todavía no alcanza los puntos de regularidad y quedan notas del plan pendientes. Sin notas: no tiene ninguna registrada en la selección.")
    st.subheader("Detalle de estudiantes")
    buscar = st.text_input("Buscar por usuario o nombre", placeholder="Escribí para filtrar esta tabla")
    detalle = detalle_estudiantes(resumen, resultado, etiqueta)
    if buscar:
        coincide = detalle["Usuario"].str.contains(buscar, case=False, regex=False, na=False) | detalle["Estudiante"].str.contains(buscar, case=False, regex=False, na=False)
        detalle = detalle[coincide]
    st.dataframe(detalle.round(2), hide_index=True, width="stretch")
    descargar(detalle, "rendimiento_estudiantes.csv", "descarga_rendimiento")

with st.expander(f"Criterio de cálculo · {materia}"):
    if regla is None:
        st.write("Se muestra el promedio porcentual de las notas registradas por instrumento. La materia todavía no tiene una regla académica configurada.")
    elif regla["calculo"] == "suma":
        st.write(f"{materia}: se suman los puntos obtenidos en los instrumentos seleccionados, sin convertirlos a porcentaje.")
        st.write("Por debajo del umbral de regularidad, la situación permanece En curso mientras falten notas del plan. Los puntos acumulados pueden aumentar al incorporar nuevas evaluaciones.")
    else:
        st.write(f"{materia}: se calcula el promedio de las notas registradas en los instrumentos seleccionados. La situación provisoria se obtiene aplicando los umbrales de esta materia a ese promedio.")
    st.caption("Las notas faltantes no se reemplazan por cero. La cobertura indica cuántos instrumentos seleccionados tienen una nota registrada.")
    if regla:
        st.write(f"Umbrales: Regular desde {regla['regular_desde']:g}; Promociona desde {regla['promocion_desde']:g}. Los resultados se muestran como provisorios.")
