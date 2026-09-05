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

# --- Encabezado --------------------------------------------------------------
# La fuente y la fecha del panel van en dos líneas rotuladas, no en una sola
# separada por un punto medio: "panel al 3a dek ago 2026" no decía si esa fecha
# era la del dato o la de la última corrida.
HEADER_SOURCE = f"**Fuente:** {SOURCE_MD}"
HEADER_UPDATED = "**Actualizado al:** {dekad}"

INTRO = (
    "Esta herramienta de visualización utiliza los datos satelitales "
    "agroclimáticos que publica FAO en su portal de indicadores por país, "
    "dentro del Global Information and Early Warning System (GIEWS). Entrega "
    "el historial a nivel de país, departamento y municipio del Agricultural "
    "Stress Index (ASI), o índice de estrés agrícola; del Vegetation Condition "
    "Index (VCI), o índice de condición de la vegetación; y de la "
    "precipitación.")

# El aviso de dato preliminar es una propiedad permanente de la fuente, no de
# la consulta, así que vive en el encabezado y no en una caja que aparecía y
# desaparecía según el dekad elegido. Dice de quién son las revisiones: son de
# FAO, no correcciones de este panel.
PRELIMINARY_HEADER = (
    "Los últimos tres dekads son datos preliminares: FAO puede revisarlos en "
    "actualizaciones futuras.")

# Rótulo del dekad al que corresponde cada cifra de encabezado. Va rotulado y
# no como fecha suelta: suelta se leía como la fecha de actualización del panel,
# que es otra cosa y ya está arriba.
KPI_DEKAD = "Último dekad disponible: {dekad}"

# --- Definiciones de indicador, junto a las cifras de encabezado -------------
# Se muestran cerca de las métricas principales, no en la pestaña "Cómo leer":
# es lo primero que alguien necesita para interpretar el número que acaba de
# ver. No se duplican en "Cómo leer".
# La primera posición es el nombre con el que se rotula la ficha: el nombre
# completo del indicador, en inglés como lo publica FAO y en español, y no la
# sigla sola. Quien llega al panel por primera vez no tiene por qué saber qué
# es "ASI", y la sigla sola tampoco permite buscarlo en el portal de FAO.
INDICATOR_NAMES = {
    "ASI": "Agricultural Stress Index (ASI) · índice de estrés agrícola",
    "VCI": ("Vegetation Condition Index (VCI) · índice de condición de la "
            "vegetación"),
}
# El nombre en español a secas, para titular las figuras: ahí la sigla va
# aparte y el nombre en inglés no cabe sin comerse el rango de fechas.
INDICATOR_PLAIN = {
    "ASI": "Índice de estrés agrícola",
    "VCI": "Índice de condición de la vegetación",
}
INDICATOR_DEFINITIONS = {
    "ASI": (INDICATOR_NAMES["ASI"],
            "Porcentaje del área de cultivo que estuvo bajo condiciones de "
            "estrés hídrico durante la temporada. La primera y la postrera son "
            "dos índices separados, cada uno medido sobre la máscara de cultivo "
            "de su propia temporada: no se suman ni se promedian entre sí. Cada "
            "uno existe solo dentro de su ventana de cultivo (primera de mayo a "
            "octubre, postrera de septiembre a enero); fuera de ella el índice "
            "queda congelado en el valor con que cerró la temporada y no "
            "describe esa fecha."),
    "VCI": (INDICATOR_NAMES["VCI"],
            "Indica qué tan saludable está la vegetación actualmente en "
            "comparación con su rango histórico para la misma época del año. "
            "Valores altos indican condiciones relativamente favorables; "
            "valores bajos indican mayor estrés de la vegetación. A diferencia "
            "del índice de estrés agrícola, es continuo todo el año: no depende "
            "de una ventana de cultivo."),
}

# Título de la caja desplegable con las definiciones. Van plegadas: son la
# referencia que se consulta una vez, no algo que haga falta leer en cada
# consulta, y desplegadas empujaban las figuras fuera de la primera pantalla.
DEFINITIONS_BOX = "Qué mide cada serie"

# El resumen nacional es un modo de vista, no un indicador: muestra las dos
# temporadas del ASI una al lado de la otra, cada una con su cifra y su mapa de
# calor, más el VCI y la lluvia. Nunca resume las dos temporadas en un número.
OVERVIEW_LABEL = "Resumen nacional (todos los indicadores)"
OVERVIEW_HELP = ("Las dos temporadas del ASI por separado, cada una con su "
                 "cifra y su mapa de calor, más el VCI y la lluvia. Para ver "
                 "un solo indicador, selecciónelo arriba.")

# --- Las dos vistas de una temporada, a nivel país ---------------------------
# Son el mismo dato ordenado de dos maneras, así que los títulos dicen qué
# pregunta responde cada una y no repiten el nombre del indicador, que ya está
# en el encabezado de la sección. Sin eso, dos figuras tituladas casi igual se
# leen como dos indicadores distintos, que es lo que pasaba antes.
# Las dos llevan el mismo título, que nombra el indicador y la ventana: son el
# mismo dato y titularlas distinto las hacía leer como dos indicadores. Lo que
# cambia es la cola del subtítulo, que dice cómo está codificado cada uno, para
# poder referirse a una de las dos sin ambigüedad.
SEASON_TITLE = "{indicador} ({sigla}) · {ventana}"
SEASON_SUBTITLE = (
    "{sigla} nacional por dekad de la temporada {temporada} ({meses}), "
    "ponderado por el área de cultivo de cada municipio · {codificacion}")
SEASON_MATRIX_ENCODING = "una fila por temporada, el valor en la intensidad del color"
SEASON_LINE_ENCODING = "una línea por temporada, el valor en la altura del punto"
OVERVIEW_KPI_NOTE = "Promedios nacionales ponderados por píxeles válidos."

# El VCI no tiene temporada, así que su eje es el año completo y sus líneas son
# años calendario. Misma idea que en las temporadas: superponer en vez de
# encadenar, para poder comparar un ciclo contra otro.
YEAR_LINE_TITLE = "Matriz año × dekad · codificada en posición"
YEAR_LINE_SUBTITLE = (
    "Una línea por año sobre los 36 dekads del calendario; la altura del punto "
    "es el valor del índice, y el año más reciente va destacado")
SEASON_PAIR_NOTE = (
    "Las dos figuras grafican el mismo dato: {indicador}, como promedio "
    "nacional ponderado por píxeles válidos de las estimaciones satelitales por "
    "píxel que publica FAO para Honduras, en {ventana}. La temporada "
    "{temporada} va de {meses}; cada mes se divide en tres periodos "
    "de unos diez días, llamados dekads, y el índice se evalúa en cada uno. "
    "Fuera de esa ventana el índice queda congelado en el valor con que cerró "
    "la temporada, así que no se grafica.")

# Aclaración sobre las alertas de ASI, para no insinuar que son una
# declaratoria oficial de sequía.
ALERT_DISCLAIMER = ("Las alertas reflejan condiciones de estrés/sequía "
                    "agrícola identificadas por FAO GIEWS/ASIS y no "
                    "necesariamente una declaratoria oficial de sequía.")

# --- Avisos que dependen de la selección -------------------------------------
# Quedó uno solo. Los de fuera de temporada y de dato preliminar eran cajas que
# aparecían y desaparecían al mover la ventana, lo que las hacía leer como
# alertas sobre esa selección cuando describían propiedades permanentes: la
# primera, del indicador (vive en INDICATOR_DEFINITIONS); la segunda, de la
# fuente (vive en PRELIMINARY_HEADER).
NO_DATA = ("Sin dato para esta selección. No es un cero: el panel no inventa "
           "filas. Pruebe otra ventana u otro indicador.")

# --- Pestaña "Cómo leer" -----------------------------------------------------
# ASI y VCI ya no tienen ficha aquí: su definición se muestra junto a las
# cifras de encabezado (ver INDICATOR_DEFINITIONS), para no repetirla dos
# veces. El indicador combinado ya no existe: las dos temporadas del ASI se
# muestran siempre por separado.
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
    ("Los dekads más recientes pueden revisarse",
     "FAO sigue completando sus imágenes más nuevas con información que va "
     "llegando, así que los valores de los últimos tres dekads de cada serie "
     "pueden corregirse en una próxima actualización. El panel los acepta "
     "automáticamente y los marca como preliminares. Se observó una revisión "
     "de FAO dos dekads atrás del más nuevo, y de ahí sale la ventana de tres; "
     "más atrás de eso, un cambio detiene la actualización para revisarlo a "
     "mano."),
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
RANGE_HELP = ("Atajos para las ventanas de uso corriente. Mover el deslizador "
              "pasa el atajo a Personalizado.")
SERIES_HELP = {
    "resumen": OVERVIEW_HELP,
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
        "estacionales.",
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


# En el resumen nacional cada indicador es una columna con su propia etiqueta,
# porque las dos temporadas del ASI nunca se colapsan en un solo número. Las
# definiciones se arman desde el registro de series para que una serie nueva no
# aparezca en la tabla sin explicación.
SERIES_COLUMNS = {
    s.label: (f"{s.label}. Promedio nacional ponderado por píxeles válidos, "
              f"en {s.unit.lower()}.")
    for s in cfg.SERIES.values()
}
RAIN_COLUMNS = {
    "lluvia (mm)": "Lluvia observada acumulada en el dekad, en milímetros, "
                   "ponderada por área de cultivo.",
    "lluvia LTA (mm)": "Promedio de largo plazo de la lluvia que publica FAO, "
                       "en milímetros. No se recalcula.",
    "anomalía de lluvia (%)": "Diferencia porcentual entre la lluvia observada "
                              "y su promedio de largo plazo.",
}


def describe_column(name: str) -> str:
    """Definición de una columna, con los umbrales resueltos por patrón."""
    if name in COLUMNS:
        return COLUMNS[name]
    if name in SERIES_COLUMNS:
        return SERIES_COLUMNS[name]
    if name in RAIN_COLUMNS:
        return RAIN_COLUMNS[name]
    for prefijo, plantilla in COLUMN_PATTERNS:
        if name.startswith(prefijo):
            return plantilla.format(v=name[len(prefijo):])
    return ""
