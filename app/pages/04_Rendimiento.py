import sys
from pathlib import Path

import streamlit as st
import plotly.express as px

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.ui_academica import (
    COLORES, cargar, descargar, detalle_estudiantes, encabezado, filtros,
    formato, grafico, medida_resultado,
)
from src.kpis_academicos import ESTADOS, resumen_instrumentos

st.set_page_config(page_title="Rendimiento académico", page_icon="📊", layout="wide")
encabezado(4, "Rendimiento académico", "Explorá los resultados por instrumento, la cobertura de notas y el avance académico observado.")
datos, reglas, base, catalogo = cargar()
materia, regla, notas, resumen, elegidas = filtros(datos, reglas, base, catalogo, "rendimiento")
resultado, etiqueta = medida_resultado(regla)

a, b, c, d = st.columns(4)
a.metric("Estudiantes en la población", len(resumen))
con_nota = int(resumen["instrumentos_con_nota"].gt(0).sum())
b.metric("Con alguna nota", con_nota, help="Denominador: estudiantes de la población seleccionada.")
c.metric("Instrumentos seleccionados", len(elegidas))
d.metric("Puntos promedio observados" if regla and regla["calculo"] == "suma" else "Promedio observado", formato(resumen[resultado].mean()), help="Promedio entre estudiantes con resultado observado. No se incluyen estudiantes sin nota ni se imputan ceros.")

tab_instrumentos, tab_estudiantes, tab_metodo = st.tabs(["Por instrumento", "Por estudiante", "Cómo se calcula"])
with tab_instrumentos:
    st.subheader("Comparación entre instrumentos")
    escala = st.radio("Escala del gráfico", ["Porcentaje del instrumento", "Puntos originales"], horizontal=True)
    tabla = resumen_instrumentos(notas, len(resumen)).set_index("evaluacion").reindex(elegidas)
    tabla["con_nota"] = tabla["con_nota"].fillna(0).astype(int)
    tabla["sin_nota"] = len(resumen) - tabla["con_nota"]
    tabla["cobertura_pct"] = tabla["con_nota"] / len(resumen) * 100
    maximos = catalogo[catalogo["materia"].eq(materia)].set_index("evaluacion")["nota_maxima"]
    tabla["nota_maxima"] = maximos.reindex(tabla.index)
    tabla = tabla.reset_index()
    y = "promedio_pct" if escala == "Porcentaje del instrumento" else "promedio"
    fig = px.bar(tabla, x="evaluacion", y=y, hover_data=["con_nota", "nota_maxima", "cobertura_pct"], labels={"evaluacion": "Instrumento", y: "Promedio (%)" if y == "promedio_pct" else "Promedio (puntos)", "con_nota": "Estudiantes con nota", "nota_maxima": "Puntos posibles", "cobertura_pct": "Cobertura (%)"})
    grafico(fig, "rendimiento_instrumentos")
    st.caption("Cada promedio usa únicamente notas registradas, incluidos los ceros explícitos. Los porcentajes permiten comparar instrumentos con diferentes máximos; no reemplazan la suma de puntos de Álgebra.")
    nombres = {"evaluacion": "Instrumento", "con_nota": "Con nota", "sin_nota": "Sin nota", "promedio": "Promedio (puntos)", "promedio_pct": "Promedio (%)", "minima": "Mínima", "maxima": "Máxima", "nota_maxima": "Máximo posible", "cobertura_pct": "Cobertura (%)"}
    st.dataframe(tabla.rename(columns=nombres).round(2), hide_index=True, width="stretch")
    descargar(tabla.rename(columns=nombres), "resultados_por_instrumento.csv", "descarga_instrumentos")

with tab_estudiantes:
    izquierda, derecha = st.columns(2)
    with izquierda:
        st.subheader("Distribución de resultados parciales")
        observados = resumen[resumen[resultado].notna()]
        if observados.empty:
            st.info("No hay resultados observados en la selección.")
        else:
            fig = px.histogram(observados, x=resultado, nbins=15, labels={resultado: etiqueta})
            fig.update_yaxes(title="Estudiantes")
            grafico(fig, "rendimiento_distribucion")
    with derecha:
        st.subheader("Condición académica final")
        conteos = resumen["condicion"].value_counts().reindex(ESTADOS, fill_value=0).rename_axis("Condición").reset_index(name="Estudiantes")
        fig = px.bar(conteos, x="Condición", y="Estudiantes", color="Condición", color_discrete_map=COLORES, text="Estudiantes")
        fig.update_layout(showlegend=False)
        grafico(fig, "rendimiento_condiciones")
        st.caption("Sin determinar: no hay cierre y esquema académico suficientes, o faltan notas requeridas. No equivale a Libre.")
    st.subheader("Detalle de estudiantes")
    buscar = st.text_input("Buscar por usuario o nombre", placeholder="Escribí para filtrar esta tabla")
    detalle = detalle_estudiantes(resumen, resultado, etiqueta)
    if buscar:
        coincide = detalle["Usuario"].str.contains(buscar, case=False, regex=False, na=False) | detalle["Estudiante"].str.contains(buscar, case=False, regex=False, na=False)
        detalle = detalle[coincide]
    st.dataframe(detalle.round(2), hide_index=True, width="stretch")
    descargar(detalle, "rendimiento_estudiantes.csv", "descarga_rendimiento")

with tab_metodo:
    st.markdown("""
- **Unidad:** estudiante y materia; las comparaciones por instrumento usan una nota por estudiante e instrumento.
- **Población:** el filtro lateral define el denominador; incluye a quienes no tienen notas.
- **Cobertura de notas:** instrumentos con nota / instrumentos seleccionados × 100. Describe los archivos disponibles, no la finalización de la cursada.
- **Álgebra:** suma de puntos observados. **Materias con regla de promedio:** promedio de las notas observadas. Ambos se identifican como resultados parciales.
- **Faltantes:** se conservan sin nota; los ceros explícitos sí se calculan. No se deducen vencimientos a partir de las fechas de exportación.
- **Condición final:** exige cierre confirmado y notas completas según la configuración de la materia. Su semáforo académico no depende de la actividad.
- **Actualizaciones:** se conserva la exportación más reciente por estudiante e instrumento. Fechas iguales con notas contradictorias se rechazan.
""")
    if regla:
        st.write(f"Umbrales configurados: Regular desde {regla['regular_desde']:g}; Promociona desde {regla['promocion_desde']:g}. Se aplican cuando se puede determinar la condición final.")
