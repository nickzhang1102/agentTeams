"""与提供商无关的启动网关与适配器注册表。

网关仅负责客户端认证与路由。工作流细节保留在适配器之后，这样未来的系统
就不会依赖 Agent Teams 的患者专属负载字段或 LangGraph 内部实现。
"""

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from services.integration_client_service import (
    IntegrationClientContext,
    IntegrationClientError,
    IntegrationClientService,
)


class IntegrationAdapter(Protocol):
    """与提供商无关的集成 SPI。

    适配器负责工作流与适配器细节。网关调用方仅交换稳定的引用/状态值以及
    不透明的元数据。
    """

    adapter_key: str

    def launch(
        self,
        db_session: Session,
        *,
        payload: dict[str, Any],
        request_id: str,
        client: IntegrationClientContext,
    ) -> dict[str, Any]: ...

    def get_status(
        self,
        db_session: Session,
        *,
        request_id: str,
        client: IntegrationClientContext,
    ) -> dict[str, Any]: ...

    def reconcile(
        self,
        db_session: Session,
        *,
        request_id: str,
        client: IntegrationClientContext,
    ) -> dict[str, Any]: ...

    def reissue_embed(
        self,
        db_session: Session,
        *,
        request_id: str,
        client: IntegrationClientContext,
    ) -> dict[str, Any]: ...

    def schedule_launch(
        self,
        db_session: Session,
        *,
        result: dict[str, Any],
        request_id: str,
        client: IntegrationClientContext,
    ) -> None: ...


class IntegrationAdapterRegistry:
    _adapters: dict[str, IntegrationAdapter] = {}

    @classmethod
    def register(cls, adapter: IntegrationAdapter) -> None:
        key = str(adapter.adapter_key or '').strip()
        if not key:
            raise ValueError('integration adapter adapter_key is required')
        cls._adapters[key] = adapter

    @classmethod
    def get(cls, adapter_key: str) -> IntegrationAdapter | None:
        return cls._adapters.get(str(adapter_key or '').strip())


class IntegrationGateway:
    """认证并分派一个已经是幂等的启动请求。"""

    def __init__(self, db_session: Session):
        self.db_session = db_session

    def authenticate(self, client_key: str, integration_key: str | None) -> IntegrationClientContext:
        return IntegrationClientService.authenticate(
            self.db_session,
            client_key,
            integration_key,
        )

    def launch(
        self,
        client: IntegrationClientContext,
        *,
        payload: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        if client.capabilities.get('launch') is not True:
            raise IntegrationClientError(
                403,
                'integration_capability_disabled',
                'Integration launch capability is disabled',
            )
        adapter = IntegrationAdapterRegistry.get(client.adapter_key)
        if adapter is None:
            raise IntegrationClientError(
                501,
                'integration_adapter_unavailable',
                'Integration launch adapter is not available',
            )
        return adapter.launch(
            self.db_session,
            payload=payload,
            request_id=request_id,
            client=client,
        )

    def _adapter_for(self, client: IntegrationClientContext) -> IntegrationAdapter:
        adapter = IntegrationAdapterRegistry.get(client.adapter_key)
        if adapter is None:
            raise IntegrationClientError(
                501,
                'integration_adapter_unavailable',
                'Integration adapter is not available',
            )
        return adapter

    def get_status(self, client: IntegrationClientContext, *, request_id: str) -> dict[str, Any]:
        if client.capabilities.get('status_query') is not True:
            raise IntegrationClientError(403, 'integration_capability_disabled', 'Integration status capability is disabled')
        return self._adapter_for(client).get_status(
            self.db_session, request_id=request_id, client=client
        )

    def reconcile(self, client: IntegrationClientContext, *, request_id: str) -> dict[str, Any]:
        if client.capabilities.get('reconcile') is not True and client.capabilities.get('status_query') is not True:
            raise IntegrationClientError(403, 'integration_capability_disabled', 'Integration reconcile capability is disabled')
        return self._adapter_for(client).reconcile(
            self.db_session, request_id=request_id, client=client
        )

    def reissue_embed(self, client: IntegrationClientContext, *, request_id: str) -> dict[str, Any]:
        if client.capabilities.get('reissue_embed') is not True:
            raise IntegrationClientError(
                403,
                'integration_capability_disabled',
                'Integration embed reissue capability is disabled',
            )
        return self._adapter_for(client).reissue_embed(
            self.db_session, request_id=request_id, client=client
        )

    def schedule_launch(
        self,
        client: IntegrationClientContext,
        *,
        result: dict[str, Any],
        request_id: str,
    ) -> None:
        self._adapter_for(client).schedule_launch(
            self.db_session,
            result=result,
            request_id=request_id,
            client=client,
        )


def register_builtin_adapters() -> None:
    """延迟注册适配器，使导入网关保持无副作用。"""
    if IntegrationAdapterRegistry.get('agentteams') is not None:
        return
    from services.agentteams_integration_launch import launch_agentteams_consultation

    class _AgentTeamsAdapter:
        adapter_key = 'agentteams'

        @staticmethod
        def _normalize_status(value: Any) -> str:
            status = str(value or 'created').strip().lower()
            if status in {'not_found', 'created', 'completed', 'failed', 'stopped'}:
                return status
            return 'running'

        @staticmethod
        def _storage_request_id(request_id: str, client: IntegrationClientContext) -> str:
            from services.agentteams_integration_launch import agentteams_storage_request_id
            return agentteams_storage_request_id(request_id, client.client_key)

        def launch(self, db_session, *, payload, request_id, client):
            adapted_payload = dict(payload)
            adapted_payload['source'] = 'agentteams'
            metadata = dict(adapted_payload.get('metadata') or {})
            metadata.setdefault('integration_client', client.client_key)
            adapted_payload['metadata'] = metadata
            result = launch_agentteams_consultation(
                db_session=db_session,
                payload=adapted_payload,
                request_id=self._storage_request_id(request_id, client),
                integration_key=None,
                integration_context=client,
            )
            result['status'] = self._normalize_status(result.get('status'))
            return result

        def get_status(self, db_session, *, request_id, client):
            from services.agentteams_integration_launch import get_agentteams_launch_by_request_id
            result = get_agentteams_launch_by_request_id(
                db_session=db_session,
                request_id=self._storage_request_id(request_id, client),
                integration_key=None,
                integration_context=client,
            )
            result['request_id'] = request_id
            result['status'] = self._normalize_status(result.get('status'))
            return result

        def reconcile(self, db_session, *, request_id, client):
            # 协调刻意保持只读；任何随后的状态转换由持久化工作线程负责，
            # 而非此端点。
            return self.get_status(db_session, request_id=request_id, client=client)

        def reissue_embed(self, db_session, *, request_id, client):
            from services.agentteams_integration_launch import reissue_agentteams_embed_token
            result = reissue_agentteams_embed_token(
                db_session=db_session,
                request_id=self._storage_request_id(request_id, client),
                integration_key=None,
                integration_context=client,
            )
            result['status'] = self._normalize_status(result.get('status'))
            return result

        def schedule_launch(self, db_session, *, result, request_id, client):
            if not result.pop('_start_background', False):
                return
            from models import AgentTeamsLaunch
            # 在调用时通过 API 模块解析，以便部署与契约测试能够替换调度器，
            # 而无需改变适配器的边界。
            from api.agentteams_integration_api import schedule_agentteams_launch

            launch = db_session.query(AgentTeamsLaunch).filter_by(
                source='agentteams',
                request_id=self._storage_request_id(request_id, client),
            ).one()
            schedule_agentteams_launch(launch.id)

    IntegrationAdapterRegistry.register(_AgentTeamsAdapter())
