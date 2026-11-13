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
materia, regla, notas, resumen, elegidas = filtros(datos, reglas, base, catalogo, "relacion", mostrar_aviso=False)
resultado, etiqueta_resultado = medida_resultado(regla)

izquierda, derecha = st.columns(2)
metricas = {"Tiempo de uso (minutos)": "tiempo_uso_min", "Cantidad de interacciones": "interacciones", "Avance (%)": "avance"}
with izquierda:
    etiqueta_x = st.selectbox("Qué actividad comparar", list(metricas))
with derecha:
    opciones = {etiqueta_resultado: resultado}
    if resultado != "promedio_instrumentos_pct":
        opciones["Promedio porcentual por instrumento (%)"] = "promedio_instrumentos_pct"
    etiqueta_y = st.selectbox("Con qué resultado académico", list(opciones))
x, y = metricas[etiqueta_x], opciones[etiqueta_y]
coeficientes = correlaciones(resumen, x, y)
validos = resumen[resumen[x].notna() & resumen[y].notna()].copy()
a, b, c = st.columns(3)
a.metric("Estudiantes seleccionados", len(resumen))
b.metric("Con nota y participación", coeficientes["n"], help="Tienen tanto un resultado académico como un valor de la actividad elegida. Un cero registrado también cuenta como dato.")
c.metric("Sin datos para comparar", len(resumen) - coeficientes["n"], help="Les falta el resultado académico, el dato de participación o ambos.")
st.caption(f"El gráfico compara a {len(validos)} de los {len(resumen)} estudiantes seleccionados: son quienes tienen los dos datos disponibles.")

st.subheader("Participación y resultados del grupo")
st.write("Cada punto es un estudiante. Más a la derecha indica mayor actividad; más arriba, un resultado académico más alto.")
if validos.empty:
    st.info("No hay pares válidos para este cruce. Podés cambiar la población o revisar si hay datos de participación disponibles para esta materia.")
else:
    fig = px.scatter(validos, x=x, y=y, color="instrumentos_con_nota", hover_name="estudiante", hover_data=["usuario", "instrumentos_con_nota", "cobertura_notas_pct"], color_continuous_scale=["#AFD7DD", "#126E83"], labels={x: etiqueta_x, y: etiqueta_y, "instrumentos_con_nota": "Instrumentos con nota", "usuario": "Usuario", "cobertura_notas_pct": "Cobertura (%)"}, opacity=0.75)
    fig.update_traces(marker=dict(size=10, line=dict(width=0.6, color="white")))
    grafico(fig, "relacion_dispersion")
st.caption("Cada punto representa un estudiante. Diferencias en la cantidad de instrumentos con nota pueden afectar la comparación. Una correlación describe asociación y no demuestra causalidad.")

with st.expander("Detalle estadístico de la relación"):
    a, b = st.columns(2)
    a.metric("Correlación lineal · Pearson", formato(coeficientes["pearson"], 3))
    b.metric("Correlación por orden · Spearman", formato(coeficientes["spearman"], 3))
    st.write("Los coeficientes van de −1 a 1. Cerca de 0, la asociación medida es pequeña. Valores positivos indican que ambas variables tienden a aumentar juntas; valores negativos, que una tiende a disminuir cuando aumenta la otra.")
    st.caption("Pearson mide la asociación lineal. Spearman compara el orden de los valores. Se calculan con los mismos estudiantes y requieren al menos tres observaciones con variación en ambos datos.")

st.subheader("Estudiantes con poca actividad y notas bajas")
st.write("Esta búsqueda reúne a quienes cumplen las dos condiciones elegidas. Sirve para revisar casos y no cambia su situación académica provisoria.")
with st.expander("Cambiar los criterios de búsqueda"):
    a, b = st.columns(2)
    valor_x = float(validos[x].quantile(0.25)) if not validos.empty else 0.0
    with a:
        umbral_x = st.number_input(f"Máximo de actividad · {etiqueta_x}", min_value=0.0, value=max(0.0, valor_x), key=f"umbral_x_{materia}_{x}")
        st.caption("El valor inicial es el percentil 25 de la actividad del grupo con datos comparables. Podés cambiarlo.")
    with b:
        umbral_y = st.number_input(f"Nota inferior a · {etiqueta_y}", min_value=0.0, value=60.0, key=f"umbral_y_{materia}_{y}")

unidades_x = {"tiempo_uso_min": "minutos de uso", "interacciones": "interacciones", "avance": "% de avance"}
unidad_y = "%" if y == "promedio_instrumentos_pct" else "puntos"
st.write(f"Criterios actuales: resultado **menor a {formato(umbral_y)} {unidad_y}** y actividad **menor o igual a {formato(umbral_x)} {unidades_x[x]}**.")
resumen["grupo_exploratorio"] = grupos_exploratorios(resumen, x, y, umbral_x, umbral_y)
coinciden = resumen["grupo_exploratorio"].eq("Menor actividad y resultado bajo el umbral")
st.metric("Estudiantes que cumplen ambos criterios", int(coinciden.sum()))
if regla and regla["calculo"] == "suma" and y == "resultado_parcial":
    st.caption("Se comparan puntos acumulados de una cursada parcial. Estar por debajo de 60 con evaluaciones pendientes no determina la condición Libre.")
columnas = ["usuario", "estudiante", x, y, "instrumentos_con_nota", "cobertura_notas_pct"]
tabla = resumen[columnas].rename(columns={"usuario": "Usuario", "estudiante": "Estudiante", x: etiqueta_x, y: etiqueta_y, "instrumentos_con_nota": "Instrumentos con nota", "cobertura_notas_pct": "Cobertura (%)"})
if coinciden.any():
    para_revisar = tabla.loc[coinciden]
    st.dataframe(para_revisar.round(2), hide_index=True, width="stretch")
    descargar(para_revisar, "estudiantes_para_revisar.csv", "descarga_revision")
else:
    st.info("Ningún estudiante con datos disponibles cumple ambos criterios. Podés modificar los valores en Cambiar los criterios de búsqueda.")

with st.expander("Ver los datos de todos los estudiantes seleccionados"):
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
