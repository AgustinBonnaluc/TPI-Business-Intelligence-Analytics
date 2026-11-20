"""Carga de archivos nuevos del LMS desde la app.

Flujo que usa la página "Cargar datos":

1. `leer_subidos()`: identifica, lee y limpia cada Excel (o los Excel de un .zip). No guarda nada.
2. `resumen()`: describe qué va a cambiar cada archivo, para revisarlo antes de aplicar.
3. `aplicar()`: combina los archivos con las tablas actuales y guarda el resultado en
   data/actualizado/. Desde ese momento `cargar_datos()` lee esa carpeta.
4. `restaurar()`: borra data/actualizado/ y vuelve a los datos originales.

Cómo se combina cada tipo de archivo con lo que ya hay:

- calificaciones: una evaluación nueva se agrega; una que ya estaba se reemplaza
  por la exportación más reciente.
- trazabilidad: se suman los eventos y se descartan los repetidos.
- participación y padrón: son una foto de la materia, así que reemplazan los de esa materia.
"""

import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import PurePosixPath

import pandas as pd

from src.kpis import ACTUALIZADO_DIR, CONFIG_MATERIAS, TABLAS, cargar_datos, reglas_materias
from src.limpieza import LIMPIEZA, leer_archivo

NOMBRES_TIPO = {
    "calificaciones": "Calificaciones",
    "participacion": "Participación",
    "trazabilidad": "Trazabilidad",
    "matricula": "Padrón de matriculados",
}

RESPALDO_CONFIG = ACTUALIZADO_DIR / "materias_original.json"
REGISTRO_CARGAS = ACTUALIZADO_DIR / "cargas.json"


@dataclass
class ArchivoLeido:
    nombre: str
    tipo: str = None
    materia: str = None
    tabla: pd.DataFrame = None  # ya limpia, con el mismo formato que los Parquet
    error: str = None


# 1. Lectura

def _excels(nombre, contenido):
    """Un .xlsx tal cual, o los .xlsx que haya dentro de un .zip."""
    if nombre.lower().endswith(".xlsx"):
        return [(nombre, contenido)]
    if nombre.lower().endswith(".zip"):
        with zipfile.ZipFile(BytesIO(contenido)) as comprimido:
            return [
                (PurePosixPath(interno).name, comprimido.read(interno))
                for interno in comprimido.namelist()
                if interno.lower().endswith(".xlsx")
                and not interno.startswith("__MACOSX")
                and not PurePosixPath(interno).name.startswith("~$")
            ]
    raise ValueError("Solo se aceptan archivos .xlsx o .zip")


def leer_subidos(archivos):
    """Lee una lista de (nombre, contenido). Un archivo con problemas no frena a los demás."""
    leidos = []
    for nombre, contenido in archivos:
        try:
            excels = _excels(nombre, contenido)
        except (ValueError, zipfile.BadZipFile) as error:
            leidos.append(ArchivoLeido(nombre, error=str(error)))
            continue

        for nombre_excel, contenido_excel in excels:
            try:
                tipo, materia, cruda = leer_archivo(nombre_excel, contenido_excel)
                tabla = LIMPIEZA[tipo]([cruda])
                leidos.append(ArchivoLeido(nombre_excel, tipo, materia, tabla))
            except Exception as error:  # cualquier problema del archivo se muestra en la página
                leidos.append(ArchivoLeido(nombre_excel, error=f"No se pudo leer: {error}"))
    return leidos


# 2. Combinación con las tablas actuales

def _misma_evaluacion(actual, nueva):
    return actual["materia"].eq(nueva["materia"].iat[0]) & actual["evaluacion"].eq(nueva["evaluacion"].iat[0])


def _es_mas_vieja(actual, nueva):
    """True si ya hay una exportación más reciente de la misma evaluación."""
    misma = _misma_evaluacion(actual, nueva)
    return misma.any() and actual.loc[misma, "fecha_exportacion"].max() > nueva["fecha_exportacion"].max()


def combinar(datos, leidos):
    """Devuelve las cuatro tablas con los archivos nuevos incorporados."""
    tablas = dict(datos)
    for archivo in leidos:
        if archivo.error:
            continue
        actual, nueva = tablas[archivo.tipo], archivo.tabla

        if archivo.tipo == "calificaciones":
            if _es_mas_vieja(actual, nueva):
                continue
            tablas["calificaciones"] = pd.concat([actual[~_misma_evaluacion(actual, nueva)], nueva])
        elif archivo.tipo == "trazabilidad":
            tablas["trazabilidad"] = pd.concat([actual, nueva]).drop_duplicates()
        else:
            otras_materias = actual[actual["materia"] != archivo.materia]
            tablas[archivo.tipo] = pd.concat([otras_materias, nueva])

    return {nombre: tabla.reset_index(drop=True) for nombre, tabla in tablas.items()}


# Resumen para revisar antes de aplicar

def _detalle(archivo, datos):
    actual, nueva = datos[archivo.tipo], archivo.tabla
    materia_cargada = archivo.materia in set(actual["materia"])

    if archivo.tipo == "calificaciones":
        evaluacion = nueva["evaluacion"].iat[0]
        notas = int(nueva["nota"].notna().sum())
        if _es_mas_vieja(actual, nueva):
            return f"{evaluacion}: ya hay una exportación más reciente, se ignora"
        if _misma_evaluacion(actual, nueva).any():
            return f"Reemplaza las notas de {evaluacion} ({notas} notas)"
        return f"Evaluación nueva: {evaluacion} ({notas} notas)"

    if archivo.tipo == "trazabilidad":
        nuevos = len(pd.concat([actual, nueva]).drop_duplicates()) - len(actual)
        cantidad = f"{nuevos:,}".replace(",", ".")
        desde, hasta = nueva["fecha"].min(), nueva["fecha"].max()
        return f"{cantidad} eventos nuevos, del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}"

    if archivo.tipo == "participacion":
        alumnos = int(nueva["perfil"].eq("Alumnos").sum())
        accion = "Reemplaza el reporte" if materia_cargada else "Reporte nuevo"
        return f"{accion} ({alumnos} alumnos)"

    inscriptos = int(nueva["estado"].eq("Aceptada").sum())
    bajas = int(nueva["estado"].eq("Baja").sum())
    accion = "Reemplaza el padrón" if materia_cargada else "Padrón nuevo"
    return f"{accion} ({inscriptos} inscriptos, {bajas} bajas)"


def resumen(leidos, datos):
    """Una fila por archivo: qué es, de qué materia y qué va a cambiar."""
    filas = []
    for archivo in leidos:
        if archivo.error:
            filas.append({"Archivo": archivo.nombre, "Tipo": "—", "Materia": "—", "Qué va a pasar": archivo.error})
        else:
            filas.append({
                "Archivo": archivo.nombre,
                "Tipo": NOMBRES_TIPO[archivo.tipo],
                "Materia": archivo.materia,
                "Qué va a pasar": _detalle(archivo, datos),
            })
    return pd.DataFrame(filas)


def materias_nuevas(leidos):
    """Materias de los archivos que todavía no tienen reglas de cálculo."""
    reglas = reglas_materias()
    return sorted({a.materia for a in leidos if not a.error and a.materia not in reglas})


def materias_sin_padron(leidos, datos):
    """Materias que no tienen padrón, ni cargado ni entre los archivos subidos."""
    con_padron = set(datos["matricula"]["materia"])
    con_padron |= {a.materia for a in leidos if a.tipo == "matricula"}
    return sorted({a.materia for a in leidos if not a.error} - con_padron)


# 3. Aplicar y 4. restaurar

def regla_nueva(calculo, regular_desde, promocion_desde):
    """Regla de una materia con el mismo formato que config/materias.json."""
    return {
        "calculo": calculo,
        "regular_desde": regular_desde,
        "promocion_desde": promocion_desde,
        "cierre_confirmado": False,
        "instrumentos_requeridos": [],
    }


def _guardar_json(ruta, contenido):
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")


def aplicar(leidos, reglas_nuevas):
    """Combina los archivos con los datos actuales y guarda todo en data/actualizado/."""
    validos = [a for a in leidos if not a.error]
    tablas = combinar(cargar_datos(), validos)
    ACTUALIZADO_DIR.mkdir(parents=True, exist_ok=True)

    if reglas_nuevas:
        # Se guarda una copia de la configuración original para poder restaurarla
        if not RESPALDO_CONFIG.exists():
            shutil.copy(CONFIG_MATERIAS, RESPALDO_CONFIG)
        _guardar_json(CONFIG_MATERIAS, reglas_materias() | reglas_nuevas)

    # TABLAS termina en calificaciones, que se guarda última: su presencia es la que activa data/actualizado/
    for nombre in TABLAS:
        tablas[nombre].to_parquet(ACTUALIZADO_DIR / f"{nombre}.parquet", index=False)

    cargas = json.loads(REGISTRO_CARGAS.read_text(encoding="utf-8")) if REGISTRO_CARGAS.exists() else []
    momento = datetime.now().strftime("%d/%m/%Y %H:%M")
    cargas += [{"Cargado": momento, "Archivo": a.nombre, "Tipo": NOMBRES_TIPO[a.tipo], "Materia": a.materia}
               for a in validos]
    _guardar_json(REGISTRO_CARGAS, cargas)


def cargas_realizadas():
    """Archivos cargados desde la app desde la última restauración."""
    if not REGISTRO_CARGAS.exists():
        return pd.DataFrame()
    return pd.DataFrame(json.loads(REGISTRO_CARGAS.read_text(encoding="utf-8")))


def restaurar():
    """Vuelve a los datos y a la configuración de materias originales."""
    if RESPALDO_CONFIG.exists():
        shutil.copy(RESPALDO_CONFIG, CONFIG_MATERIAS)
    shutil.rmtree(ACTUALIZADO_DIR, ignore_errors=True)
