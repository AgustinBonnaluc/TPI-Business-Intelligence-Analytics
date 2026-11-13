from pathlib import Path

import streamlit as st

from src.kpis import PROCESSED_DIR, TABLAS, cargar_datos
from src.kpis_academicos import (
    cargar_reglas, catalogo_evaluaciones, poblacion, preparar_calificaciones,
    resumen_academico,
)

RAIZ = Path(__file__).resolve().parents[1]
COLORES = {"Promociona": "#228565", "Regular": "#D49B21", "Libre": "#CE5260", "Sin determinar": "#8492A6"}


def firma_archivos():
    rutas = [PROCESSED_DIR / f"{tabla}.parquet" for tabla in TABLAS]
    rutas.append(RAIZ / "config" / "materias.json")
    return tuple((str(r), r.stat().st_mtime_ns, r.stat().st_size) for r in rutas)


@st.cache_data(show_spinner="Leyendo datos procesados…")
def _cargar(firma):
    datos = cargar_datos()
    datos["calificaciones"] = preparar_calificaciones(datos["calificaciones"])
    reglas = cargar_reglas()
    base = poblacion(datos)
    catalogo = catalogo_evaluaciones(datos["calificaciones"])
    return datos, reglas, base, catalogo


def cargar():
    try:
        return _cargar(firma_archivos())
    except (OSError, ValueError, KeyError, ImportError) as exc:
        st.error(f"No se pudieron cargar los datos: {exc}")
        st.info("Revisá los Parquet de data/processed/, la configuración de materias y las dependencias del entorno.")
        st.stop()


def encabezado(numero, titulo, descripcion):
    st.caption(f"SEGUIMIENTO ACADÉMICO  /  TABLERO {numero}")
    st.title(titulo)
    st.write(descripcion)


def filtros(datos, reglas, base, catalogo, prefijo):
    materias = sorted(base["materia"].dropna().unique())
    if not materias:
        st.info("Todavía no hay estudiantes o materias para analizar.")
        st.stop()
    with st.sidebar:
        st.header("Filtros")
        materia = st.selectbox("Asignatura", materias, key=f"{prefijo}_materia")
        por_materia = base[base["materia"].eq(materia)].copy()
        opciones = ["Matrícula aceptada", "Todos con registros"]
        indice = 0 if por_materia["inscripto"].any() else 1
        alcance = st.radio("Población", opciones, index=indice, key=f"{prefijo}_poblacion_{materia}")
        if alcance == opciones[0]:
            por_materia = por_materia[por_materia["inscripto"]]
        disponibles = catalogo.loc[catalogo["materia"].eq(materia), "evaluacion"].tolist()
        elegidas = st.multiselect("Instrumentos", disponibles, default=disponibles, key=f"{prefijo}_evaluaciones_{materia}")
        st.caption("La población incluye estudiantes sin nota. La ausencia de matrícula o participación no se interpreta como nota cero.")
        if st.button("Actualizar datos", key=f"{prefijo}_actualizar"):
            _cargar.clear()
            st.rerun()
    st.caption(f"{materia} · {alcance} · {len(elegidas)} de {len(disponibles)} instrumentos seleccionados")
    if por_materia.empty:
        st.info("No hay estudiantes en esta población. Podés cambiar el filtro a Todos con registros.")
        st.stop()
    if not elegidas:
        st.info("Seleccioná al menos un instrumento en el panel lateral. Si no hay opciones, esta materia todavía no tiene calificaciones disponibles.")
        st.stop()
    notas = datos["calificaciones"]
    notas = notas[notas["materia"].eq(materia) & notas["evaluacion"].isin(elegidas)]
    notas = notas.merge(por_materia[["materia", "usuario"]], on=["materia", "usuario"], validate="many_to_one")
    seleccion = catalogo[catalogo["materia"].eq(materia) & catalogo["evaluacion"].isin(elegidas)]
    resumen = resumen_academico(
        por_materia, notas, reglas,
        catalogo_completo=catalogo,
        catalogo_seleccionado=seleccion,
    )
    regla = reglas.get(materia)
    if regla is None:
        st.info("Esta materia aún no tiene regla académica configurada. Se muestran notas y promedios porcentuales descriptivos, sin condición final.")
    else:
        texto = "Suma de puntos observados" if regla["calculo"] == "suma" else "Promedio de notas observadas"
        st.info(f"Resultado parcial: {texto.lower()}. Las notas faltantes se conservan; no se completan con cero.")
        if "puntos_plan" in regla:
            maximo = catalogo.loc[catalogo["materia"].eq(materia), "nota_maxima"].sum()
            cobertura = f"Cobertura de archivos: {maximo:g} de {regla['puntos_plan']:g} puntos del plan"
            if "instrumentos_plan" in regla:
                cobertura += f"; {len(disponibles)} de {regla['instrumentos_plan']} instrumentos previstos"
            st.caption(cobertura + ".")
    fechas = datos["calificaciones"].loc[datos["calificaciones"]["materia"].eq(materia), "fecha_exportacion"].dropna()
    if not fechas.empty:
        desde, hasta = fechas.min().strftime("%d/%m/%Y"), fechas.max().strftime("%d/%m/%Y")
        st.caption(f"Exportaciones de notas: {desde}" + (f" a {hasta}" if desde != hasta else "") + ". Las notas no se reconstruyen por fecha de actividad.")
    return materia, regla, notas, resumen, elegidas


def medida_resultado(regla):
    if regla is None:
        return "promedio_instrumentos_pct", "Promedio porcentual por instrumento (%)"
    if regla["calculo"] == "suma":
        return "resultado_parcial", "Puntos acumulados observados"
    return "resultado_parcial", "Promedio de notas observadas"


def grafico(figura, clave):
    figura.update_layout(
        template="plotly_white", font=dict(family="Arial", size=13, color="#27384B"),
        margin=dict(l=12, r=12, t=35, b=20), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", colorway=["#147D92", "#228565", "#D49B21", "#CE5260"],
        legend_title_text="", height=390,
    )
    st.plotly_chart(figura, width="stretch", key=clave, config={"displaylogo": False})


def formato(valor, decimales=1):
    return "Sin datos" if valor is None or valor != valor else f"{valor:,.{decimales}f}"


def descargar(tabla, nombre, clave):
    st.download_button("Descargar tabla CSV", tabla.to_csv(index=False).encode("utf-8-sig"), nombre, "text/csv", key=clave)


def detalle_estudiantes(resumen, resultado, etiqueta):
    columnas = ["usuario", "estudiante", "estado", "instrumentos_con_nota", "instrumentos_sin_nota", "cobertura_notas_pct", resultado, "condicion", "motivo_condicion"]
    return resumen[columnas].rename(columns={
        "usuario": "Usuario", "estudiante": "Estudiante", "estado": "Estado de matrícula",
        "instrumentos_con_nota": "Instrumentos con nota", "instrumentos_sin_nota": "Instrumentos sin nota",
        "cobertura_notas_pct": "Cobertura de notas (%)", resultado: etiqueta,
        "condicion": "Condición final", "motivo_condicion": "Motivo de la condición",
    })
