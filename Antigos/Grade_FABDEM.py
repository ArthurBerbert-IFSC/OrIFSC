from qgis.core import QgsVectorLayer, QgsProject, QgsVectorLayerSimpleLabeling, Qgis
from qgis.gui import QgsMessageBar
from qgis.utils import iface
from PyQt5.QtGui import QFont
import json
import requests

def apply_symbology_and_labels(layer):
    label_settings = QgsPalLayerSettings()
    text_format = QgsTextFormat()
    # Configurações de rótulo (exemplo)
    text_format.setFont(QFont("Arial", 10))
    text_format.setSize(10)
    label_settings.setFormat(text_format)

    labeling = QgsVectorLayerSimpleLabeling(label_settings)
    layer.setLabelsEnabled(True)
    layer.setLabeling(labeling)
    layer.triggerRepaint()

def download_geojson(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        iface.messageBar().pushMessage("Erro", f"Falha no download do GeoJSON: {e}", level=Qgis.Critical, duration=3)
        return None

def download_zip(url, output_path):
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(output_path, 'wb') as f:
            f.write(response.content)
        iface.messageBar().pushMessage("Sucesso", "Arquivo ZIP baixado com sucesso!", level=Qgis.Success, duration=3)
    except requests.exceptions.RequestException as e:
        iface.messageBar().pushMessage("Erro", f"Falha no download do arquivo ZIP: {e}", level=Qgis.Critical, duration=3)

def on_feature_selected(layer, selected_features):
    if selected_features:
        feature = selected_features[0]
        zip_url = feature['zip_url']  # Substitua 'zip_url' pelo nome do atributo que contém o link para o arquivo ZIP
        output_path = '/caminho/para/salvar/o/arquivo.zip'  # Substitua pelo caminho onde deseja salvar o arquivo ZIP
        download_zip(zip_url, output_path)

def load_geojson(url):
    geojson_data = download_geojson(url)
    if geojson_data:
        # Criar uma camada a partir dos dados GeoJSON
        layer = QgsVectorLayer(json.dumps(geojson_data), "Grade FABDEM", "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)  # Adiciona a camada ao projeto QGIS
            apply_symbology_and_labels(layer)  # Aplica a simbologia e os rótulos
            iface.messageBar().pushMessage("Sucesso", "GeoJSON carregado com sucesso!", level=Qgis.Success, duration=3)
            
            # Conectar o sinal de seleção de feição
            layer.selectionChanged.connect(lambda: on_feature_selected(layer, layer.selectedFeatures()))
        else:
            iface.messageBar().pushMessage("Erro", "Não foi possível carregar a camada!", level=Qgis.Critical, duration=3)
    else:
        iface.messageBar().pushMessage("Erro", "Falha no download do GeoJSON!", level=Qgis.Critical, duration=3)

# URL do GeoJSON fixo
geojson_url = 'https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/FABDEM_v1-2_tiles.geojson'
load_geojson(geojson_url)

print("Fim do script")

