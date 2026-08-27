"""Texto de la app, en un solo lugar.

El portal es un tablero: la pantalla la ocupan los datos y los controles, no la
prosa. Todo lo explicativo —cómo leer los indicadores, la ponderación, las
limitaciones, la procedencia y la validación— vive en la pestaña "Cómo leer" y
no repartido por cada vista ni al final de cada scroll.

Lo único que sigue apareciendo fuera de esa pestaña son los avisos que dependen
de la selección: fuera de temporada y sin dato. Esos no son contexto general,
son una advertencia sobre la cifra que se está mirando en ese momento.
"""

from asis import config as cfg

TITLE = "Panel agroclimático de Honduras"
HELP_TAB = "Cómo leer"

# Toda cita de la fuente enlaza al portal oficial de FAO GIEWS para Honduras.
# El enlace vive en config.SOURCE_URL, que es de donde lo toman también la nota
# al pie de cada figura y los cuadernos.
SOURCE_MD = f"[{cfg.SOURCE_NAME}]({cfg.SOURCE_URL})"
PORTAL_MD = (f"Portal oficial de FAO GIEWS para Honduras: "
             f"[indicadores por país]({cfg.SOURCE_URL}).")

# --- Definiciones de indicador, junto a las cifras de encabezado -------------
# Se muestran cerca de las métricas principales, no en la pestaña "Cómo leer":
# es lo primero que alguien necesita para interpretar el número que acaba de
# ver. No se duplican en "Cómo leer".
INDICATOR_DEFINITIONS = {
    "ASI": ("ASI", "Porcentaje del área de cultivo que estuvo bajo condiciones "
                   "de estrés hídrico durante la temporada."),
    "VCI": ("VCI", "Indica qué tan saludable está la vegetación actualmente en "
                   "comparación con su rango histórico para la misma época del "
                   "año. Valores altos indican condiciones relativamente "
                   "favorables; valores bajos indican mayor estrés de la "
                   "vegetación."),
}

# Etiqueta del indicador combinado cuando se ofrece a nivel país como la vista
# general por omisión. No se muestra como "ASI - el más alto de las dos
# temporadas": ese nombre y su explicación se retiraron del selector.
OVERVIEW_LABEL = "Resumen nacional (todos los indicadores)"
OVERVIEW_HELP = ("Vista general con el ASI, el VCI y la lluvia sobre el mismo "
                 "eje de tiempo. Para ver un solo indicador, selecciónelo "
                 "arriba.")

# Aclaración sobre las alertas de ASI, para no insinuar que son una
# declaratoria oficial de sequía.
ALERT_DISCLAIMER = ("Las alertas reflejan condiciones de estrés/sequía "
                    "agrícola identificadas por FAO GIEWS/ASIS y no "
                    "necesariamente una declaratoria oficial de sequía.")

# --- Avisos que dependen de la selección -------------------------------------
# Dos redacciones porque el indicador combinado se evalúa contra las dos
# temporadas y una sola plantilla daba "fuera de la temporada primera ni la
# postrera", que no es gramatical.
OUT_OF_SEASON = (
    "**Fuera de temporada.** En {dekad} el índice está congelado en el valor con "
    "que cerró la {temporada} ({ventana}): no describe esa fecha. Use el VCI, que "
    "cubre todo el año, o mueva la ventana dentro de la temporada.")

OUT_OF_SEASON_COMBINED = (
    "**Fuera de temporada.** En {dekad} no hay ninguna temporada activa "
    "({ventana}), así que el índice está congelado en el valor con que cerró la "
    "última: no describe esa fecha. Use el VCI, que cubre todo el año.")

PARTIAL_SEASON = (
    "{n} de {total} dekads de la ventana caen fuera de la temporada "
    "{temporada}. Ahí el índice está congelado.")

PARTIAL_SEASON_COMBINED = (
    "En {n} de {total} dekads de la ventana no hay ninguna temporada activa. "
    "Ahí el índice está congelado.")

NO_DATA = ("Sin dato para esta selección. No es un cero: el panel no inventa "
           "filas. Pruebe otra ventana u otro indicador.")

# --- Pestaña "Cómo leer" -----------------------------------------------------
# ASI y VCI ya no tienen ficha aquí: su definición se muestra junto a las
# cifras de encabezado (ver INDICATOR_DEFINITIONS), para no repetirla dos
# veces. La ficha del indicador combinado tampoco: ese indicador se retiró del
# selector visible.
READING = [
    ("Sin dato no es cero",
     "Una unidad en blanco no tiene dato en ese dekad: puede estar fuera de la "
     "ventana de cultivo o no tener área agrícola. Tratarlo como cero fabrica "
     "una calma que el índice no afirma."),
    ("Alertas de ASI, no declaratoria de sequía",
     ALERT_DISCLAIMER),
    ("Temporadas agrícolas",
     "La primera se siembra entre mayo y junio y se cosecha entre agosto y "
     "septiembre. La postrera se siembra en septiembre y se cosecha entre "
     "diciembre y enero. Fuera de su ventana, el ASI de esa temporada no "
     "describe la fecha que se está mirando."),
    ("Los agregados se ponderan por área",
     "Subir de municipio a departamento o país pondera por píxeles válidos del "
     "ráster, no por número de unidades: un municipio con diez veces más área "
     "de cultivo pesa diez veces más. Promediar sin ponderar cambia la cifra "
     "nacional en más de tres puntos."),
    ("Los percentiles solo existen a nivel municipal",
     "El p90 de un departamento no es el promedio de los p90 de sus "
     "municipios, así que no se publica en los niveles agregados."),
]

LIMITS = [
    ("El ASI solo existe dentro de la ventana de cultivo",
     "Fuera de ella el municipio aparece sin dato o con el valor congelado de "
     "la temporada, nunca en cero. El VCI, en cambio, es continuo todo el año."),
    ("La serie histórica arranca en 2005",
     "La serie de lluvia de GIEWS tiene un quiebre de homogeneidad alrededor de "
     "ese año, así que mezclarla con lo anterior introduciría un salto que no es "
     "climático. Eso deja la línea base de percentiles en unos veinte años: "
     "razonable para mediana y cuartiles, débil para caracterizar extremos."),
    ("Los límites son GAUL 2015, no la división administrativa vigente",
     "Los agregados de este panel son comparables entre sí, pero no son cifras "
     "oficiales de ninguna unidad territorial de Honduras."),
    ("Los índices no miden producción ni pérdida",
     "Miden condición de la vegetación y déficit hídrico. El paso de estrés "
     "agroclimático a impacto en cosecha o en seguridad alimentaria requiere "
     "información que no está en este panel."),
    ("Ningún índice de sequía mide una inundación",
     "Tras Eta e Iota en noviembre de 2020 el VCI nacional incluso subió: más "
     "agua reverdece el promedio del país. El daño por exceso es local y hay "
     "que buscarlo por municipio."),
    ("Las banderas del ráster no son valores del índice",
     "Los valores 251 a 255 marcan fuera de temporada, sin dato, sin "
     "estacionalidad, sin cultivo y nodata. El enmascarado ocurre en el "
     "servidor, de modo que ninguna bandera entra como valor en la estadística "
     "zonal."),
]

# --- Fichas cortas -----------------------------------------------------------
DOWNLOAD_HELP = ("Descarga el corte exacto que está en pantalla: nivel, "
                 "indicador y ventana seleccionados.")

SOURCE_TEMPLATE = (
    f"Fuente: {SOURCE_MD}. Rásteres de ~1 km agregados a municipio "
    "(GAUL 2015), ponderando por píxeles válidos. Panel construido el "
    "{construido}. Último dekad disponible: {ultimo}.")

VALIDATION_TEMPLATE = (
    f"Contraste contra la serie departamental oficial de {SOURCE_MD}: "
    "r={r:.3f} "
    "(R²={r2:.3f}), error absoluto medio {mae:.2f} pp, sesgo {sesgo:+.2f} pp "
    "sobre {pares:,} pares departamento-dekad.")

EMPTY_PANEL = (
    "Este despliegue no trae datos construidos. El panel se genera fuera de "
    "línea y se versiona en el repositorio: corra "
    "`python -m asis.build --desde 2005-01-D1` y versione la carpeta `data/`.")

AI_NOTE = (f"Panel construido con asistencia de IA. Las cifras provienen de "
           f"las fuentes primarias de {SOURCE_MD}.")

# --- Ayuda de los controles (tooltips, no texto en pantalla) -----------------
LEVEL_HELP = ("Cambia el mapa y las vistas. Departamento y país se derivan del "
              "panel municipal ponderando por píxeles válidos.")
WINDOW_HELP = "Solo se ofrecen dekads que FAO publicó."
SERIES_HELP = {
    cfg.ASI_COMBINED: OVERVIEW_HELP,
    "asi_gs1": "Solo la temporada primera: mayo a octubre.",
    "asi_gs2": "Solo la temporada postrera: septiembre a enero.",
    "vci": "Condición de la vegetación, 0 a 1. Todo el año. Umbral FAO 0,35.",
}

# --- Transparencia: descarga por figura y diccionario de columnas ------------
# Todo dato graficado tiene que poder descargarse. La descarga general por nivel
# no alcanzaba: cada figura muestra un corte propio -otra ventana, otro nivel de
# agregacion, otra fuente- y una sola descarga no podia corresponder a todas.
FIG_DOWNLOAD = "Datos de esta figura"

COLUMNS = {
    "código municipio":
        "Código GAUL 2015 nivel 2. Identificador estable del municipio.",
    "municipio": "Nombre del municipio según GAUL 2015.",
    "código departamento": "Código GAUL 2015 nivel 1.",
    "departamento": "Nombre del departamento según GAUL 2015.",
    "dekad":
        "Tercio de mes, en formato YYYY-MM-Dn. D1 son los días 1 a 10, D2 del "
        "11 al 20 y D3 del 21 al fin de mes.",
    "fecha": "Primer día del dekad: 1, 11 o 21.",
    "temporada":
        "GS1 es la primera y GS2 la postrera. Vacío en indicadores que no son "
        "estacionales. En el indicador combinado dice de qué temporada salió el "
        "valor más alto.",
    "píxeles válidos":
        "Píxeles del ráster de ~1 km dentro de la unidad cuyo valor cae en el "
        "rango del indicador. Es el peso con el que se agrega a departamento y "
        "a país, y excluye las banderas 251 a 255.",
    "km2": "Superficie de esos píxeles válidos, a 0,988 km2 por píxel.",
    "media": "Promedio del indicador sobre los píxeles válidos de la unidad.",
    "mediana":
        "Percentil 50 del indicador dentro de la unidad. Solo existe a nivel "
        "municipal.",
    "p10": "Percentil 10 dentro de la unidad. Solo a nivel municipal.",
    "p90": "Percentil 90 dentro de la unidad. Solo a nivel municipal.",
    "municipios": "Municipios con dato que entran en el agregado.",
    "value": "Valor de la serie nacional oficial de GIEWS.",
    "valor": "Valor de la serie nacional oficial de GIEWS.",
    "obs": "Lluvia observada acumulada en el dekad, en milímetros.",
    "lta":
        "Promedio de largo plazo de la lluvia que publica FAO, en milímetros. "
        "No se recalcula: es la referencia oficial de GIEWS.",
    "anom_pct": "Anomalía de la lluvia observada sobre el promedio de largo "
                "plazo, en porcentaje.",
    "dekad_of_year": "Posición del dekad dentro del año, de 1 a 36.",
    "Year": "Año.",
    "weight": "Suma de los pesos usados para ponderar la serie nacional.",
}

# Las columnas de umbral se generan a partir de ASI_THRESHOLDS y VCI_THRESHOLDS,
# asi que se describen por patron y no una por una.
COLUMN_PATTERNS = (
    ("pct_gt", "Porcentaje del área válida de la unidad con el indicador por "
               "encima de {v}."),
    ("km2_gt", "Superficie en km2 con el indicador por encima de {v}."),
    ("pct_lt", "Porcentaje del área válida de la unidad con el indicador por "
               "debajo de {v}."),
    ("km2_lt", "Superficie en km2 con el indicador por debajo de {v}."),
)


def describe_column(name: str) -> str:
    """Definición de una columna, con los umbrales resueltos por patrón."""
    if name in COLUMNS:
        return COLUMNS[name]
    for prefijo, plantilla in COLUMN_PATTERNS:
        if name.startswith(prefijo):
            return plantilla.format(v=name[len(prefijo):])
    return ""
