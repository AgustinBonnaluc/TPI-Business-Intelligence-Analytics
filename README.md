# Herramienta de Análisis y Seguimiento Académico LMS

Trabajo Final Integrador de Business Intelligence & Analytics (Universidad de Palermo).

Dashboard en Streamlit para analizar participación, trazabilidad, rendimiento y matrícula de tres materias:
Álgebra, Probabilidad y Estadística, y Algoritmos y Estructuras de Datos.

## Estructura

- `data/raw/`: Excel originales del LMS.
- `data/processed/`: datos limpios que usa la app.
- `notebooks/`: exploración de datos.
- `src/`: limpieza, modelado y KPIs.
- `app/`: aplicación de Streamlit.
- `docs/`: informe técnico.

## Ejecución local

```bash
pip install -r requirements.txt
python -m src.limpieza   # genera data/processed/ a partir de los Excel en data/raw/
streamlit run app/streamlit_app.py
```

## Cargar datos nuevos desde la app

La página **Cargar datos** acepta reportes del LMS con el mismo formato que los de `data/raw/`
(calificaciones, participación, trazabilidad o padrón), sueltos o en un `.zip`. Cada archivo se
reconoce por su contenido, se limpia con `src/limpieza.py` y se combina con los datos actuales
(`src/carga.py`). El resultado se guarda en `data/actualizado/` y todos los tableros lo usan.

- Una evaluación nueva se agrega; una ya cargada se reemplaza por la exportación más reciente.
- Una materia nueva pide sus reglas (suma o promedio, nota para regularizar y para promocionar),
  que se guardan en `config/materias.json`.
- "Volver a los datos originales" borra `data/actualizado/` y restaura la configuración.

En Streamlit Community Cloud lo cargado se pierde cuando la app se reinicia.

## Despliegue

En Streamlit Community Cloud, indicar `app/streamlit_app.py` como archivo principal.
