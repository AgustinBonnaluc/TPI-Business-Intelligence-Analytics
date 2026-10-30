import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

st.title("Rendimiento")
st.info("Vista en construcción.")
