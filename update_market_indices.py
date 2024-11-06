import yfinance as yf
from datetime import datetime, timezone, timedelta
import csv
import os
import pandas as pd
import plotly.graph_objects as go
import plotly.utils
import json
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client
import sys
from dotenv import load_dotenv

# 首先打印当前工作目录
print(f"当前工作目录: {os.getcwd()}")
print(f".env 文件是否存在: {os.path.exists('.env')}")

# 加载 .env 文件
load_dotenv(verbose=True)  # 添加 verbose=True 来查看加载过程

# 添加初始投资日期配置
INITIAL_INVESTMENT_DATE = datetime(2024, 11, 5, 19, 0, 0, tzinfo=timezone(timedelta(hours=8)))  # 北京时间 2024-03-11 19:00:00
INITIAL_ASSET_VALUE = 40  # 每个子资产初始价值40元

# 添加初始点数配置
INITIAL_INDICES = {
    '纳斯达克综合指数': 18439.17,
    '标普500指数': 5782.76,
    '沪深300指数': 4084.18,
    '中证海外中国互联网50': 7893.96,
    '比特币(USD)': 71990.44
}

def save_to_csv(data, filename):
    """保存数据到CSV文件"""
    file_exists = os.path.isfile(filename)
    
    with open(filename, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # 如果文件不存在，写入表头和初始投资数据
        if not file_exists:
            writer.writerow(['时间', '资产名称', '当前指数', '涨跌幅', '当前价格'])
            
            # 写入初始投资数据
            initial_time = INITIAL_INVESTMENT_DATE.strftime('%Y-%m-%d %H:%M:%S')
            initial_data = [
                [initial_time, '总资产', '1.00', '0.00%', '200.00'],
                [initial_time, '纳斯达克综合指数', str(INITIAL_INDICES['纳斯达克综合指数']), '0.00%', '40.00'],
                [initial_time, '标普500指数', str(INITIAL_INDICES['标普500指数']), '0.00%', '40.00'],
                [initial_time, '沪深300指数', str(INITIAL_INDICES['沪深300指数']), '0.00%', '40.00'],
                [initial_time, '中证海外中国互联网50', str(INITIAL_INDICES['中证海外中国互联网50']), '0.00%', '40.00'],
                [initial_time, '比特币(USD)', str(INITIAL_INDICES['比特币(USD)']), '0.00%', '40.00']
            ]
            for row in initial_data:
                writer.writerow(row)
        
        # 写入当前数据
        for row in data:
            writer.writerow(row)

def calculate_asset_value(index_name, current_price):
    """计算单个子资产的当前价值"""
    initial_price = INITIAL_INDICES[index_name]
    return INITIAL_ASSET_VALUE * (current_price / initial_price)

def create_market_indices_chart(filename):
    """创建市场指数图表"""
    # 读取CSV文件
    df = pd.read_csv(filename)
    
    # 将时间列转换为datetime类型
    df['时间'] = pd.to_datetime(df['时间'])
    
    # 获取唯一的资产名称
    indices = df['资产名称'].unique()
    
    # 创建图表
    fig = go.Figure()
    
    for index_name in indices:
        index_data = df[df['资产名称'] == index_name]
        
        # 为总资产设置特殊样式
        if index_name == '总资产':
            line_width = 3
            opacity = 1
            line_color = '#000080'  # 深蓝色
        else:
            line_width = 2
            opacity = 0.6
            line_color = None
        
        # 修改这里：直接使用当前指数的数值
        fig.add_trace(go.Scatter(
            x=index_data['时间'],
            y=pd.to_numeric(index_data.iloc[:, 4]),  # 使用第5列数据
            name=index_name,
            mode='lines+markers',
            line=dict(width=line_width, color=line_color),
            opacity=opacity,
            hovertemplate="<b>%{fullData.name}</b><br>" +
                         "资产价值: %{y:,.2f}<br>" +
                         "资产指数: %{customdata[0]:,.2f}<br><extra></extra>",
            customdata=[[float(val)] for val in index_data['当前指数']]  # 直接转换为float
        ))
    
    fig.update_layout(
        title='市场指数资产价值走势',
        xaxis_title='时间',
        yaxis_title='资产价值',
        template='plotly_white',
        hovermode='x unified'
    )
    
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

def generate_html(csv_filename):
    """生成HTML文件"""
    # 生成图表数据
    graph_json = create_market_indices_chart(csv_filename)
    
    # 读取模板文件
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        template = f.read()
    
    # 替换模板中的变量
    html_content = template.replace('{{graphJSON | safe}}', graph_json)
    
    # 将生成的HTML内容写入文件
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

def check_cos_config():
    """检查腾讯云 COS 配置是否完整"""
    required_configs = {
        'TENCENT_SECRET_ID': os.environ.get('TENCENT_SECRET_ID'),
        'TENCENT_SECRET_KEY': os.environ.get('TENCENT_SECRET_KEY'),
        'TENCENT_COS_REGION': os.environ.get('TENCENT_COS_REGION'),
        'TENCENT_COS_BUCKET': os.environ.get('TENCENT_COS_BUCKET')
    }
    
    missing_configs = [key for key, value in required_configs.items() if not value]
    
    if missing_configs:
        print(f"腾讯云配置不完整，缺少以下配置: {', '.join(missing_configs)}")
        return False
    return True

def upload_to_cos(local_file, cos_file):
    """上传文件到腾讯云 COS"""
    if not check_cos_config():
        print(f"跳过上传文件 {local_file} 到 COS")
        return False
        
    try:
        # 获取环境变量中的配置信息
        secret_id = os.environ.get('TENCENT_SECRET_ID')
        secret_key = os.environ.get('TENCENT_SECRET_KEY')
        region = os.environ.get('TENCENT_COS_REGION')
        bucket = os.environ.get('TENCENT_COS_BUCKET')
        
        if not all([secret_id, secret_key, region, bucket]):
            print("未找到完整的腾讯云配置")
            return False
            
        config = CosConfig(
            Region=region,
            SecretId=secret_id,
            SecretKey=secret_key
        )
        
        client = CosS3Client(config)
        
        # 上传文件
        response = client.upload_file(
            Bucket=bucket,
            LocalFilePath=local_file,
            Key=cos_file
        )
        
        print(f"文件 {local_file} 已成功上传到 COS: {cos_file}")
        return True
        
    except Exception as e:
        print(f"上传到 COS 时发生错误: {str(e)}")
        return False

def download_from_cos(cos_file, local_file):
    """从腾讯云 COS 下载文件"""
    if not check_cos_config():
        print(f"跳过从 COS 下载文件 {cos_file}")
        return False
        
    try:
        # 获取环境变量中的配置信
        secret_id = os.environ.get('TENCENT_SECRET_ID')
        secret_key = os.environ.get('TENCENT_SECRET_KEY')
        region = os.environ.get('TENCENT_COS_REGION')
        bucket = os.environ.get('TENCENT_COS_BUCKET')
        
        if not all([secret_id, secret_key, region, bucket]):
            print("未找到完整的腾讯云配置")
            return False
            
        config = CosConfig(
            Region=region,
            SecretId=secret_id,
            SecretKey=secret_key
        )
        
        client = CosS3Client(config)
        
        # 检查文件是否存在
        try:
            client.head_object(
                Bucket=bucket,
                Key=cos_file
            )
        except:
            print(f"COS中不存在文件 {cos_file}")
            return True
        
        # 下载文件，修改参数名称为 DestFilePath
        response = client.download_file(
            Bucket=bucket,
            Key=cos_file,
            DestFilePath=local_file  # 修改这里：LocalFilePath -> DestFilePath
        )
        
        print(f"已从 COS 成功下载文件: {cos_file} 到 {local_file}")
        return True
        
    except Exception as e:
        print(f"从 COS 下载时发生错误: {str(e)}")
        return False

def get_market_indices():
    # 获取各个指数的股票代码
    nasdaq = yf.Ticker("^IXIC")
    sp500 = yf.Ticker("^GSPC")
    hs300 = yf.Ticker("000300.SS")
    china_internet = yf.Ticker("H30533.SS")
    bitcoin = yf.Ticker("BTC-USD")
    
    try:
        # 获取实时数据
        nasdaq_data = nasdaq.history(period='1d')
        sp500_data = sp500.history(period='1d')
        hs300_data = hs300.history(period='1d')
        china_internet_data = china_internet.history(period='1d')
        bitcoin_data = bitcoin.history(period='1d')
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 准备数据
        market_data = []
        total_current_assets = 0
        INITIAL_TOTAL_ASSETS = 200  # 总资产初始价格
        
        # 纳斯达克数据
        nasdaq_price = nasdaq_data['Close'].iloc[-1]
        nasdaq_open = nasdaq_data['Open'].iloc[0]
        nasdaq_change = ((nasdaq_price - nasdaq_open) / nasdaq_open) * 100
        nasdaq_asset_value = calculate_asset_value('纳斯达克综合指数', nasdaq_price)
        total_current_assets += nasdaq_asset_value
        market_data.append([current_time, '纳斯达克综合指数', f'{nasdaq_price:.2f}', f'{nasdaq_change:.2f}%', f'{nasdaq_asset_value:.2f}'])

        # 标普500数据
        sp500_price = sp500_data['Close'].iloc[-1]
        sp500_open = sp500_data['Open'].iloc[0]
        sp500_change = ((sp500_price - sp500_open) / sp500_open) * 100
        sp500_asset_value = calculate_asset_value('标普500指数', sp500_price)
        total_current_assets += sp500_asset_value
        market_data.append([current_time, '标普500指数', f'{sp500_price:.2f}', f'{sp500_change:.2f}%', f'{sp500_asset_value:.2f}'])

        # 沪深300数据
        hs300_price = hs300_data['Close'].iloc[-1]
        hs300_open = hs300_data['Open'].iloc[0]
        hs300_change = ((hs300_price - hs300_open) / hs300_open) * 100
        hs300_asset_value = calculate_asset_value('沪深300指数', hs300_price)
        total_current_assets += hs300_asset_value
        market_data.append([current_time, '沪深300指数', f'{hs300_price:.2f}', f'{hs300_change:.2f}%', f'{hs300_asset_value:.2f}'])

        # 中证海外中国互联网50数据
        china_internet_price = china_internet_data['Close'].iloc[-1]
        china_internet_open = china_internet_data['Open'].iloc[0]
        china_internet_change = ((china_internet_price - china_internet_open) / china_internet_open) * 100
        china_internet_asset_value = calculate_asset_value('中证海外中国互联网50', china_internet_price)
        total_current_assets += china_internet_asset_value
        market_data.append([current_time, '中证海外中国互联网50', f'{china_internet_price:.2f}', f'{china_internet_change:.2f}%', f'{china_internet_asset_value:.2f}'])

        # 比特币数据
        bitcoin_price = bitcoin_data['Close'].iloc[-1]
        bitcoin_open = bitcoin_data['Open'].iloc[0]
        bitcoin_change = ((bitcoin_price - bitcoin_open) / bitcoin_open) * 100
        bitcoin_asset_value = calculate_asset_value('比特币(USD)', bitcoin_price)
        total_current_assets += bitcoin_asset_value
        market_data.append([current_time, '比特币(USD)', f'{bitcoin_price:.2f}', f'{bitcoin_change:.2f}%', f'{bitcoin_asset_value:.2f}'])

        # 计算总资产涨跌幅
        total_assets_change = ((total_current_assets - INITIAL_TOTAL_ASSETS) / INITIAL_TOTAL_ASSETS) * 100
        
        # 添加总资产行
        market_data.insert(0, [current_time, '总资产', f'{total_current_assets/200:.2f}', f'{total_assets_change:.2f}%', f'{total_current_assets:.2f}'])

        # 打印CSV格式的数据
        print("时间,资产名称,当前指数,涨跌幅,当前价格")
        for row in market_data:
            print(','.join(str(item) for item in row))
            
        # 保存到CSV文件
        filename = f'market_indices.csv'
        save_to_csv(market_data, filename)
        print(f"\n数据已保存到文件: {filename}")
        
        # 生成HTML
        generate_html(filename)
        print("已生成HTML文件: index.html")
        
        # 上传文件到 COS
        files_to_upload = [
            ('market_indices.csv', 'fund_thomas/market_indices.csv'),
            ('index.html', 'fund_thomas/index.html')
        ]
        
        for local_file, cos_file in files_to_upload:
            if upload_to_cos(local_file, cos_file):
                print(f"成功上传 {local_file} 到腾讯云 COS")
            else:
                print(f"上传 {local_file} 失败")
                
    except Exception as e:
        print(f"处理数据时发生错误: {str(e)}")
        print("请检查网络连接或稍后重试")

if __name__ == "__main__":
    try:
        # 首先下载已有文件
        files_to_download = [
            ('fund_thomas/market_indices.csv', 'market_indices.csv'),
            ('fund_thomas/index.html', 'index.html')
        ]
        
        if check_cos_config():
            print("开始从 COS 下载文件")
            # 只下载第一个数据文件
            cos_file, local_file = files_to_download[0]
            download_from_cos(cos_file, local_file)
        else:
            print("由于配置不完整，跳过 COS 下载操作")
            
        # 获取市场指数
        get_market_indices()
        
    except Exception as e:
        print(f"获取数据时发生错误: {str(e)}")
