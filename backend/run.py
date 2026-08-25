"""
FastAPI 启动脚本

使用 uvicorn 启动 FastAPI 应用。
"""
import os
import uvicorn

from app import app

if __name__ == '__main__':
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5000,
        reload=os.environ.get('APP_ENV') == 'development'
    )