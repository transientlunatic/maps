from qgis.core import (
    Qgis,
    QgsProject,
    QgsPathResolver,
    QgsVectorLayer
)


from qgis.gui import (
    QgsLayerTreeMapCanvasBridge,
)



project = QgsProject.instance()


trig_file = "../sources/trigs.csv"
vlayer = QgsVectorLayer(trig_file, "Trig Points", "delimitedtext")
project.addMapLayer(vlayer)


project.write("../projects/trigs.qgz")
