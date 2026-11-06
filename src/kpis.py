"""Cálculo de KPIs, condición final e indicadores de alerta.

Todas las funciones reciben `datos` (el resultado de `cargar_datos()`) y una
`fecha_corte` opcional. Si no se indica fecha de corte, se usa el último día
con actividad registrada.

Uso típico desde un tablero:

    datos = cargar_datos()
    resumen = resumen_alumnos(datos, fecha_corte)
"""

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
TABLAS = ["matricula", "participacion", "trazabilidad", "calificaciones"]

MINUTOS_SESION = 30
DIAS_INACTIVO = 7
DIAS_ALERTA_ROJA = 14
DIAS_MARGEN_EVALUACION = 7

NOTA_REGULAR = 60
NOTA_REGULAR_BAJA = 70
NOTA_PROMOCION = {
    "Álgebra": 85,
    "Probabilidad y Estadística": 85,
    "Algoritmos y Estructuras de Datos": 90,
}

ACCIONES_ENTREGA = ["Realizar evaluación", "Finalizar realización"]


def cargar_datos():
    """Lee las tablas limpias de data/processed/."""
    return {tabla: pd.read_parquet(PROCESSED_DIR / f"{tabla}.parquet") for tabla in TABLAS}


def dia_de_corte(datos, fecha_corte=None):
    """Fecha de corte como día (sin hora). Por defecto, el último día con actividad."""
    if fecha_corte is None:
        fecha_corte = datos["trazabilidad"]["fecha"].max()
    return pd.Timestamp(fecha_corte).normalize()


# Alumnos y actividad

def alumnos(datos):
    """Una fila por alumno y materia del aula virtual, con su situación en el padrón.

    `avance` es el del reporte de participación (foto al momento de exportar).
    """
    participacion = datos["participacion"]
    aula = participacion.loc[
        participacion["perfil"] == "Alumnos",
        ["materia", "usuario", "apellido", "nombre", "avance"],
    ]
    padron = datos["matricula"][["materia", "usuario", "estado"]].rename(columns={"estado": "estado_matricula"})

    resultado = aula.merge(padron, on=["materia", "usuario"], how="left")
    resultado["inscripto"] = resultado["estado_matricula"].eq("Aceptada")
    return resultado.reset_index(drop=True)


def eventos_alumnos(datos, fecha_corte=None):
    """Eventos de alumnos en la trazabilidad hasta la fecha de corte inclusive."""
    dia = dia_de_corte(datos, fecha_corte)
    eventos = datos["trazabilidad"]
    hasta_el_corte = eventos["fecha"].dt.normalize() <= dia
    return eventos[(eventos["perfil"] == "Alumnos") & hasta_el_corte].copy()


def sesiones(datos, fecha_corte=None):
    """Una fila por sesión. Una sesión termina tras 30 minutos sin actividad.

    Una sesión de un único evento tiene duración 0.
    """
    eventos = eventos_alumnos(datos, fecha_corte).sort_values(["materia", "usuario", "fecha"])

    pausa = eventos.groupby(["materia", "usuario"])["fecha"].diff()
    eventos["nueva_sesion"] = pausa.isna() | (pausa > pd.Timedelta(minutes=MINUTOS_SESION))
    eventos["sesion"] = eventos.groupby(["materia", "usuario"])["nueva_sesion"].cumsum()

    resultado = (
        eventos.groupby(["materia", "usuario", "sesion"])
        .agg(inicio=("fecha", "min"), fin=("fecha", "max"), eventos=("fecha", "size"))
        .reset_index()
    )
    resultado["duracion_min"] = (resultado["fin"] - resultado["inicio"]).dt.total_seconds() / 60
    return resultado


# Evaluaciones y notas

def fechas_evaluaciones(datos):
    """Una fila por evaluación con la fecha desde la que cuenta para la nota final.

    La fecha de la evaluación es la primera entrega registrada en la trazabilidad.
    Cuenta para la nota recién una semana después, para no poner un 0 a quien
    todavía estaba dentro del plazo.
    """
    trazabilidad = datos["trazabilidad"]
    entregas = trazabilidad[(trazabilidad["perfil"] == "Alumnos") & trazabilidad["accion"].isin(ACCIONES_ENTREGA)]
    primera_entrega = (
        entregas.groupby(["materia", "recurso"])["fecha"].min()
        .rename_axis(["materia", "evaluacion"])
        .rename("primera_entrega")
        .reset_index()
    )

    evaluaciones = datos["calificaciones"].drop_duplicates(["materia", "evaluacion"])[
        ["materia", "evaluacion", "tipo_evaluacion", "nota_maxima", "fecha_exportacion"]
    ]
    evaluaciones = evaluaciones.merge(primera_entrega, on=["materia", "evaluacion"], how="left")
    # Si no hay entregas en la trazabilidad, se usa la fecha en que se exportaron las notas
    evaluaciones["primera_entrega"] = evaluaciones["primera_entrega"].fillna(evaluaciones["fecha_exportacion"])
    evaluaciones["cuenta_desde"] = (
        evaluaciones["primera_entrega"].dt.normalize() + pd.Timedelta(days=DIAS_MARGEN_EVALUACION)
    )
    return evaluaciones.drop(columns="fecha_exportacion").reset_index(drop=True)


def evaluaciones_vigentes(datos, fecha_corte=None):
    """Evaluaciones que ya cuentan para la nota final a la fecha de corte."""
    dia = dia_de_corte(datos, fecha_corte)
    evaluaciones = fechas_evaluaciones(datos)
    return evaluaciones[evaluaciones["cuenta_desde"] <= dia].reset_index(drop=True)


def notas_por_evaluacion(datos, fecha_corte=None):
    """Una fila por alumno inscripto y evaluación que ya cuenta a la fecha de corte.

    Solo se evalúa a los inscriptos. Si no rindió la evaluación, la nota es 0 y
    `rendida` es False.
    """
    vigentes = evaluaciones_vigentes(datos, fecha_corte)[["materia", "evaluacion", "tipo_evaluacion", "nota_maxima"]]
    inscriptos = alumnos(datos).query("inscripto")[["materia", "usuario"]]

    tabla = inscriptos.merge(vigentes, on="materia")
    notas = datos["calificaciones"][["materia", "evaluacion", "usuario", "nota"]]
    tabla = tabla.merge(notas, on=["materia", "evaluacion", "usuario"], how="left")

    tabla["rendida"] = tabla["nota"].notna()
    tabla["nota"] = tabla["nota"].fillna(0)
    tabla["nota_pct"] = tabla["nota"] / tabla["nota_maxima"] * 100
    return tabla


def nota_final(notas):
    """Nota final de 0 a 100 por alumno y materia, según el esquema de cada materia.

    - Álgebra: puntos obtenidos sobre puntos posibles de lo evaluado hasta ahora.
    - Probabilidad y Estadística: promedio de todos los exámenes (el recuperatorio es uno más).
    - Algoritmos y Estructuras de Datos: promedio de las autoevaluaciones.
    """
    es_algebra = notas["materia"] == "Álgebra"

    puntos = notas[es_algebra].groupby(["materia", "usuario"])[["nota", "nota_maxima"]].sum()
    algebra = puntos["nota"] / puntos["nota_maxima"] * 100

    promedios = notas[~es_algebra].groupby(["materia", "usuario"])["nota_pct"].mean()

    return pd.concat([algebra, promedios]).rename("nota_final")


def condicion(materia, nota):
    """Libre, Regular o Promociona según los umbrales de la consigna."""
    if pd.isna(nota):
        return None
    if nota >= NOTA_PROMOCION[materia]:
        return "Promociona"
    if nota >= NOTA_REGULAR:
        return "Regular"
    return "Libre"


# Resumen por alumno

def nivel_participacion(tiempo_min, materias):
    """Baja (25% con menos tiempo), Media o Alta (25% con más tiempo), dentro de cada materia.

    Quien no tiene tiempo en la plataforma siempre queda en Baja.
    """
    percentil = tiempo_min.groupby(materias).rank(pct=True)
    nivel = pd.cut(percentil, bins=[0, 0.25, 0.75, 1], labels=["Baja", "Media", "Alta"], include_lowest=True)
    return nivel.where(tiempo_min > 0, "Baja")


def semaforo(fila):
    """Solo para inscriptos.

    Rojo: más de 14 días sin entrar, nunca entró o Libre.
    Amarillo: entre 8 y 14 días sin entrar, o Regular con nota menor a 70.
    Verde: el resto.
    """
    if not fila["inscripto"]:
        return None
    dias = fila["dias_sin_acceso"]
    if pd.isna(dias) or dias > DIAS_ALERTA_ROJA or fila["condicion"] == "Libre":
        return "Rojo"
    if dias > DIAS_INACTIVO:
        return "Amarillo"
    if fila["condicion"] == "Regular" and fila["nota_final"] < NOTA_REGULAR_BAJA:
        return "Amarillo"
    return "Verde"


def resumen_alumnos(datos, fecha_corte=None):
    """Una fila por alumno y materia con todos los KPIs compartidos a la fecha de corte.

    Incluye a todos los alumnos del aula (para las alertas de matrícula), pero la
    nota final, la condición, el nivel de participación y el semáforo solo se
    calculan para los inscriptos.
    """
    dia = dia_de_corte(datos, fecha_corte)
    claves = ["materia", "usuario"]
    resumen = alumnos(datos).set_index(claves)

    eventos = eventos_alumnos(datos, dia)
    resumen["eventos"] = eventos.groupby(claves).size()
    resumen["ultimo_acceso"] = eventos.groupby(claves)["fecha"].max()

    por_sesion = sesiones(datos, dia)
    resumen["sesiones"] = por_sesion.groupby(claves).size()
    resumen["tiempo_min"] = por_sesion.groupby(claves)["duracion_min"].sum()

    vigentes = evaluaciones_vigentes(datos, dia)
    con_nota = datos["calificaciones"].merge(vigentes[["materia", "evaluacion"]], on=["materia", "evaluacion"])
    resumen["evaluaciones_rendidas"] = con_nota.groupby(claves).size()
    resumen["nota_final"] = nota_final(notas_por_evaluacion(datos, dia))

    resumen = resumen.reset_index()
    enteros = ["eventos", "sesiones", "evaluaciones_rendidas"]
    resumen[enteros] = resumen[enteros].fillna(0).astype(int)
    resumen["tiempo_min"] = resumen["tiempo_min"].fillna(0)

    total_evaluaciones = resumen["materia"].map(vigentes.groupby("materia").size()).fillna(0)
    no_rendidas = total_evaluaciones - resumen["evaluaciones_rendidas"]
    resumen["evaluaciones_no_rendidas"] = no_rendidas.where(resumen["inscripto"]).astype("Int64")

    resumen["dias_sin_acceso"] = (dia - resumen["ultimo_acceso"].dt.normalize()).dt.days.astype("Int64")
    resumen["activo"] = resumen["dias_sin_acceso"].le(DIAS_INACTIVO).fillna(False).astype(bool)
    resumen["condicion"] = [condicion(m, n) for m, n in zip(resumen["materia"], resumen["nota_final"])]

    inscriptos = resumen["inscripto"]
    resumen["nivel_participacion"] = nivel_participacion(
        resumen.loc[inscriptos, "tiempo_min"], resumen.loc[inscriptos, "materia"]
    )
    resumen["semaforo"] = resumen.apply(semaforo, axis=1)
    resumen["fecha_corte"] = dia
    return resumen
