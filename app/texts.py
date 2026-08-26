"""Texto de la app, en un solo lugar.

El portal es un tablero: la pantalla la ocupan los datos y los controles, no la
prosa. Todo lo explicativo —cómo leer los indicadores, la ponderación, las
limitaciones, la procedencia y la validación— vive en la pestaña "Cómo leer" y
no repartido por cada vista ni al final de cada scroll.

Lo único que sigue apareciendo fuera de esa pestaña son los avisos que dependen
de la selección: fuera de temporada y sin dato. Esos no son contexto general,
son una advertencia sobre la cifra que se está mirando en ese momento.
"""

TITLE = "Panel agroclimático de Honduras"
HELP_TAB = "Cómo leer"

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
READING = [
    ("Sin dato no es cero",
     "Una unidad en blanco no tiene dato en ese dekad: puede estar fuera de la "
     "ventana de cultivo o no tener área agrícola. Tratarlo como cero fabrica "
     "una calma que el índice no afirma."),
    ("ASI · índice de estrés agrícola",
     "Porcentaje del área de cultivo que estuvo bajo estrés hídrico durante la "
     "temporada, de 0 a 100. Es acumulativo dentro de la temporada y se "
     "reinicia con la siguiente. Mide déficit: por construcción no puede "
     "detectar un exceso de agua."),
    ("VCI · condición de la vegetación",
     "Posición del vigor de la vegetación frente a su propio historial "
     "reciente, de 0 a 1. Cubre todo el territorio y todo el año, también "
     "fuera del área de cultivo. El umbral de alerta de FAO es 0,35."),
    ("El más alto de las dos temporadas",
     "Para cada municipio y cada dekad toma el mayor de los dos valores del "
     "ASI, el de la primera y el de la postrera. No promedia ni mezcla: es uno "
     "de los dos valores reales. Las temporadas se solapan en septiembre y "
     "octubre, y fuera de su ventana el índice queda congelado; tomar el más "
     "alto evita reportar calma cuando una de las dos sí tiene estrés."),
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
    "Fuente: FAO GIEWS ASIS. Rásteres de ~1 km agregados a municipio "
    "(GAUL 2015), ponderando por píxeles válidos. Panel construido el "
    "{construido}. Último dekad disponible: {ultimo}.")

VALIDATION_TEMPLATE = (
    "Contraste contra la serie departamental oficial de FAO: r={r:.3f} "
    "(R²={r2:.3f}), error absoluto medio {mae:.2f} pp, sesgo {sesgo:+.2f} pp "
    "sobre {pares:,} pares departamento-dekad.")

EMPTY_PANEL = (
    "Este despliegue no trae datos construidos. El panel se genera fuera de "
    "línea y se versiona en el repositorio: corra "
    "`python -m asis.build --desde 2005-01-D1` y versione la carpeta `data/`.")

AI_NOTE = ("Panel construido con asistencia de IA. Las cifras provienen de las "
           "fuentes primarias de FAO GIEWS ASIS.")

# --- Ayuda de los controles (tooltips, no texto en pantalla) -----------------
LEVEL_HELP = ("Cambia el mapa y las vistas. Departamento y país se derivan del "
              "panel municipal ponderando por píxeles válidos.")
WINDOW_HELP = "Solo se ofrecen dekads que FAO publicó."
SERIES_HELP = {
    "asi_peor_caso": "El mayor de los dos valores del ASI, primera y postrera, "
                     "para cada municipio y dekad. Ver «Cómo leer».",
    "asi_gs1": "Solo la temporada primera: mayo a octubre.",
    "asi_gs2": "Solo la temporada postrera: septiembre a enero.",
    "vci": "Condición de la vegetación, 0 a 1. Todo el año. Umbral FAO 0,35.",
}
