import json
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
CLAVES = ["materia", "usuario"]
CLAVE_NOTA = CLAVES + ["evaluacion"]
ESTADOS = ["Promociona", "Regular", "Libre", "Sin determinar"]


def cargar_reglas(ruta=None):
    ruta = Path(ruta) if ruta else RAIZ / "config" / "materias.json"
    reglas = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(reglas, dict):
        raise ValueError("La configuración debe contener una regla por materia.")
    for materia, regla in reglas.items():
        if not isinstance(regla, dict):
            raise ValueError(f"La configuración de {materia} debe ser un objeto.")
        if regla.get("calculo") not in ("suma", "promedio"):
            raise ValueError(f"Regla de cálculo no válida para {materia}.")
        regular, promocion = regla.get("regular_desde"), regla.get("promocion_desde")
        if any(isinstance(valor, bool) or not isinstance(valor, (int, float)) for valor in (regular, promocion)):
            raise ValueError(f"Faltan umbrales numéricos para {materia}.")
        if not np.isfinite([regular, promocion]).all() or not 0 <= regular < promocion:
            raise ValueError(f"Los umbrales de {materia} deben ser crecientes.")
        requeridos = regla.get("instrumentos_requeridos", [])
        if (
            not isinstance(requeridos, list)
            or any(not isinstance(nombre, str) or not nombre.strip() for nombre in requeridos)
            or len(requeridos) != len(set(requeridos))
        ):
            raise ValueError(f"Revisar instrumentos requeridos de {materia}.")
        if not isinstance(regla.get("cierre_confirmado", False), bool):
            raise ValueError(f"El cierre confirmado de {materia} debe ser true o false.")
    return reglas


def _identificadores(df, requeridas):
    faltan = set(requeridas) - set(df.columns)
    if faltan:
        raise ValueError(f"Faltan columnas: {', '.join(sorted(faltan))}.")
    df = df.copy()
    for col in [c for c in ("materia", "usuario", "evaluacion") if c in requeridas]:
        df[col] = df[col].astype("string").str.normalize("NFC").str.strip()
        if (df[col].isna() | df[col].eq("")).any():
            raise ValueError(f"Hay identificadores vacíos en {col}.")
    return df


def preparar_calificaciones(df):
    """Conserva la última exportación por estudiante e instrumento; rechaza conflictos."""
    df = _identificadores(df, CLAVE_NOTA + ["nota", "nota_maxima"])
    for col in ("nota", "nota_maxima"):
        original = df[col]
        df[col] = pd.to_numeric(original, errors="coerce")
        if (original.notna() & df[col].isna()).any():
            raise ValueError(f"Hay valores no numéricos en {col}.")
    if "fecha_exportacion" in df:
        original = df["fecha_exportacion"]
        df["fecha_exportacion"] = pd.to_datetime(original, errors="coerce")
        if (original.notna() & df["fecha_exportacion"].isna()).any():
            raise ValueError("Hay fechas de exportación no válidas.")
    else:
        df["fecha_exportacion"] = pd.NaT
    # Una fecha desconocida no debe reemplazar una exportación fechada.
    df = df.sort_values("fecha_exportacion", na_position="first", kind="stable")
    ultima = df.groupby(CLAVE_NOTA, dropna=False)["fecha_exportacion"].transform("max")
    ultimas = df[df["fecha_exportacion"].eq(ultima) | ultima.isna()]
    conflictos = ultimas.groupby(CLAVE_NOTA)[["nota", "nota_maxima"]].nunique(dropna=False)
    if (conflictos > 1).any().any():
        raise ValueError("Hay notas contradictorias para la misma evaluación y fecha de exportación.")
    df = df.drop_duplicates(CLAVE_NOTA, keep="last").reset_index(drop=True)
    if (df["nota_maxima"].isna() | ~np.isfinite(df["nota_maxima"]) | df["nota_maxima"].le(0)).any():
        raise ValueError("Cada instrumento debe tener una nota máxima positiva.")
    if ((df["nota"].notna() & ~np.isfinite(df["nota"])) | df["nota"].lt(0) | df["nota"].gt(df["nota_maxima"])).any():
        raise ValueError("Hay notas fuera de la escala del instrumento.")
    if (df.groupby(["materia", "evaluacion"])["nota_maxima"].nunique() > 1).any():
        raise ValueError("Un instrumento tiene más de una escala de notas.")
    df["nota_pct"] = df["nota"] / df["nota_maxima"] * 100
    return df


def poblacion(datos):
    """Integra matrícula, alumnos del aula y notas, conservando las ausencias."""
    notas = datos["calificaciones"]
    padron = _identificadores(datos["matricula"], CLAVES + ["estado"])
    participacion = _identificadores(datos["participacion"], CLAVES + ["perfil"])
    participacion = participacion.loc[participacion["perfil"].eq("Alumnos")].copy()
    for tabla, nombre in ((padron, "matrícula"), (participacion, "participación")):
        if tabla.duplicated(CLAVES).any():
            raise ValueError(f"Hay más de un registro por estudiante y materia en {nombre}.")
    base = pd.concat([notas[CLAVES], padron[CLAVES], participacion[CLAVES]]).drop_duplicates()
    base = base.merge(padron[CLAVES + ["estado"]], on=CLAVES, how="left", validate="one_to_one")
    columnas = [c for c in ("apellido", "nombre", "interacciones", "tiempo_uso_min", "avance") if c in participacion]
    participacion["tiene_reporte_participacion"] = True
    base = base.merge(participacion[CLAVES + columnas + ["tiene_reporte_participacion"]], on=CLAVES, how="left", validate="one_to_one")
    base["inscripto"] = base["estado"].eq("Aceptada")
    base["tiene_reporte_participacion"] = base["tiene_reporte_participacion"].eq(True)
    for col in ("apellido", "nombre"):
        if col not in base:
            base[col] = ""
        base[col] = base[col].fillna("").astype(str)
    base["estudiante"] = (base["apellido"] + ", " + base["nombre"]).str.strip(", ")
    base["estudiante"] = base["estudiante"].where(base["estudiante"].ne(""), base["usuario"])
    for col in ("interacciones", "tiempo_uso_min", "avance"):
        if col not in base:
            base[col] = np.nan
        base[col] = pd.to_numeric(base[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return base.reset_index(drop=True)


def catalogo_evaluaciones(notas):
    return (
        notas.groupby(["materia", "evaluacion"], as_index=False)
        .agg(nota_maxima=("nota_maxima", "first"), registros=("usuario", "size"),
             con_nota=("nota", "count"), exportacion=("fecha_exportacion", "max"))
        .sort_values(["materia", "evaluacion"])
    )


def resumen_academico(base, notas, reglas, catalogo_completo=None, catalogo_seleccionado=None):
    """Calcula resultados y cobertura; la condición final exige cierre y notas completas."""
    salida = base.copy().set_index(CLAVES)
    agrupadas = notas.groupby(CLAVES)
    salida["instrumentos_con_nota"] = agrupadas["nota"].count()
    salida["promedio_instrumentos_pct"] = agrupadas["nota_pct"].mean()
    salida["resultado_parcial"] = np.nan
    salida["condicion"] = "Sin determinar"
    salida["motivo_condicion"] = "Cursada sin cierre académico confirmado"
    seleccion = catalogo_seleccionado if catalogo_seleccionado is not None else catalogo_evaluaciones(notas)
    salida["instrumentos_seleccionados"] = salida.index.get_level_values("materia").map(seleccion.groupby("materia").size()).fillna(0)
    salida["instrumentos_con_nota"] = salida["instrumentos_con_nota"].fillna(0).astype(int)
    salida["instrumentos_sin_nota"] = salida["instrumentos_seleccionados"] - salida["instrumentos_con_nota"]
    salida["cobertura_notas_pct"] = salida["instrumentos_con_nota"].div(salida["instrumentos_seleccionados"].replace(0, np.nan)) * 100
    completo = catalogo_completo if catalogo_completo is not None else seleccion
    for materia in salida.index.get_level_values("materia").unique():
        mascara = salida.index.get_level_values("materia") == materia
        regla = reglas.get(materia)
        if regla is None:
            salida.loc[mascara, "motivo_condicion"] = "Materia sin regla académica configurada"
            continue
        if regla["calculo"] == "suma":
            resultado = agrupadas["nota"].sum(min_count=1)
        else:
            resultado = agrupadas["nota"].mean()
        salida.loc[mascara, "resultado_parcial"] = resultado.reindex(salida.index[mascara])
        requeridos = set(regla.get("instrumentos_requeridos", []))
        if not regla.get("cierre_confirmado", False) or not requeridos:
            continue
        disponibles = set(completo.loc[completo["materia"].eq(materia), "evaluacion"])
        elegidas = set(seleccion.loc[seleccion["materia"].eq(materia), "evaluacion"])
        catalogo_materia = completo[completo["materia"].eq(materia)]
        cantidad_correcta = len(requeridos) == regla.get("instrumentos_plan", len(requeridos))
        puntos_correctos = "puntos_plan" not in regla or np.isclose(catalogo_materia["nota_maxima"].sum(), regla["puntos_plan"])
        if disponibles != requeridos or elegidas != requeridos or not cantidad_correcta or not puntos_correctos:
            salida.loc[mascara, "motivo_condicion"] = "Instrumentos disponibles o seleccionados no coinciden con el esquema de cierre"
            continue
        completas = mascara & salida["instrumentos_con_nota"].eq(len(requeridos))
        salida.loc[mascara, "motivo_condicion"] = "Faltan notas requeridas; no se imputaron ceros"
        valor = salida.loc[completas, "resultado_parcial"]
        salida.loc[completas, "condicion"] = np.select(
            [valor.ge(regla["promocion_desde"]), valor.ge(regla["regular_desde"])],
            ["Promociona", "Regular"], default="Libre",
        )
        salida.loc[completas, "motivo_condicion"] = "Cierre confirmado y notas requeridas completas"
    salida["semaforo_academico"] = salida["condicion"].map({"Promociona": "Verde", "Regular": "Amarillo", "Libre": "Rojo"})
    return salida.reset_index()


def resumen_instrumentos(notas, cantidad_estudiantes):
    tabla = (
        notas.groupby("evaluacion", as_index=False)
        .agg(con_nota=("nota", "count"), promedio=("nota", "mean"),
             promedio_pct=("nota_pct", "mean"), minima=("nota", "min"),
             maxima=("nota", "max"), nota_maxima=("nota_maxima", "first"))
    )
    tabla["sin_nota"] = cantidad_estudiantes - tabla["con_nota"]
    tabla["cobertura_pct"] = tabla["con_nota"] / cantidad_estudiantes * 100 if cantidad_estudiantes else np.nan
    return tabla


def correlaciones(tabla, x, y):
    """Pearson y Spearman con los mismos pares válidos; sin imputaciones."""
    pares = tabla[[x, y]].replace([np.inf, -np.inf], np.nan).dropna()
    resultado = {"n": len(pares), "pearson": None, "spearman": None}
    if len(pares) >= 3 and pares[x].nunique() > 1 and pares[y].nunique() > 1:
        resultado["pearson"] = float(pares[x].corr(pares[y]))
        resultado["spearman"] = float(pares[x].rank().corr(pares[y].rank()))
    return resultado


def grupos_exploratorios(tabla, x, y, umbral_actividad, umbral_nota):
    """Umbrales descriptivos elegidos en pantalla; no son condiciones académicas."""
    actividad, nota = tabla[x], tabla[y]
    etiquetas = np.select(
        [nota.isna(), actividad.isna(), actividad.le(umbral_actividad) & nota.lt(umbral_nota), nota.lt(umbral_nota)],
        ["Sin resultado", "Sin dato de participación", "Menor actividad y resultado bajo el umbral", "Resultado bajo el umbral"],
        default="Resto de pares observados",
    )
    return pd.Series(etiquetas, index=tabla.index)
