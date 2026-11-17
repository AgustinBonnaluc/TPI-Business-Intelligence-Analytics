"""Utilidades compartidas por los tableros Streamlit."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.kpis import cargar_datos as _cargar_datos
from src.kpis import dia_de_corte


@st.cache_data(show_spinner="Cargando datos…")
def cargar_datos():
    """Lee las tablas procesadas una sola vez por sesión de Streamlit."""
    return _cargar_datos()


def filtros_sidebar(datos, clave: str = "default"):
    """Sidebar con fecha de corte y selección de materias.

    Devuelve `(fecha_corte: Timestamp, materias: list[str])`.
    Si no hay materias seleccionadas, usa todas.
    """
    st.sidebar.header("Filtros")

    corte_default = dia_de_corte(datos).date()
    fecha = st.sidebar.date_input(
        "Fecha de corte",
        value=corte_default,
        max_value=corte_default,
        key=f"fecha_corte_{clave}",
    )
    if isinstance(fecha, tuple):
        fecha = fecha[0] if fecha else corte_default

    todas = sorted(datos["participacion"]["materia"].dropna().unique())
    materias = st.sidebar.multiselect(
        "Materias",
        options=todas,
        default=todas,
        key=f"materias_{clave}",
    )
    if not materias:
        materias = todas

    return pd.Timestamp(fecha).normalize(), materias


def filtrar_materias(df: pd.DataFrame, materias: list[str]) -> pd.DataFrame:
    """Filtra un DataFrame por la columna `materia`."""
    return df[df["materia"].isin(materias)].copy()
