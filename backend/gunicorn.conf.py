"""
Gunicorn 配置文件 - 生产环境优化

文档: https://docs.gunicorn.org/en/stable/settings.html
"""

import multiprocessing
import os

# 服务器绑定
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"

# 工作进程数（容器环境固定 4，避免 cpu_count 在不同环境不一致）
workers = int(os.getenv('WORKERS', 4))

# 工作模式（sync, gevent, eventlet）
worker_class = 'sync'

# 每个工作进程的线程数
threads = int(os.getenv('THREADS', 2))

# 工作进程最大请求数（之后重启，防止内存泄漏）
max_requests = 1000
max_requests_jitter = 50

# 超时时间（秒）
timeout = 120
graceful_timeout = 30
keepalive = 5

# 日志配置
accesslog = '-'  # stdout
errorlog = '-'   # stderr
loglevel = os.getenv('LOG_LEVEL', 'info')

# 进程名
proc_name = 'claude-chat-backend'

# 安全配置
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# 性能优化
preload_app = True  # 预加载应用（节省内存）
reload = False      # 生产环境禁用自动重载

# SSL 配置（如果需要）
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'

# 钩子函数
def on_starting(server):
    """服务器启动时执行"""
    print(f'🚀 Gunicorn 启动中...')
    print(f'   工作进程数: {workers}')
    print(f'   线程数: {threads}')
    print(f'   绑定地址: {bind}')


def when_ready(server):
    """服务器准备就绪时执行"""
    print('✅ Gunicorn 已准备就绪')


def on_exit(server):
    """服务器退出时执行"""
    print('👋 Gunicorn 正在关闭...')


def worker_exit(server, worker):
    """工作进程退出时执行"""
    print(f'⚠️  工作进程 {worker.pid} 已退出')


def pre_fork(server, worker):
    """Fork 工作进程前执行"""
    pass


def post_fork(server, worker):
    """Fork 工作进程后执行"""
    print(f'⚙️  工作进程 {worker.pid} 已启动')
