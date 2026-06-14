# Cálculo de pendientes por tramo — Geoproceso QGIS

**Calcula longitud, diferencia de cota y pendiente (%) para cada tramo de una red de líneas, muestreando uno o varios rásters.**

![QGIS 3.20+](https://img.shields.io/badge/QGIS-3.20%2B-green)
![Python](https://img.shields.io/badge/Python-3-blue)
![Licencia](https://img.shields.io/badge/licencia-MIT-green)

---

## El problema: calcular pendientes tramo a tramo no es trivial

Una red de líneas (cauces, viario, tuberías, vías pecuarias…) está formada por muchos vértices. Conocer la pendiente real de la red exige calcular, para
**cada par de vértices consecutivos**, la diferencia de cota y la distancia entre ellos, no la pendiente media de toda la línea, sino la de cada tramo
individual.

QGIS no ofrece esto de serie. La alternativa manual sería:

1. Explotar cada línea en segmentos de dos vértices.
2. Para cada vértice, extraer el valor del MDT con *Muestrear valores raster*.
3. Calcular longitud, diferencia de cota y pendiente con la calculadora de campos.
4. Repetir para cada tesela si el MDT está troceado, y gestionar a mano los puntos que caen fuera de cobertura o sobre NoData.

Para una red con miles de tramos y un MDT dividido en varias teselas, este proceso es lento y propenso a errores (sobre todo en los nodos sin dato, que suelen romper los cálculos posteriores). Este geoproceso automatiza los 4 pasos en una sola pasada sobre toda la capa.

---

## Características

- **Explosión automática en tramos**: cada segmento entre dos vértices consecutivos se convierte en una entidad independiente con su propio `id_tramo`.
- **Soporte multi-ráster**: admite varias teselas a la vez. Si un punto cae sobre varias, se usa la **media de los valores válidos** o el **primer
  válido**, según se elija.
- **Longitud según el tipo de CRS**: distancia cartesiana en metros si el CRS es proyectado, o distancia geodésica (elipsoidal) si es geográfico (grados).
- **Gestión de nodos sin dato** — si un vértice cae fuera de cobertura o sobre NoData, el valor queda `NULL` pero **se conserva la geometría** del tramo; el  campo `OBS` señala el caso (`SIN_DATO_NODO1`, `SIN_DATO_NODO2`, `SIN_DATO_AMBOS`, `LONGITUD_CERO`).
- **Reproyección automática**: si la capa de líneas y los rásters están en CRS distintos, los puntos se reproyectan antes de muestrear.
- **Cualquier formato OGR de entrada**: GeoPackage, Shapefile, GeoJSON, GML…
- **Geometrías curvas**: los arcos (p. ej. en GML) se segmentizan automáticamente antes de explotar en tramos.
- **Conserva campos de origen**: selección opcional de qué campos de la capa de entrada se trasladan a la salida.
- **Dos formas de uso**: como algoritmo del Processing Toolbox (con ventana de parámetros) o como script de la Consola de Python (parámetros en código).

> **Nota:** la pendiente es una aproximación 2D: se calcula como `(diferencia de cota / longitud planimétrica del tramo) × 100`, no como distancia 3D real sobre el terreno.

---

## Instalación

Requisitos: **QGIS 3.20 o superior** (cualquier versión LTR reciente lo cumple). Sin dependencias externas adicionales.

### Opción A — Algoritmo del Processing Toolbox (recomendado)

1. Abre QGIS.
2. Menú **Procesos → Caja de herramientas**.
3. En la barra de la caja de herramientas, pulsa el icono de scripts de Python.
4. Elige **«Añadir script a la caja de herramientas…»** y selecciona `pendientes_por_tramo_processing.py`.
5. El algoritmo aparece en el grupo **Geoprocesos personalizados** con el nombre **«Pendientes por tramo (líneas + ráster)»**.

### Opción B — Script de Consola de Python

1. Abre QGIS → **Complementos → Consola de Python**.
2. Abre `pendientes_por_tramo.py` en el editor de la consola (icono *Mostrar editor*) o pégalo directamente.
3. Edita el bloque `CONFIGURACIÓN` al principio del archivo (ver tabla en [Uso](#uso)).
4. Ejecuta el script.

---

## Uso

### Opción A — Processing Toolbox

| Paso | Qué hace |
|------|----------|
| **1 — Abrir el algoritmo** | Doble clic en **«Pendientes por tramo (líneas + ráster)»** dentro de *Geoprocesos personalizados*. |
| **2 — Capa de líneas** | Selecciona la capa de entrada (cualquier formato OGR vectorial de líneas). |
| **3 — Capa(s) ráster** | Selector múltiple: marca todas las teselas del MDT necesarias. |
| **4 — Banda y modo** | Indica la banda a muestrear (por defecto `1`) y elige *Media de válidos* o *Primer válido* para los solapes entre teselas. |
| **5 — Campos a conservar** | Selección opcional de campos de la capa origen que se trasladan a la salida. |
| **6 — Campo OBS** | Activado por defecto; añade el aviso de nodos sin dato. |
| **7 — Ejecutar** | Elige archivo y formato de salida (GeoPackage, Shapefile, GeoJSON, GML, capa temporal…) y pulsa **Ejecutar**. Progreso y avisos en el panel de Processing. |

### Opción B — Script de consola

Edita estas variables en el bloque `CONFIGURACIÓN` antes de ejecutar:

| Variable | Descripción |
|---|---|
| `LINE_PATH` | Ruta de la capa de líneas de entrada. |
| `RASTER_PATHS` | Lista de rutas de los rásters (una o varias teselas). |
| `BAND` | Banda a muestrear (por defecto `1`). |
| `OUTPUT_PATH` | Ruta de salida; la extensión determina el formato si `OUTPUT_DRIVER` es `None`. |
| `OUTPUT_DRIVER` | `None` para autodetectar, o forzar (`"GPKG"`, `"ESRI Shapefile"`, `"GeoJSON"`, `"GML"`…). |
| `KEEP_FIELDS` | `[]` ninguno, `"*"` todos, o lista de nombres de campos origen a conservar. |
| `MULTI_RASTER_MODE` | `"mean"` (media de válidos) o `"first"`. |
| `ADD_OBS_FIELD` | `True` para añadir el campo `OBS`. |
| `LOAD_RESULT` | `True` para cargar la capa resultante en el proyecto. |

---

## Campos de salida

| Campo | Tipo | Descripción |
|---|---|---|
| `id_tramo` | int | Identificador secuencial del tramo. |
| *(campos origen)* | — | Campos de la capa de entrada seleccionados en `KEEP_FIELDS` / paso 5. |
| `NODO1` | double | Valor del ráster en el vértice inicial del tramo. |
| `NODO2` | double | Valor del ráster en el vértice final del tramo. |
| `LONGITUD` | double | Longitud horizontal del tramo en metros (cartesiana o geodésica según el CRS). |
| `DIF_VALOR` | double | `\|NODO1 − NODO2\|`. |
| `PENDIENTE` | double | `(DIF_VALOR / LONGITUD) × 100`. |
| `OBS` | string | Aviso si algún nodo queda sin dato o la longitud es cero. Vacío si todo es correcto. |

---

## Arquitectura (algoritmo Processing)

```
pendientes_por_tramo_processing.py
└── PendientesPorTramo (QgsProcessingAlgorithm)
    ├── initAlgorithm()      # Declara los parámetros de la ventana
    ├── processAlgorithm()   # Bucle principal: explota líneas en tramos,
    │                         # muestrea rásters y escribe la capa de salida
    ├── _iter_polylines()     # Segmentiza geometrías curvas y devuelve
    │                         # las polilíneas (simples o multiparte)
    ├── _length_m()           # Longitud en metros vía QgsDistanceArea
    │                         # (cartesiana o geodésica según el CRS)
    └── _sample()             # Muestrea el valor de una o varias teselas
                              # ráster en un punto, según MULTI_RASTER_MODE
```

| Componente | Descripción |
|---|---|
| `initAlgorithm()` | Define los parámetros de entrada: capa de líneas, lista de rásters, banda, modo multi-ráster, campos a conservar, campo OBS y capa de salida. |
| `processAlgorithm()` | Itera sobre las entidades de entrada, explota cada geometría en tramos, calcula `NODO1`/`NODO2`/`LONGITUD`/`DIF_VALOR`/`PENDIENTE`/`OBS` y escribe cada tramo en el *sink* de salida. |
| `_iter_polylines(geom)` | Segmentiza geometrías curvas y normaliza simples/multiparte a una lista de polilíneas de vértices. |
| `_length_m(da, p1, p2)` | Calcula la distancia entre dos puntos en metros, usando `QgsDistanceArea` configurado como cartesiano o geodésico según el CRS de la capa de líneas. |
| `_sample(point, rasters, transforms, band, mode)` | Reproyecta el punto al CRS de cada ráster si es necesario, muestrea la banda indicada y combina los valores de varias teselas según `mode` (`"mean"` / `"first"`). |

---

## Notas

- Asegúrate de que el ráster (MDT) expresa la cota en metros y la capa permite medir longitudes en metros, para que `PENDIENTE` sea coherente.
- Se asume que todas las teselas ráster comparten la misma estructura de bandas (lo habitual en un MDT troceado).

---

## Licencia

MIT — José Carlos Rico · [CITYLAB360, S.C.A.](https://citylab360.es)

## Autor / Contacto

**José Carlos Rico**
CITYLAB360, S.C.A. · [citylab360.es](https://citylab360.es)

¿Errores o sugerencias? Abre un [issue](../../issues).
