import sys
from pathlib import Path

import streamlit as st
import plotly.express as px

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.ui_academica import cargar, descargar, encabezado, filtros, formato, grafico, medida_resultado
from src.kpis_academicos import correlaciones, grupos_exploratorios

st.set_page_config(page_title="Notas vs. participación", page_icon="🔎", layout="wide")
encabezado(5, "Notas vs. participación", "Explorá asociaciones entre actividad registrada y resultados académicos, dentro de una misma materia.")
datos, reglas, base, catalogo = cargar()
materia, regla, notas, resumen, elegidas = filtros(datos, reglas, base, catalogo, "relacion")
resultado, etiqueta_resultado = medida_resultado(regla)

izquierda, derecha = st.columns(2)
metricas = {"Tiempo de uso reportado (minutos)": "tiempo_uso_min", "Interacciones reportadas": "interacciones", "Avance reportado (%)": "avance"}
with izquierda:
    etiqueta_x = st.selectbox("Participación", list(metricas))
with derecha:
    opciones = {etiqueta_resultado: resultado}
    if resultado != "promedio_instrumentos_pct":
        opciones["Promedio porcentual por instrumento (%)"] = "promedio_instrumentos_pct"
    etiqueta_y = st.selectbox("Rendimiento", list(opciones))
x, y = metricas[etiqueta_x], opciones[etiqueta_y]
coeficientes = correlaciones(resumen, x, y)
validos = resumen[resumen[x].notna() & resumen[y].notna()].copy()
a, b, c, d = st.columns(4)
a.metric("Estudiantes en la población", len(resumen))
b.metric("Pares válidos", coeficientes["n"], help="Estudiantes con las dos medidas presentes. Los ceros registrados se incluyen.")
c.metric("Pearson · r", formato(coeficientes["pearson"], 3))
d.metric("Spearman · ρ", formato(coeficientes["spearman"], 3))
st.caption(f"Se excluyen de la correlación {len(resumen) - len(validos)} estudiantes por falta de alguna medida. Se necesitan al menos tres pares y variación en ambos ejes.")

st.subheader("Dispersión de estudiantes")
if validos.empty:
    st.info("No hay pares válidos para este cruce. Podés cambiar la población o revisar si hay datos de participación disponibles para esta materia.")
else:
    fig = px.scatter(validos, x=x, y=y, color="instrumentos_con_nota", hover_name="estudiante", hover_data=["usuario", "instrumentos_con_nota", "cobertura_notas_pct"], color_continuous_scale=["#AFD7DD", "#126E83"], labels={x: etiqueta_x, y: etiqueta_y, "instrumentos_con_nota": "Instrumentos con nota", "usuario": "Usuario", "cobertura_notas_pct": "Cobertura (%)"}, opacity=0.75)
    fig.update_traces(marker=dict(size=10, line=dict(width=0.6, color="white")))
    grafico(fig, "relacion_dispersion")
st.caption("Cada punto representa un estudiante. Diferencias en la cantidad de instrumentos con nota pueden afectar la comparación. Una correlación describe asociación y no demuestra causalidad.")

with st.expander("Puntos de atención exploratorios", expanded=True):
    st.write("Elegí umbrales para localizar estudiantes con menor actividad y resultados bajos respecto de esa referencia. Este grupo no define la condición académica ni demuestra riesgo de abandono.")
    a, b = st.columns(2)
    valor_x = float(validos[x].quantile(0.25)) if not validos.empty else 0.0
    with a:
        umbral_x = st.number_input(f"Actividad menor o igual a · {etiqueta_x}", min_value=0.0, value=max(0.0, valor_x), key=f"umbral_x_{materia}_{x}")
        st.caption("Valor inicial: percentil 25 de los pares válidos de la selección.")
    with b:
        umbral_y = st.number_input(f"Resultado menor a · {etiqueta_y}", min_value=0.0, value=60.0, key=f"umbral_y_{materia}_{y}")
    resumen["grupo_exploratorio"] = grupos_exploratorios(resumen, x, y, umbral_x, umbral_y)
    grupo_atencion = "Menor actividad y resultado bajo el umbral"
    cantidad = int(resumen["grupo_exploratorio"].eq(grupo_atencion).sum())
    st.metric("Estudiantes bajo ambos umbrales", cantidad)
    if regla and regla["calculo"] == "suma" and y == "resultado_parcial":
        st.caption("En Álgebra se comparan puntos parciales. Estar por debajo de 60 con instrumentos faltantes no determina la condición Libre.")
    conteos = resumen["grupo_exploratorio"].value_counts().rename_axis("Grupo").reset_index(name="Estudiantes")
    fig = px.bar(conteos, x="Estudiantes", y="Grupo", orientation="h", text="Estudiantes")
    grafico(fig, "relacion_grupos")
    solo_atencion = st.checkbox("Mostrar solo estudiantes bajo ambos umbrales")
    tabla = resumen[resumen["grupo_exploratorio"].eq(grupo_atencion)] if solo_atencion else resumen
    columnas = ["usuario", "estudiante", x, y, "instrumentos_con_nota", "cobertura_notas_pct", "grupo_exploratorio"]
    tabla = tabla[columnas].rename(columns={"usuario": "Usuario", "estudiante": "Estudiante", x: etiqueta_x, y: etiqueta_y, "instrumentos_con_nota": "Instrumentos con nota", "cobertura_notas_pct": "Cobertura (%)", "grupo_exploratorio": "Grupo exploratorio"})
    st.dataframe(tabla.round(2), hide_index=True, width="stretch")
    descargar(tabla, "notas_vs_participacion.csv", "descarga_relacion")

with st.expander("Fuentes y alcance del análisis"):
    st.markdown("""
- Las notas se cruzan con participación mediante **materia + usuario**, con una fila por estudiante y materia.
- Tiempo, interacciones y avance provienen del **reporte de participación**. El tiempo reportado no es una estimación de sesiones reconstruidas desde eventos.
- Los reportes son fotos acumuladas. No se presentan como datos de un período histórico seleccionado ni prueban que la actividad haya ocurrido antes de la nota.
- El resultado usa los instrumentos elegidos. El promedio porcentual por instrumento es descriptivo y no reemplaza el sistema acumulativo de Álgebra.
- Pearson mide asociación lineal; Spearman compara los rangos, promediando los empates. Ambos usan exactamente los mismos pares válidos.
- La ausencia de un reporte queda sin dato. Un cero explícito de actividad se conserva y puede entrar en el grupo exploratorio.
""")
