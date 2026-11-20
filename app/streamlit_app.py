import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))

st.set_page_config(page_title="Seguimiento académico LMS", layout="wide")


def inicio():
    _, contenido, _ = st.columns([1, 6, 1])
    with contenido:
        st.subheader("Universidad de Palermo")
        st.write("Business Intelligence & Analytics")
        st.caption("Trabajo Final Integrador")
        st.divider()

        st.title("Análisis y seguimiento académico")
        st.write(
            "Participación, rendimiento y seguimiento de estudiantes "
            "a partir de datos del LMS."
        )

        st.divider()
        st.subheader("Integrantes")
        st.markdown("**Agustín Blás Bonnaluc**")
        st.markdown("**Julieta Medina Fernández**")
        st.markdown("**Mariano Sanchez de Vera Bastone**")


paginas = [st.Page(inicio, title="Inicio", default=True)]
for archivo in (
    "01_General.py",
    "02_Participacion.py",
    "03_Trazabilidad.py",
    "04_Rendimiento.py",
    "05_Notas_vs_Participacion.py",
    "06_Individual.py",
    "07_Matricula_Alertas.py",
    "08_Cargar_Datos.py",
):
    paginas.append(st.Page(f"pages/{archivo}"))

st.navigation(paginas, expanded=True).run()
