import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src import carga
from src.kpis import ACTUALIZADO_DIR, cargar_datos, carpeta_datos

CALCULOS = {"Promedio de las notas": "promedio", "Suma de puntos": "suma"}


@st.cache_data(show_spinner="Leyendo los archivos…")
def leer(archivos):
    return carga.leer_subidos(archivos)


st.title("Cargar datos")
st.write(
    "Subí reportes exportados del LMS con el mismo formato que los originales: calificaciones, "
    "participación, trazabilidad o padrón de matriculados. Podés subir varios .xlsx o un .zip. "
    "Antes de aplicar se muestra qué va a cambiar."
)

if "carga_ok" in st.session_state:
    st.success(st.session_state.pop("carga_ok"))

# Estado actual de los datos
if carpeta_datos() == ACTUALIZADO_DIR:
    st.info("Los tableros muestran los datos originales más los archivos cargados desde esta página.")
    with st.expander("Archivos cargados"):
        st.dataframe(carga.cargas_realizadas(), hide_index=True)
    if st.button("Volver a los datos originales"):
        carga.restaurar()
        st.cache_data.clear()
        st.session_state["carga_ok"] = "Se restauraron los datos originales."
        st.rerun()
else:
    st.caption("Los tableros muestran los datos originales del repositorio.")

# Subida de archivos (la clave cambia después de aplicar, para vaciar el selector)
st.session_state.setdefault("carga_n", 0)
subidos = st.file_uploader(
    "Archivos del LMS",
    type=["xlsx", "zip"],
    accept_multiple_files=True,
    key=f"subida_{st.session_state['carga_n']}",
)
if not subidos:
    st.stop()

leidos = leer([(archivo.name, archivo.getvalue()) for archivo in subidos])
datos = cargar_datos()

st.subheader("Qué va a cambiar")
st.dataframe(carga.resumen(leidos, datos), hide_index=True)

validos = [archivo for archivo in leidos if not archivo.error]
if not validos:
    st.error("No se pudo leer ningún archivo. Revisá que sean reportes exportados del LMS.")
    st.stop()

for materia in carga.materias_sin_padron(leidos, datos):
    st.warning(
        f"{materia} no tiene padrón de matriculados: sin padrón no se calculan la nota final, "
        "la condición ni el semáforo. Subí también el padrón de la materia."
    )

with st.form("aplicar"):
    reglas_nuevas = {}
    for materia in carga.materias_nuevas(leidos):
        st.markdown(f"**Materia nueva: {materia}.** Indicá cómo se calcula su nota final (escala 0 a 100).")
        col1, col2, col3 = st.columns(3)
        calculo = col1.radio(
            "Nota final",
            list(CALCULOS),
            key=f"calculo_{materia}",
            help="Suma de puntos: puntos obtenidos sobre los posibles de lo evaluado, como en Álgebra.",
        )
        regular = col2.number_input("Regular desde", 0, 100, 60, key=f"regular_{materia}")
        promocion = col3.number_input("Promociona desde", 0, 100, 85, key=f"promocion_{materia}")
        reglas_nuevas[materia] = carga.regla_nueva(CALCULOS[calculo], regular, promocion)
    aplicar = st.form_submit_button("Aplicar", type="primary")

if aplicar:
    if any(regla["regular_desde"] >= regla["promocion_desde"] for regla in reglas_nuevas.values()):
        st.error("La nota para promocionar tiene que ser mayor que la nota para regularizar.")
        st.stop()
    with st.spinner("Recalculando los tableros…"):
        carga.aplicar(leidos, reglas_nuevas)
    st.cache_data.clear()
    st.session_state["carga_n"] += 1
    cantidad = "1 archivo" if len(validos) == 1 else f"{len(validos)} archivos"
    st.session_state["carga_ok"] = f"Se cargó {cantidad}. Abrí cualquier tablero para ver los datos actualizados."
    st.rerun()
