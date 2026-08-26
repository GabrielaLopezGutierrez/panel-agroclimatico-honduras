"""Texto de la app, en un solo lugar.

Las limitaciones son un panel permanente y no un apéndice: quien usa la app no
va a leer el cuaderno, y estas advertencias son la diferencia entre leer bien y
leer mal una cifra.
"""

TITLE = "Panel agroclimático de Honduras"
SUBTITLE = ("Índice de estrés agrícola y condición de la vegetación por "
            "municipio, a partir de FAO GIEWS ASIS.")

HOW_TO_READ_SHORT = (
    "Los indicadores miden condición de la vegetación y déficit hídrico, no "
    "producción ni pérdida de cosecha. Una unidad en blanco no tiene dato, que "
    "no es lo mismo que no tener estrés: **sin dato no es cero.**")

MAP_SUBTITLE = (
    "Clases y colores oficiales de FAO. En blanco, {unidad}s sin dato: fuera de "
    "temporada o sin área de cultivo, que no es lo mismo que sin estrés.")

HOW_TO_READ = (
    "Los indicadores miden **condición de la vegetación y déficit hídrico**, no "
    "producción ni pérdida de cosecha. Un municipio en blanco no tiene dato: "
    "puede estar fuera de la ventana de cultivo o no tener área agrícola. "
    "**Sin dato no es cero.**")

OUT_OF_SEASON = (
    "**Fuera de temporada.** El {serie} solo existe dentro de la ventana de "
    "cultivo de la {temporada} ({ventana}). En el dekad seleccionado "
    "({dekad}) el índice está congelado en el valor con que cerró la "
    "temporada: no describe la situación de esa fecha. Para una lectura "
    "vigente use el VCI, que cubre todo el año, o mueva la ventana dentro de "
    "la temporada.")

PARTIAL_SEASON = (
    "La ventana seleccionada incluye {n} de {total} dekads fuera de la ventana "
    "de cultivo de la {temporada}. En esos dekads el índice está congelado y no "
    "debe leerse como estrés vigente.")

NO_DATA = (
    "No hay dato para la selección. No es un cero: el panel no inventa filas "
    "municipio-dekad. Pruebe otra ventana u otro indicador.")

COUNTRY_MAP = (
    "En el nivel nacional el mapa sería un único valor para todo el país. La "
    "vista útil es la serie de tiempo; para ver el reparto territorial, cambie "
    "el nivel a departamento o municipio.")

DEPARTMENT_MAP = (
    "El mapa usa los límites departamentales, sin las fronteras municipales: "
    "el valor es del departamento entero y dibujar la división interna "
    "insinuaría un detalle que este nivel no tiene. Para el detalle municipal, "
    "cambie el nivel.")

WEIGHTING = (
    "Los agregados departamentales y nacionales ponderan por píxeles válidos "
    "del ráster, no por número de unidades: un municipio con diez veces más "
    "área de cultivo pesa diez veces más. Los percentiles (p10, mediana, p90) "
    "existen solo a nivel municipal, porque el p90 de un departamento no es el "
    "promedio de los p90 de sus municipios.")

LIMITS = [
    ("El ASI solo existe dentro de la ventana de cultivo",
     "Fuera de ella el municipio aparece sin dato o con el valor congelado de "
     "la temporada, nunca en cero. Tratarlo como cero fabrica una calma que el "
     "índice no afirma. El VCI, en cambio, es continuo todo el año."),
    ("La serie histórica arranca en 2005",
     "La serie de lluvia de GIEWS tiene un quiebre de homogeneidad alrededor de "
     "ese año, así que mezclarla con lo anterior introduciría un salto que no es "
     "climático. Eso deja la línea base de percentiles en unos veinte años: "
     "razonable para mediana y cuartiles, débil para caracterizar extremos."),
    ("Los límites son GAUL 2015, no la división administrativa vigente",
     "Los agregados municipales de este panel son comparables entre sí, pero no "
     "son cifras oficiales de ninguna unidad territorial de Honduras."),
    ("Los índices no miden producción ni pérdida",
     "Miden condición de la vegetación y déficit hídrico. El paso de estrés "
     "agroclimático a impacto en cosecha o en seguridad alimentaria requiere "
     "información que no está en este panel."),
    ("Ningún índice de sequía mide una inundación",
     "El ASI mide déficit hídrico y por construcción no puede ver un exceso de "
     "agua. Tras Eta e Iota en noviembre de 2020 el VCI nacional incluso subió: "
     "más agua reverdece el promedio del país. El daño por exceso es local y "
     "hay que buscarlo por municipio."),
    ("Las banderas del ráster no son valores del índice",
     "Los valores 251 a 255 marcan fuera de temporada, sin dato, sin "
     "estacionalidad, sin cultivo y nodata. El enmascarado ocurre en el "
     "servidor, de modo que ninguna bandera entra como valor en la estadística "
     "zonal. Contarlas como dato es el error más común al agregar estos "
     "rásteres."),
]

DOWNLOAD_HELP = (
    "Descarga el corte exacto que está en pantalla, con el nivel, el indicador "
    "y la ventana seleccionados.")

SOURCE_TEMPLATE = (
    "Fuente: FAO GIEWS ASIS. Rásteres de ~1 km agregados a municipio (GAUL "
    "2015), ponderando por píxeles válidos. Panel construido el {construido}. "
    "Último dekad disponible: {ultimo}.")

VALIDATION_TEMPLATE = (
    "Contraste contra la serie departamental oficial de FAO: r={r:.3f} "
    "(R²={r2:.3f}), error absoluto medio {mae:.2f} pp, sesgo {sesgo:+.2f} pp "
    "sobre {pares:,} pares departamento-dekad.")

EMPTY_PANEL = (
    "Este despliegue no trae datos construidos. El panel se genera fuera de "
    "línea y se versiona en el repositorio: corra "
    "`python -m asis.build --desde 2005-01-D1` y versione la carpeta `data/`.")

AI_NOTE = ("Panel construido con asistencia de IA. Las cifras provienen de las "
           "fuentes primarias de FAO GIEWS ASIS; la validación contra el dato "
           "oficial se reporta arriba.")
