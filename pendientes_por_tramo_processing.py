# -*- coding: utf-8 -*-
"""
GEOPROCESO QGIS (Processing) — Pendientes por tramo
===================================================
Algoritmo para el Processing Toolbox: calcula, para cada tramo entre vértices
consecutivos de una capa de líneas, la longitud, la diferencia de cota tomada
de uno o varios rásters y la pendiente en %.

Cómo instalarlo (aparece un diálogo con todos los parámetros):
  Opción A — Caja de herramientas:
    Processing > Caja de herramientas > icono de scripts (Python) >
    "Añadir script a la caja de herramientas..." > seleccionar este .py
  Opción B — Editor de scripts:
    Processing > Caja de herramientas > icono de scripts > "Crear script nuevo
    desde plantilla", pegar este código, Guardar. Quedará bajo el grupo
    "Geoprocesos personalizados".

Luego: doble clic en el algoritmo -> se abre la ventana de parámetros.

Salida: capa de líneas (un tramo por par de vértices consecutivos) con campos
  id_tramo, [campos origen elegidos], NODO1, NODO2, LONGITUD, DIF_VALOR,
  PENDIENTE, OBS.
"""

import math

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsProcessingParameterField,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingException,
    QgsFeature, QgsFields, QgsField, QgsGeometry, QgsPointXY,
    QgsWkbTypes, QgsCoordinateTransform, QgsDistanceArea, QgsUnitTypes,
)


RESERVED = {"id_tramo", "nodo1", "nodo2", "longitud", "dif_valor", "pendiente", "obs"}


class PendientesPorTramo(QgsProcessingAlgorithm):

    INPUT = "INPUT"
    RASTERS = "RASTERS"
    BAND = "BAND"
    MODE = "MODE"
    KEEP_FIELDS = "KEEP_FIELDS"
    ADD_OBS = "ADD_OBS"
    OUTPUT = "OUTPUT"

    # ----------------------- metadatos ----------------------- #
    def name(self):
        return "pendientes_por_tramo"

    def displayName(self):
        return self.tr("Pendientes por tramo (líneas + ráster)")

    def group(self):
        return self.tr("Geoprocesos personalizados")

    def groupId(self):
        return "geoprocesos_personalizados"

    def createInstance(self):
        return PendientesPorTramo()

    def tr(self, string):
        return QCoreApplication.translate("PendientesPorTramo", string)

    def shortHelpString(self):
        return self.tr(
            "Explota la capa de líneas en tramos (segmentos entre vértices "
            "consecutivos) y, para cada tramo:\n"
            "• NODO1/NODO2: valor del ráster en el vértice inicial y final.\n"
            "• LONGITUD: longitud horizontal en metros (cartesiana si el CRS "
            "es proyectado; geodésica si es geográfico).\n"
            "• DIF_VALOR = |NODO1 − NODO2|.\n"
            "• PENDIENTE = (DIF_VALOR / LONGITUD) × 100.\n\n"
            "Admite varias teselas ráster: si un punto cae sobre varias se "
            "usa la media de los valores válidos (o el primero, según opción). "
            "Si un nodo queda sin dato (fuera de cobertura o NoData), los "
            "valores quedan NULL y se conserva la geometría del tramo; el "
            "campo OBS lo indica.\n\n"
            "El formato de salida se elige en el propio cuadro de salida."
        )

    # ----------------------- parámetros ----------------------- #
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT,
            self.tr("Capa de líneas de entrada"),
            [QgsProcessing.TypeVectorLine],
        ))

        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.RASTERS,
            self.tr("Capa(s) ráster (una o varias teselas)"),
            QgsProcessing.TypeRaster,
        ))

        self.addParameter(QgsProcessingParameterNumber(
            self.BAND,
            self.tr("Banda del ráster"),
            QgsProcessingParameterNumber.Integer,
            defaultValue=1, minValue=1,
        ))

        self.addParameter(QgsProcessingParameterEnum(
            self.MODE,
            self.tr("Valor cuando un punto cae sobre varias teselas"),
            options=[self.tr("Media de válidos"), self.tr("Primer válido")],
            defaultValue=0,
        ))

        self.addParameter(QgsProcessingParameterField(
            self.KEEP_FIELDS,
            self.tr("Campos de la capa origen a conservar (opcional)"),
            parentLayerParameterName=self.INPUT,
            allowMultiple=True,
            optional=True,
        ))

        self.addParameter(QgsProcessingParameterBoolean(
            self.ADD_OBS,
            self.tr("Añadir campo OBS (aviso de nodos sin dato)"),
            defaultValue=True,
        ))

        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT,
            self.tr("Tramos con pendiente"),
            QgsProcessing.TypeVectorLine,
        ))

    # ----------------------- ejecución ----------------------- #
    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.tr("Capa de líneas no válida."))

        rasters = self.parameterAsLayerList(parameters, self.RASTERS, context)
        rasters = [r for r in rasters if r is not None and r.type() == r.RasterLayer] \
            if rasters else []
        if not rasters:
            raise QgsProcessingException(self.tr("Debe aportar al menos un ráster."))

        band = self.parameterAsInt(parameters, self.BAND, context)
        mode = "first" if self.parameterAsEnum(parameters, self.MODE, context) == 1 else "mean"
        keep_names = self.parameterAsFields(parameters, self.KEEP_FIELDS, context) or []
        add_obs = self.parameterAsBool(parameters, self.ADD_OBS, context)

        line_crs = source.sourceCrs()
        tr_ctx = context.transformContext()

        # Transformaciones CRS_líneas -> CRS_ráster (None si coinciden).
        transforms = []
        for r in rasters:
            transforms.append(None if r.crs() == line_crs
                              else QgsCoordinateTransform(line_crs, r.crs(), tr_ctx))

        # Medidor de distancias según el tipo de CRS.
        da = QgsDistanceArea()
        da.setSourceCrs(line_crs, tr_ctx)
        if line_crs.isGeographic():
            da.setEllipsoid(line_crs.ellipsoidAcronym() or "WGS84")
            feedback.pushInfo("CRS geográfico -> longitud GEODÉSICA (m).")
        else:
            da.setEllipsoid("NONE")
            feedback.pushInfo("CRS proyectado -> longitud CARTESIANA (m).")

        # Campos origen a conservar (se omiten los que choquen con reservados).
        src_fields = source.fields()
        kept = []
        for name in keep_names:
            idx = src_fields.indexOf(name)
            if idx < 0:
                continue
            if name.lower() in RESERVED:
                feedback.pushWarning(
                    self.tr("El campo '%s' choca con un campo reservado; se omite.") % name)
                continue
            kept.append((name, src_fields.at(idx)))

        # Estructura de campos de salida.
        out_fields = QgsFields()
        out_fields.append(QgsField("id_tramo", QVariant.Int))
        for name, fdef in kept:
            f = QgsField(fdef)
            f.setName(name)
            out_fields.append(f)
        out_fields.append(QgsField("NODO1", QVariant.Double))
        out_fields.append(QgsField("NODO2", QVariant.Double))
        out_fields.append(QgsField("LONGITUD", QVariant.Double))
        out_fields.append(QgsField("DIF_VALOR", QVariant.Double))
        out_fields.append(QgsField("PENDIENTE", QVariant.Double))
        if add_obs:
            out_fields.append(QgsField("OBS", QVariant.String, len=40))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, QgsWkbTypes.LineString, line_crs,
        )
        if sink is None:
            raise QgsProcessingException(self.tr("No se pudo crear la capa de salida."))

        total = source.featureCount() or 0
        step = 100.0 / total if total else 0
        id_tramo = 0

        for current, feat in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break

            kept_vals = [feat[name] for name, _ in kept]

            for polyline in self._iter_polylines(feat.geometry()):
                for i in range(len(polyline) - 1):
                    p1, p2 = polyline[i], polyline[i + 1]
                    id_tramo += 1

                    v1 = self._sample(p1, rasters, transforms, band, mode)
                    v2 = self._sample(p2, rasters, transforms, band, mode)
                    length = self._length_m(da, p1, p2)

                    dif = abs(v1 - v2) if (v1 is not None and v2 is not None) else None
                    slope = (dif / length) * 100.0 if (dif is not None and length and length > 0) else None

                    if v1 is None and v2 is None:
                        obs = "SIN_DATO_AMBOS"
                    elif v1 is None:
                        obs = "SIN_DATO_NODO1"
                    elif v2 is None:
                        obs = "SIN_DATO_NODO2"
                    elif length == 0:
                        obs = "LONGITUD_CERO"
                    else:
                        obs = ""

                    of = QgsFeature(out_fields)
                    of.setGeometry(QgsGeometry.fromPolylineXY([p1, p2]))
                    attrs = [id_tramo] + kept_vals + [v1, v2, length, dif, slope]
                    if add_obs:
                        attrs.append(obs)
                    of.setAttributes(attrs)
                    sink.addFeature(of)

            if step:
                feedback.setProgress(int((current + 1) * step))

        feedback.pushInfo("Tramos generados: %d" % id_tramo)
        return {self.OUTPUT: dest_id}

    # ----------------------- utilidades ----------------------- #
    @staticmethod
    def _iter_polylines(geom):
        if geom is None or geom.isEmpty():
            return []
        if QgsWkbTypes.isCurvedType(geom.wkbType()):
            try:
                geom = QgsGeometry(geom.constGet().segmentize())
            except Exception:
                pass
        if geom.isMultipart():
            return geom.asMultiPolyline()
        pl = geom.asPolyline()
        return [pl] if pl else []

    @staticmethod
    def _length_m(da, p1, p2):
        raw = da.measureLine(p1, p2)
        factor = QgsUnitTypes.fromUnitToUnitFactor(
            da.lengthUnits(), QgsUnitTypes.DistanceMeters)
        return raw * factor

    @staticmethod
    def _sample(point, rasters, transforms, band, mode):
        values = []
        for r, tr in zip(rasters, transforms):
            pt = point if tr is None else tr.transform(point)
            if not r.extent().contains(pt):
                continue
            val, ok = r.dataProvider().sample(QgsPointXY(pt), band)
            if ok and val is not None and not (isinstance(val, float) and math.isnan(val)):
                if mode == "first":
                    return float(val)
                values.append(float(val))
        if not values:
            return None
        return sum(values) / len(values)
