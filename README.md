# Herramienta de Análisis y Seguimiento Académico LMS

Trabajo Final Integrador de Business Intelligence & Analytics (Universidad de Palermo).

Dashboard en Streamlit para analizar participación, trazabilidad, rendimiento y matrícula de tres materias:
Álgebra, Probabilidad y Estadística, y Algoritmos y Estructuras de Datos.

## Estructura

- `data/raw/`: Excel originales del LMS (no se suben al repo).
- `data/processed/`: datos limpios que usa la app.
- `notebooks/`: exploración de datos.
- `src/`: limpieza, modelado y KPIs.
- `app/`: aplicación de Streamlit.
- `docs/`: informe técnico.

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

## Despliegue

En Streamlit Community Cloud, indicar `app/streamlit_app.py` como archivo principal.
