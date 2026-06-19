import os
import requests
from tqdm import tqdm

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
            lon_upper_str = f'E{lon_lower + 10:03d}'

        URL = f'{shortURL}{lat_str}{lon_str}-{lat_upper_str}{lon_upper_str}_FABDEM_V1-2.zip'

        print(URL)
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

# Abrir o arquivo zip e extrair o arquivo .tif da laltitude e longitude 
# mais próxima do ponto de interesse
# S027W049_FABDEM_V1-2.tif
# S027W050_FABDEM_V1-2.tif
# S028W050_FABDEM_V1-2.tif
def extract_raster():
    


# Teste

# -27.5840,-48.6861
URL_Raster = FABDEM.CreateURL(-27, -48)
download_raster(URL_Raster)
