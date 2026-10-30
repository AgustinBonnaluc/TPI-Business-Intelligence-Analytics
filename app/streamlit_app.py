import sys
from pathlib import Path

import streamlit as st

# Streamlit solo agrega app/ al path; src/ está en la raíz del repo
sys.path.append(str(Path(__file__).resolve().parents[1]))

st.set_page_config(page_title="Seguimiento Académico LMS", layout="wide")

st.title("Herramienta de Análisis y Seguimiento Académico LMS")
st.write("Elegí una vista en el menú lateral.")
