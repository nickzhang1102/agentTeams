"""Admin API Router（聚合入口）

聚合所有 admin 子路由模块，提供统一的 /api/admin 前缀。
具体路由实现在各子模块中。
"""

from fastapi import APIRouter

from api.admin.mcp_admin_api import router as mcp_admin_router
from api.admin.dashboard_api import router as dashboard_router
from api.admin.agent_admin_api import router as agent_admin_router
from api.admin.performance_api import router as performance_router
from api.admin.tool_logs_api import router as tool_logs_router
from api.admin.settings_api import router as settings_router
from api.admin.leader_admin_api import router as leader_admin_router
from api.admin.priority_rules_api import router as priority_rules_router
from api.admin.llm_model_admin_api import router as llm_model_admin_router
from api.admin.agentteams_integration_admin_api import router as agentteams_integration_admin_router
from api.admin.integration_clients_admin_api import router as integration_clients_admin_router

# 向后兼容：导出常量供外部模块使用（如 tests/test_openharness_config.py）
from api.admin.openharness_config import OPENHARNESS_CONFIG_SCHEMA  # noqa: F401


router = APIRouter(prefix="/api/admin", tags=["admin"])

# 挂载所有子路由
router.include_router(mcp_admin_router)
router.include_router(dashboard_router)
router.include_router(agent_admin_router)
router.include_router(performance_router)
router.include_router(tool_logs_router)
router.include_router(settings_router)
router.include_router(leader_admin_router)
router.include_router(priority_rules_router)
router.include_router(llm_model_admin_router)
router.include_router(agentteams_integration_admin_router)
router.include_router(integration_clients_admin_router)
