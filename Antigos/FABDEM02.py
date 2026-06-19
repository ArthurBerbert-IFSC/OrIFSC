import os
import requests
from tqdm import tqdm
from osgeo import gdal, ogr, osr
import zipfile

def nearest_lower_ten(n):
    return n - (n % 10)

class FABDEM:

    @staticmethod
    def CreateURL(lat, lon):
        shortURL = 'https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/'

        # Arredonda para a dezena inferior mais próxima
        lat_lower = nearest_lower_ten(lat)
        lon_lower = nearest_lower_ten(lon)

        if lat_lower < 0:
            lat_str = f'S{abs(lat_lower):02d}'
            lat_upper_str = f'S{abs(lat_lower + 10):02d}'
        else:
            lat_str = f'N{lat_lower:02d}'
            lat_upper_str = f'N{lat_lower + 10:02d}'

        if lon_lower < 0:
            lon_str = f'W{abs(lon_lower):03d}'
            lon_upper_str = f'W{abs(lon_lower + 10):03d}'
        else:
            lon_str = f'E{lon_lower:03d}'
            lon_upper_str = f'E{lon_lower + 10}:03d}'

        URL = f'{shortURL}{lat_str}{lon_str}-{lat_upper_str}{lon_upper_str}_FABDEM_V1-2.zip'
        return URL


def download_raster(URL):
    if os.path.exists('FABDEM.zip'):
        print('File already exists!')
        return

    print('Downloading...')
    response = requests.get(URL, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    block_size = 1024  # 1 Kibibyte

    with open('FABDEM.zip', 'wb') as file, tqdm(
        desc='FABDEM.zip',
        total=total_size,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(block_size):
            file.write(data)
            bar.update(len(data))

    print('Downloaded!')

def extract_raster(zip_file='FABDEM.zip'):
    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
        zip_ref.extractall('.')
        for file in zip_ref.namelist():
            if file.endswith('.tif'):
                return file
    return None

def generate_contours(input_tif, output_shp, interval=10):
    src_ds = gdal.Open(input_tif)
    src_band = src_ds.GetRasterBand(1)
    
    # Configurando o driver para o formato shapefile
    drv = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(output_shp):
        drv.DeleteDataSource(output_shp)
    dst_ds = drv.CreateDataSource(output_shp)
    
    dst_layer = dst_ds.CreateLayer('contour', srs=None, geom_type=ogr.wkbLineString)
    
    # Cria um campo para armazenar os valores de elevação
    field_defn = ogr.FieldDefn("ID", ogr.OFTInteger)
    dst_layer.CreateField(field_defn)
    
    gdal.ContourGenerate(src_band, interval, 0, [], 0, 0, dst_layer, 0, 1)
    
    src_ds = None
    dst_ds = None
    print(f'Curvas de nível geradas e salvas em {output_shp}.')

def reproject_to_sirgas2000(input_shp, output_shp):
    drv = ogr.GetDriverByName("ESRI Shapefile")
    src_ds = drv.Open(input_shp, 0)
    src_layer = src_ds.GetLayer()
    
    # Define o sistema de coordenadas SIRGAS 2000 (EPSG:4674)
    sirgas2000 = osr.SpatialReference()
    sirgas2000.ImportFromEPSG(4674)
    
    dst_ds = drv.CreateDataSource(output_shp)
    dst_layer = dst_ds.CreateLayer("reprojected", geom_type=ogr.wkbLineString, srs=sirgas2000)
    
    for i in range(src_layer.GetLayerDefn().GetFieldCount()):
        field_defn = src_layer.GetLayerDefn().GetFieldDefn(i)
        dst_layer.CreateField(field_defn)
    
    coord_trans = osr.CoordinateTransformation(src_layer.GetSpatialRef(), sirgas2000)
    
    for feature in src_layer:
        geom = feature.GetGeometryRef()
        geom.Transform(coord_trans)
        new_feature = ogr.Feature(dst_layer.GetLayerDefn())
        new_feature.SetGeometry(geom)
        for i in range(feature.GetFieldCount()):
            new_feature.SetField(i, feature.GetField(i))
        dst_layer.CreateFeature(new_feature)
        new_feature = None
    
    src_ds = None
    dst_ds = None
    print(f'Shapefile reprojectado para SIRGAS 2000 e salvo em {output_shp}.')

# Teste

# Definir coordenadas e URL
lat, lon = -27, -48
URL_Raster = FABDEM.CreateURL(lat, lon)

# Baixar e extrair o raster
download_raster(URL_Raster)
input_tif = extract_raster()

# Gerar curvas de nível
output_shp = 'contours.shp'
generate_contours(input_tif, output_shp, interval=10)

# Reprojetar para SIRGAS 2000
reprojected_shp = 'contours_sirgas2000.shp'
reproject_to_sirgas2000(output_shp, reprojected_shp)