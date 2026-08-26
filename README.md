# Panel agroclimático de Honduras

Panel municipal de estrés agrícola y condición de la vegetación a partir de
FAO GIEWS ASIS, para Sendas. Reconstruye desde las fuentes primarias de FAO un
panel municipio × dekad, lo versiona en el repositorio y lo sirve en una app que
permite verlo, filtrarlo y descargarlo en CSV.

| | |
|---|---|
| **Fuentes** | ImageServer ASIS (rásteres ~1 km) y CSV oficiales del portal GIEWS |
| **Unidad de análisis** | Municipio (GAUL 2015 nivel 2), 290 municipios |
| **Resolución temporal** | Dekad (tercios de mes) |
| **Periodo** | Desde 2005, gobernado por `START_YEAR` |
| **Series** | ASI primera, ASI postrera, VCI, y el peor caso de las dos temporadas |

## Cómo se usa

### La app

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Tres controles: nivel (municipio, departamento o país), indicador y ventana
(un dekad o un rango). Cada vista trae la descarga en CSV del corte exacto que
está en pantalla.

La app no toca la red ni necesita credenciales: lee el panel ya construido de
`data/`. Por eso abre en segundos y por eso se puede desplegar en cualquier
servicio que corra Streamlit.

### Desplegar la app

Va en Streamlit Community Cloud, que lee el repositorio directamente. En
[share.streamlit.io](https://share.streamlit.io) se conecta el repo con:

| Campo | Valor |
|---|---|
| Branch | `main` |
| Main file path | `streamlit_app.py` |
| Python version | 3.12 |

No hay secretos que configurar: la app no llama a ningún servicio ni necesita
credenciales. Instala `requirements.txt`, que a propósito no incluye rasterio ni
geopandas.

Cada commit de datos dispara un redespliegue, y eso además vacía la caché del
proceso. Si en algún momento la app queda corriendo sin redesplegar, tampoco
sirve datos viejos: la caché está indexada por la fecha de `data/manifest.json`.

### Actualizar los datos

```bash
pip install -r requirements-build.txt
python -m asis.build
```

Sin argumentos, agrega lo que FAO haya publicado desde la última corrida. El
relleno histórico completo es `python -m asis.build --desde 2005-01-D1` y tarda
alrededor de una hora la primera vez, porque descarga unos 2.300 rásteres; todo
queda en `asis_cache/` y las corridas siguientes son rápidas.

Esto ya corre solo: `.github/workflows/actualizar-panel.yml` se ejecuta tres
veces al mes, reconstruye lo nuevo, corre las pruebas y commitea `data/` si algo
cambió. También se puede lanzar a mano desde la pestaña Actions.

### Las pruebas

```bash
pytest tests/ -q
```

No tocan la red: usan el panel y las instantáneas versionadas. La prueba que
importa es `tests/test_validation.py`, que contrasta el agregado propio contra
la serie departamental oficial de FAO. Si falla, algo se rompió en la cadena y
ninguna cifra del panel debería citarse hasta entender qué.

## Cómo está organizado

```
asis/                 el cálculo, una sola vez
  config.py           endpoints, START_YEAR, rangos válidos, registro de series
  calendar.py         aritmética de dekads
  client.py           catálogo, rásteres recortados y CSV oficiales de FAO
  zonal.py            geometrías GAUL y estadística zonal (rasterio, geopandas)
  aggregate.py        municipio -> departamento -> país, ponderado
  panel.py            lectura del panel versionado (lo único que usa la app)
  viz.py              figuras de Plotly, compartidas con los cuadernos
  build.py            construcción incremental
app/                  controles y texto de la app
data/                 versionado: el panel, la geometría y las series oficiales
notebooks/            los cuadernos, que importan el paquete
tests/                pruebas sin red
```

El cálculo vive una sola vez, en `asis/`. La app y los cuadernos lo importan, de
modo que una corrección en la estadística zonal se hace en un solo lugar.

## Qué hay en `data/`

`data/municipal/<serie>/<año>.parquet` es el panel, con el esquema completo de
`zonal_stats`: media, mediana, p10, p90, píxeles válidos, km² y superficie por
umbral de severidad. Solo se guarda el nivel municipal; departamento y país se
derivan al vuelo ponderando por píxeles válidos.

`data/oficial/` trae las series nacionales que publica GIEWS, que son el dato de
FAO y no un agregado propio, más la instantánea fechada de los CSV de los que
salen. `data/geo/` trae la geometría municipal simplificada, para que la app
dibuje mapas sin geopandas.

`data/manifest.json` declara qué series y qué dekads hay, cuándo se construyó y
el resultado de la validación contra FAO.

Los rásteres no se versionan: son unos 2,4 GB y se reconstruyen solos.

## Cómo leerlo sin equivocarse

Estas advertencias también son un panel permanente de la app, porque quien la
usa no va a leer esto.

**Sin dato no es cero.** El ASI existe solo dentro de la ventana de cultivo de su
temporada. Fuera de ella el municipio aparece sin dato, o con el valor congelado
con que cerró la temporada. Tratarlo como cero fabrica una calma que el índice no
afirma. La app avisa explícitamente cuando la ventana seleccionada cae fuera de
temporada, en vez de mostrar un mapa vacío.

**Los agregados se ponderan por área, no por unidades.** Subir de municipio a
departamento o país pondera por píxeles válidos. Promediar municipios sin
ponderar sobreestima los pequeños: en el último dekad la diferencia entre una y
otra cuenta es de más de tres puntos.

**Los percentiles solo existen a nivel municipal.** El p90 de un departamento no
es el promedio de los p90 de sus municipios, así que no se publica.

**Ningún índice de sequía mide una inundación.** El ASI mide déficit hídrico y
por construcción no puede ver un exceso de agua.

**Los límites son GAUL 2015**, que no coinciden en todos los casos con la
división administrativa vigente. Los agregados son comparables entre sí, pero no
son cifras oficiales de ninguna unidad territorial.

**Los índices no miden producción ni pérdida**, sino condición de la vegetación
y déficit hídrico.

## Estado

El panel se construyó y validó contra la serie departamental oficial de FAO:
r = 0,959, error absoluto medio de 0,55 puntos porcentuales y sesgo de
−0,01 pp sobre 12.280 pares departamento-dekad. La cifra vigente queda
registrada en `data/manifest.json`, se muestra en el encabezado de la app y la
comprueba `tests/test_validation.py`.

El registro de decisiones de diseño, con las alternativas que se descartaron y
por qué, se mantiene aparte de este repositorio. Conviene consultarlo antes de
proponer cambios de arquitectura: varias decisiones que parecen arbitrarias
responden a un problema concreto que ya se encontró.

Cualquier salida que se publique con firma de Sendas sin revisión humana
sustantiva debe marcarse como asistida por IA.
