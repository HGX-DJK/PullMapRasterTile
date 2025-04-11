import math
import os
import requests
import time
from concurrent.futures import ThreadPoolExecutor

class RegionalAMapDownloader:
    def __init__(self, config):
        self.config = config
        self.downloaded = 0

    def _latlon_to_tile(self, lat, lon, zoom):
        """将经纬度转换为瓦片坐标（高德使用Web墨卡托投影）"""
        lat_rad = math.radians(lat)
        n = 2**zoom
        x = (lon + 180.0) / 360.0 * n
        y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
        return int(x), int(y)

    def _get_tile_range(self, zoom):
        """计算指定层级的瓦片范围"""
        # 上海市地理边界（WGS84坐标）
        bounds = {
            'min_lon': 120.85,
            'max_lon': 122.20,
            'min_lat': 30.67,
            'max_lat': 31.88
        }
        
        # 计算四个角的瓦片坐标
        x1, y1 = self._latlon_to_tile(bounds['max_lat'], bounds['min_lon'], zoom)
        x2, y2 = self._latlon_to_tile(bounds['min_lat'], bounds['max_lon'], zoom)
        
        # 确定有效范围
        max_tile = 2**zoom - 1
        x_min = max(0, min(x1, x2) - 1)  # 向西扩展1个瓦片
        x_max = min(max_tile, max(x1, x2) + 1)  # 向东扩展1个瓦片
        y_min = max(0, min(y1, y2) - 1)  # 向南扩展1个瓦片
        y_max = min(max_tile, max(y1, y2) + 1)  # 向北扩展1个瓦片
        
        return (x_min, x_max, y_min, y_max)

    def generate_coordinates(self):
        """生成区域内的瓦片坐标"""
        for z in range(self.config['z_start'], self.config['z_end'] + 1):
            x_min, x_max, y_min, y_max = self._get_tile_range(z)
            print(f'层级 {z}: X[{x_min}-{x_max}] Y[{y_min}-{y_max}] 约{(x_max-x_min+1)*(y_max-y_min+1)}个瓦片')
            
            for x in range(x_min, x_max + 1):
                for y in range(y_min, y_max + 1):
                    yield (z, x, y)

    def download_tile(self, z, x, y):
        """下载单个瓦片"""
        url = f"https://webrd04.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}"
        path = os.path.join(self.config['save_dir'], f'{z}/{x}/{y}.png')

        if not self.config['overwrite'] and os.path.exists(path):
            return False

        os.makedirs(os.path.dirname(path), exist_ok=True)

        for retry in range(3):
            try:
                response = requests.get(url, headers=self.config['headers'], timeout=5)
                if response.status_code == 200:
                    with open(path, 'wb') as f:
                        f.write(response.content)
                    self.downloaded += 1
                    return True
                time.sleep(1)
            except Exception as e:
                print(f"下载失败 ({z},{x},{y}): {str(e)}")
                time.sleep(2**retry)
        return False

    def run(self):
        """启动下载任务"""
        total = sum(1 for _ in self.generate_coordinates())
        print(f'需要下载的瓦片总数: {total}')
        
        with ThreadPoolExecutor(max_workers=self.config['max_workers']) as executor:
            futures = []
            start_time = time.time()
            
            for z, x, y in self.generate_coordinates():
                future = executor.submit(self.download_tile, z, x, y)
                futures.append(future)
                time.sleep(self.config['request_interval'])
            
            # 显示进度
            success = 0
            for i, future in enumerate(futures):
                if future.result():
                    success += 1
                if i % 100 == 0:
                    elapsed = time.time() - start_time
                    print(f'进度: {i+1}/{total} | 成功率: {success/(i+1):.1%} | 速度: {i/elapsed:.1f}tile/s')

if __name__ == '__main__':
    config = {
        'z_start': 13,        # 起始层级
        'z_end': 13,          # 结束层级（上海城区建议14级）
        'save_dir': './shanghai_tiles',
        'max_workers': 6,     # 并发线程数
        'request_interval': 0.2,  # 请求间隔（秒）
        'overwrite': False,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://www.amap.com/'
        }
    }

    downloader = RegionalAMapDownloader(config)
    downloader.run()