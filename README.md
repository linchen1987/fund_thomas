# 资产价格追踪器

## 项目简介
这是一个自动化追踪和展示主要市场指数数据的工具。该项目可以抓取最新的市场指数数据，并通过网页界面直观地展示这些信息。

- 自动获取主要市场指数的最新数据
    - 标的为纳斯达克指数、标普500指数、沪深300指数、中概互联、比特币
    - 初始投入日期为 2024.11.05, 金额 200 元，每个标的占比均为 20%（40 元）
- 自动更新数据：使用 Github Action 每日自动出发任务，自动记录当天资产价格
- 使用腾讯云 COS 存储数据
- 网页可视化展示

## 本地运行
```
pip install -r requirements.txt

python update_market_indices.py
```

## 使用 github action 和 腾讯云
1. 在腾讯云开通 COS, 创建存储桶
2. 将 .env.templates 中的配置填写到 Github - 你的 repo - settings - secrets and variables - actions 中
