"""Route introspection helpers that work across FastAPI versions.

FastAPI >= 0.141 的 include_router 改为惰性注册：app.routes 中出现无
.path 属性的 _IncludedRouter，实际路由藏在 include_context.included_router
之下；旧版本则已立即展开为带 .path 的 APIRoute。这里统一两种形态。
"""
from typing import Iterator


def iter_route_paths(router) -> Iterator[str]:
    """递归枚举路由器（含惰性 include 的子路由器）上全部路由的完整路径。"""
    for route in router.routes:
        context = getattr(route, 'include_context', None)
        if context is not None:
            nested = getattr(context, 'included_router', None)
            if nested is not None:
                prefix = getattr(context, 'prefix', '') or ''
                for nested_path in iter_route_paths(nested):
                    yield prefix + nested_path
            continue
        path = getattr(route, 'path', None)
        if path:
            yield path
