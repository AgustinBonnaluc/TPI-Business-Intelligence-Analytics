"""Lectura y limpieza de los archivos exportados del LMS.

Lee los Excel de data/raw/ y genera cuatro tablas limpias en data/processed/:

- matricula.parquet       una fila por alumno y materia (inscripción vigente)
- participacion.parquet   una fila por usuario y materia (reporte consolidado)
- trazabilidad.parquet    una fila por evento registrado en el aula
- calificaciones.parquet  una fila por alumno y evaluación

Uso, desde la raíz del repo:

    python -m src.limpieza
"""

import html
import re
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RAW_DIR = RAIZ / "data" / "raw"
PROCESSED_DIR = RAIZ / "data" / "processed"

MATERIAS = ["Álgebra", "Probabilidad y Estadística", "Algoritmos y Estructuras de Datos"]



# Bytes 0x80-0x9F que quedaron como caracteres de control: en el original eran
# caracteres Windows-1252 (por ejemplo \x96 es la raya "–").
_CP1252 = {}
for _b in range(0x80, 0xA0):
    try:
        _CP1252[_b] = bytes([_b]).decode("cp1252")
    except UnicodeDecodeError:
        _CP1252[_b] = ""

# Emojis y el espacio que los sigue ("&#128073;  Actividad" -> "Actividad")
_EMOJI = re.compile("[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE00-\uFE0F\u200D]+\\s*")
# Algunos acentos vienen escritos como texto, por ejemplo "realizaci\x{F3}n"
_ESCAPE_HEX = re.compile(r"\\x\{([0-9A-Fa-f]+)\}")


def limpiar_texto(valor):
    """Decodifica entidades HTML y escapes, quita emojis y normaliza espacios."""
    if not isinstance(valor, str):
        return valor
    texto = _ESCAPE_HEX.sub(lambda m: chr(int(m.group(1), 16)), valor)
    texto = html.unescape(texto).translate(_CP1252)
    texto = _EMOJI.sub("", texto).replace("\xa0", " ")
    return re.sub(r"\s+", " ", texto).strip()


def _nfc(texto):
    return unicodedata.normalize("NFC", texto)


def _carpeta(materia):
    """Carpeta de una materia en data/raw, sin depender de la forma Unicode del nombre."""
    for carpeta in RAW_DIR.iterdir():
        if carpeta.is_dir() and _nfc(carpeta.name) == _nfc(materia):
            return carpeta
    raise FileNotFoundError(f"No está la carpeta de '{materia}' en {RAW_DIR}")


def _unico(carpeta, patron):
    archivos = sorted(carpeta.glob(patron))
    if len(archivos) != 1:
        raise FileNotFoundError(f"Se esperaba un archivo '{patron}' en {carpeta} y hay {len(archivos)}")
    return archivos[0]


def limpiar_matricula():
    """Una fila por alumno y materia.

    El sistema de inscripciones guarda un registro por trámite: hay alumnos con
    una baja y una reinscripción, o con varias bajas. Se toma como vigente la
    última inscripción aceptada; si no hay ninguna, el alumno queda como "Baja".
    """
    tablas = []
    for materia in MATERIAS:
        archivo = next(f for f in (RAW_DIR / "Matriculados").glob("*.xlsx") if _nfc(f.stem) == _nfc(materia))
        df = pd.read_excel(archivo, header=1)
        df = df[df["Identificación"].notna()]  # quita la fila final "Cantidad de filas:"
        df = df.rename(columns={
            "Alumno": "alumno",
            "Identificación": "usuario",
            "Comisión": "comision",
            "Estado Insc.": "estado",
            "Instancia": "instancia",
            "Fecha inscripción": "fecha_inscripcion",
            "Nro de Transacción": "nro_transaccion",
        })
        df["materia"] = materia
        tablas.append(df)

    df = pd.concat(tablas, ignore_index=True)
    df["comision"] = df["comision"].astype(int)
    df["nro_transaccion"] = df["nro_transaccion"].astype(int)
    df["fecha_inscripcion"] = pd.to_datetime(df["fecha_inscripcion"], format="%d/%m/%Y %H:%M:%S")

    df["_aceptada"] = df["estado"].eq("Aceptada")
    cantidad_bajas = df[df["estado"].eq("Baja")].groupby(["materia", "usuario"]).size()
    vigente = (
        df.sort_values(["_aceptada", "fecha_inscripcion"])
        .groupby(["materia", "usuario"], as_index=False)
        .tail(1)
        .set_index(["materia", "usuario"])
    )
    vigente["cantidad_bajas"] = cantidad_bajas.reindex(vigente.index, fill_value=0).astype(int)
    vigente = vigente.reset_index()

    columnas = ["materia", "comision", "usuario", "alumno", "estado", "instancia",
                "fecha_inscripcion", "nro_transaccion", "cantidad_bajas"]
    return vigente[columnas].sort_values(["materia", "usuario"]).reset_index(drop=True)



# El encabezado ocupa dos filas (por ejemplo "Foros" arriba y "Cargados" abajo).
COLUMNAS_PARTICIPACION = [
    "usuario", "apellido", "nombre", "email", "aula", "perfil", "fecha_alta", "avance",
    "interacciones", "primera_interaccion", "ultima_interaccion", "tiempo_uso", "emails_enviados",
    "encuestas_cantidad", "encuestas_cargadas",
    "archivos_cantidad", "archivos_cargados",
    "sitios_cantidad", "sitios_cargados",
    "wikis_cantidad", "wikis_cargados", "wikis_paginas_con_revisiones",
    "foros_temas", "foros_cargados", "foros_temas_con_intervencion", "foros_intervenciones",
    "anuncios_cantidad", "anuncios_cargados",
    "noticias_cantidad", "noticias_cargadas",
]


def _tiempo_a_minutos(valor):
    """'HH:MM' -> minutos. Las horas pueden pasar de 24 (por ejemplo '28:54')."""
    if not isinstance(valor, str) or ":" not in valor:
        return pd.NA
    horas, minutos = valor.split(":")
    return int(horas) * 60 + int(minutos)


def limpiar_participacion():
    """Una fila por usuario y materia. Incluye docentes e invitados (columna `perfil`)."""
    tablas = []
    for materia in MATERIAS:
        archivo = _unico(_carpeta(materia), "reporte_participacion_*.xlsx")
        df = pd.read_excel(archivo, header=None, skiprows=7)
        encabezado = pd.read_excel(archivo, header=None, skiprows=5, nrows=1).iloc[0]
        if df.shape[1] != len(COLUMNAS_PARTICIPACION) or encabezado[0] != "Usuario":
            raise ValueError(f"Cambió el formato del reporte de participación: {archivo.name}")
        df.columns = COLUMNAS_PARTICIPACION
        df["materia"] = materia
        tablas.append(df)

    df = pd.concat(tablas, ignore_index=True)
    df = df.drop(columns=["email", "aula"])  # email viene vacío; aula es la materia

    df["fecha_alta"] = pd.to_datetime(df["fecha_alta"], format="%d/%m/%Y")
    for col in ["primera_interaccion", "ultima_interaccion"]:
        df[col] = pd.to_datetime(df[col], format="%d/%m/%Y %H:%M:%S")
    # El staff tiene avance "no aplica": queda vacío
    df["avance"] = pd.to_numeric(df["avance"], errors="coerce").astype("Float64")
    df["tiempo_uso_min"] = df["tiempo_uso"].map(_tiempo_a_minutos).astype("Int64")
    df = df.drop(columns=["tiempo_uso"])

    enteros = [c for c in COLUMNAS_PARTICIPACION[12:] if c in df.columns] + ["interacciones"]
    df[enteros] = df[enteros].astype(int)
    for col in ["apellido", "nombre"]:
        df[col] = df[col].map(limpiar_texto)

    primeras = ["materia", "usuario", "apellido", "nombre", "perfil"]
    return df[primeras + [c for c in df.columns if c not in primeras]]



# Algunas descripciones nombran a otro usuario, por ejemplo
# "Visualización de la realización del usuario 'Nombre Apellido' ...".
# Ese nombre no es un recurso del aula, así que se saltea al extraer el recurso.
_USUARIO_EN_DESCRIPCION = re.compile(r"(usuario )'[^']*'")
_PRIMER_ENTRECOMILLADO = re.compile(r"'([^']*)'")
_UNIDAD = re.compile(r"de la unidad '([^']*)'")

# Acción vacía en el original: se deduce de la descripción
_ACCION_POR_DESCRIPCION = [
    ("Descarga del archivo adjunto", "Descargar adjunto"),
    ("Descarga", "Descargar"),
    ("Modificacion", "Editar intervención"),
]


def _completar_accion(fila):
    if pd.notna(fila["accion"]):
        return fila["accion"]
    for prefijo, accion in _ACCION_POR_DESCRIPCION:
        if fila["descripcion"].startswith(prefijo):
            return accion
    return "Sin dato"


def limpiar_trazabilidad():
    """Una fila por evento del aula, de alumnos y docentes."""
    tablas = []
    for materia in MATERIAS:
        archivo = _unico(_carpeta(materia), "reporte_trazabilidad_*.xlsx")
        df = pd.read_excel(archivo, header=5)
        df["materia"] = materia
        tablas.append(df)

    df = pd.concat(tablas, ignore_index=True)
    # Filas idénticas (mismo usuario, segundo y acción): el LMS registró dos veces el mismo clic
    df = df.drop_duplicates()
    df = df.rename(columns={
        "Fecha": "fecha", "IP Usuario": "ip", "Usuario": "usuario", "Perfil": "perfil",
        "Sección": "seccion", "Acción": "accion", "Descripción": "descripcion",
    })
    # Apellido y nombre ya están en participación; el aula es la materia
    df = df.drop(columns=["Apellido", "Nombre", "Aula"])

    df["fecha"] = pd.to_datetime(df["fecha"], format="%Y-%m-%d %H:%M:%S")
    for col in ["seccion", "accion", "descripcion"]:
        df[col] = df[col].map(limpiar_texto)
    df["accion"] = df.apply(_completar_accion, axis=1)
    df["seccion_principal"] = df["seccion"].str.split(" > ").str[0]
    # El recurso es el primer texto entre comillas que no sea un nombre de usuario
    sin_usuario = df["descripcion"].str.replace(_USUARIO_EN_DESCRIPCION, r"\1", regex=True)
    df["recurso"] = sin_usuario.str.extract(_PRIMER_ENTRECOMILLADO, expand=False)
    df["unidad"] = df["descripcion"].str.extract(_UNIDAD, expand=False)

    columnas = ["materia", "fecha", "usuario", "perfil", "ip", "seccion", "seccion_principal",
                "accion", "descripcion", "recurso", "unidad"]
    return df[columnas].sort_values(["materia", "fecha", "usuario"]).reset_index(drop=True)


def _tipo_evaluacion(nombre):
    n = nombre.lower()
    if "recuperatorio" in n:
        return "Recuperatorio"
    if "parcial" in n:
        return "Parcial"
    if "autoevaluaci" in n:
        return "Autoevaluación"
    if "semanal" in n:
        return "Evaluación semanal"
    if "actividad" in n:
        return "Actividad"
    return "Otra"


def _leer_calificacion(archivo, materia):
    cabecera = pd.read_excel(archivo, header=None, nrows=4)[0].tolist()
    exportacion = cabecera[0].split(":", 1)[1].strip()
    evaluacion = limpiar_texto(cabecera[2].split(":", 1)[1])

    df = pd.read_excel(archivo, header=6)
    if list(df.columns[:5]) != ["Usuario", "Apellido", "Nombre", "Nota", "Observaciones"]:
        raise ValueError(f"Cambió el formato del archivo de calificaciones: {archivo.name}")

    nota = df["Nota"].astype(str).str.extract(r"^\s*([\d.,]+)\s*/\s*([\d.,]+)\s*$")
    nota = nota.apply(lambda c: pd.to_numeric(c.str.replace(",", "."), errors="coerce"))

    return pd.DataFrame({
        "materia": materia,
        "evaluacion": evaluacion,
        "tipo_evaluacion": _tipo_evaluacion(evaluacion),
        "usuario": df["Usuario"],
        "nota": nota[0],
        "nota_maxima": nota[1],
        "nota_pct": (nota[0] / nota[1] * 100).round(2),
        "aprobada": df["Observaciones"].str.strip().str.lower().eq("aprobada"),
        "fecha_exportacion": pd.to_datetime(exportacion, format="%d/%m/%Y %H:%M"),
        "archivo": archivo.name,
    })


def limpiar_calificaciones():
    """Una fila por alumno y evaluación. `nota_pct` lleva todas las notas a escala 0-100."""
    tablas = [
        _leer_calificacion(archivo, materia)
        for materia in MATERIAS
        for archivo in sorted(_carpeta(materia).glob("calificaciones_alumnos_*.xlsx"))
    ]
    df = pd.concat(tablas, ignore_index=True)
    sin_nota = df["nota"].isna().sum()
    if sin_nota:
        print(f"  Aviso: {sin_nota} notas no se pudieron leer y quedaron vacías")
    return df


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    tablas = {
        "matricula": limpiar_matricula,
        "participacion": limpiar_participacion,
        "trazabilidad": limpiar_trazabilidad,
        "calificaciones": limpiar_calificaciones,
    }
    for nombre, funcion in tablas.items():
        print(f"Limpiando {nombre}...")
        df = funcion()
        destino = PROCESSED_DIR / f"{nombre}.parquet"
        df.to_parquet(destino, index=False)
        print(f"  {len(df):,} filas, {df.shape[1]} columnas -> {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
