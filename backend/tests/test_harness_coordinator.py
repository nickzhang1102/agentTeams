"""
Tests for HarnessCoordinator
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import os
import tempfile
from pathlib import Path

from services.harness.harness_coordinator import HarnessCoordinator


class TestHarnessCoordinator:
    """Test HarnessCoordinator functionality."""

    def test_coordinator_initialization(self):
        """Test coordinator initialization."""
        coordinator = HarnessCoordinator()

        assert coordinator is not None
        assert coordinator.agents_dir is not None
        assert isinstance(coordinator.registered_agents, dict)
        # Coordinator automatically registers agents from agents_dir
        # So registered_agents may not be empty

    def test_coordinator_with_custom_agents_dir(self):
        """Test coordinator with custom agents directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            coordinator = HarnessCoordinator(agents_dir=tmpdir)

            assert coordinator.agents_dir == tmpdir

    def test_parse_agent_config(self):
        """Test parsing agent configuration from markdown file."""
        coordinator = HarnessCoordinator()

        # Create a temporary agent file
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_file = Path(tmpdir) / "test-agent.md"
            agent_file.write_text("""---
name: test-agent
description: "Test agent for unit testing"
model: inherit
---

# Test Agent

## Role
This is a test agent for unit testing purposes.
""")

            config = coordinator._parse_agent_config(agent_file)

            assert config is not None
            assert config["name"] == "test-agent"
            assert config["description"] == "Test agent for unit testing"
            assert config["model"] == "inherit"
            assert "system_prompt" in config

    def test_parse_agent_config_missing_frontmatter(self):
        """Test parsing agent file without YAML frontmatter."""
        coordinator = HarnessCoordinator()

        with tempfile.TemporaryDirectory() as tmpdir:
            agent_file = Path(tmpdir) / "invalid-agent.md"
            agent_file.write_text("""# Invalid Agent

This agent has no frontmatter.
""")

            config = coordinator._parse_agent_config(agent_file)

            # Should return None or empty config
            assert config is None or config == {}

    def test_get_agent_tools_medical(self):
        """Test tool assignment for medical agents."""
        coordinator = HarnessCoordinator()

        # Medical agent keywords
        tools = coordinator._get_agent_tools("cardiology-expert")
        assert "read_file" in tools
        assert "write_file" in tools
        assert "grep" in tools
        assert "glob" in tools
        assert "web_search" in tools

    def test_get_agent_tools_technical(self):
        """Test tool assignment for technical agents."""
        coordinator = HarnessCoordinator()

        # Technical agent keywords
        tools = coordinator._get_agent_tools("fullstack-developer")
        assert "read_file" in tools
        assert "write_file" in tools
        assert "grep" in tools
        assert "glob" in tools
        assert "bash" in tools
        assert "edit_file" in tools
        assert "web_search" in tools

    def test_get_agent_tools_business(self):
        """Test tool assignment for business agents."""
        coordinator = HarnessCoordinator()

        # Business agent (default)
        tools = coordinator._get_agent_tools("marketing-agent")
        assert "read_file" in tools
        assert "write_file" in tools
        assert "grep" in tools
        assert "glob" in tools
        assert "web_search" in tools
        assert "bash" not in tools

    def test_register_single_agent(self):
        """Test registering a single agent."""
        coordinator = HarnessCoordinator()

        agent_config = {
            "name": "test-agent",
            "description": "Test agent",
            "model": "inherit",
            "system_prompt": "You are a test agent."
        }

        coordinator._register_single_agent(agent_config)

        assert "test-agent" in coordinator.registered_agents
        registered = coordinator.registered_agents["test-agent"]
        assert registered["name"] == "test-agent"
        assert registered["description"] == "Test agent"
        assert "tools" in registered

    def test_register_agents_from_directory(self):
        """Test registering agents from directory."""
        coordinator = HarnessCoordinator()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test agent files
            agent1 = Path(tmpdir) / "agent1.md"
            agent1.write_text("""---
name: agent1
description: "First test agent"
model: inherit
---

# Agent 1
""")

            agent2 = Path(tmpdir) / "agent2.md"
            agent2.write_text("""---
name: agent2
description: "Second test agent"
model: inherit
---

# Agent 2
""")

            coordinator.agents_dir = tmpdir
            coordinator._register_agents()

            assert "agent1" in coordinator.registered_agents
            assert "agent2" in coordinator.registered_agents

    def test_execute_agent_not_registered(self):
        """Test executing an unregistered agent."""
        coordinator = HarnessCoordinator()

        with pytest.raises(ValueError, match="Agent 'nonexistent' not registered"):
            coordinator.execute_agent(
                agent_id="nonexistent",
                task="Test task"
            )

    def test_get_global_coordinator_instance(self):
        """Test getting global coordinator instance."""
        from services.harness.harness_coordinator import get_harness_coordinator

        coordinator1 = get_harness_coordinator()
        coordinator2 = get_harness_coordinator()

        # Should return the same instance
        assert coordinator1 is coordinator2

    def test_query_context_uses_each_injected_workflow_llm_service(self):
        """The global coordinator must not leak one workflow model into another."""
        coordinator = HarnessCoordinator()
        coordinator._ensure_tool_registry = MagicMock(return_value=MagicMock())
        coordinator._filter_tool_registry = MagicMock(return_value=MagicMock())
        coordinator._filter_tool_registry.return_value.to_api_schema.return_value = []
        agent_config = {
            "tools": [],
            "model": "inherit",
            "system_prompt": "test",
        }
        service_a = MagicMock(model="model-a")
        service_a.get_max_output_tokens.return_value = 100
        service_b = MagicMock(model="model-b")
        service_b.get_max_output_tokens.return_value = 200

        with patch("services.harness.openharness_llm_client.OpenHarnessLLMClient") as client_cls:
            context_a, _ = coordinator._build_query_context(
                {"WORKSPACE_DIR": "data/workspace"}, agent_config, "agent-a", llm_service=service_a
            )
            context_b, _ = coordinator._build_query_context(
                {"WORKSPACE_DIR": "data/workspace"}, agent_config, "agent-a", llm_service=service_b
            )

        assert client_cls.call_args_list[0].args == (service_a,)
        assert client_cls.call_args_list[0].kwargs == {"model": "model-a"}
        assert client_cls.call_args_list[1].args == (service_b,)
        assert client_cls.call_args_list[1].kwargs == {"model": "model-b"}
        assert context_a.model == "model-a"
        assert context_b.model == "model-b"

    def test_fallback_llm_service_is_resolved_fresh_per_call(self):
        coordinator = HarnessCoordinator()
        with patch("services.llm_service.create_llm_service") as create_service:
            coordinator._create_fallback_llm_service({"LLM_MODEL": "model-a"})
            coordinator._create_fallback_llm_service({"LLM_MODEL": "model-a"})

        assert create_service.call_count == 2


class TestHarnessCoordinatorIntegration:
    """Integration tests for HarnessCoordinator (requires OpenHarness)."""

    @pytest.mark.skipif(
        not os.environ.get("OPENHARNESS_ENABLED"),
        reason="OpenHarness integration disabled"
    )
    def test_execute_agent_with_tools(self):
        """Test executing an agent with tool access."""
        coordinator = HarnessCoordinator()

        # Register a test agent
        agent_config = {
            "name": "test-worker",
            "description": "Test worker agent",
            "model": "inherit",
            "system_prompt": "You are a test worker."
        }
        coordinator._register_single_agent(agent_config)

        # Execute agent (this would require actual OpenHarness runtime)
        # For now, just verify the method exists
        assert hasattr(coordinator, "execute_agent")

    @pytest.mark.skipif(
        not os.environ.get("OPENHARNESS_ENABLED"),
        reason="OpenHarness integration disabled"
    )
    def test_execute_team_parallel(self):
        """Test executing multiple agents in parallel."""
        coordinator = HarnessCoordinator()

        # Register test agents
        for i in range(3):
            agent_config = {
                "name": f"test-agent-{i}",
                "description": f"Test agent {i}",
                "model": "inherit",
                "system_prompt": f"You are test agent {i}."
            }
            coordinator._register_single_agent(agent_config)

        # Execute team (this would require actual OpenHarness runtime)
        # For now, just verify the method exists
        assert hasattr(coordinator, "execute_team")

    def test_execute_team_parallel_mode(self):
        """Test parallel team execution with framework."""
        coordinator = HarnessCoordinator()

        # Register test agents
        for i in range(3):
            agent_config = {
                "name": f"parallel-agent-{i}",
                "description": f"Parallel test agent {i}",
                "model": "inherit",
                "system_prompt": f"You are parallel test agent {i}."
            }
            coordinator._register_single_agent(agent_config)

        # Mock 单 Agent 执行：本测试验证的是并行编排与结果聚合，不依赖真实 LLM
        def _fake_execute(agent_id, task, context=None, history=None,
                          event_callback=None, user_id=None, llm_service=None):
            return {
                "success": True,
                "status": "completed",
                "agent_id": agent_id,
                "content": f"done by {agent_id}",
                "tool_calls": [],
            }

        coordinator.execute_agent = MagicMock(side_effect=_fake_execute)

        # Execute team in parallel mode
        agents = ["parallel-agent-0", "parallel-agent-1", "parallel-agent-2"]
        results = coordinator.execute_team(
            agents=agents,
            task="test parallel execution",
            parallel=True
        )

        # Verify results
        assert len(results) == 3
        for result in results:
            assert result["success"] is True
            # Status can be "completed" (OpenHarness available) or "framework_ready" (legacy mode)
            assert result["status"] in ["completed", "framework_ready"]
            # Legacy mode has tools_available, actual execution has content and tool_calls
            if result["status"] == "framework_ready":
                assert "tools_available" in result
            else:
                assert "content" in result
                assert "tool_calls" in result

    def test_execute_team_sequential_mode(self):
        """Test sequential team execution with framework."""
        coordinator = HarnessCoordinator()

        # Register test agents
        agent_config = {
            "name": "sequential-agent",
            "description": "Sequential test agent",
            "model": "inherit",
            "system_prompt": "You are a sequential test agent."
        }
        coordinator._register_single_agent(agent_config)

        # Mock 单 Agent 执行：验证顺序编排，不依赖真实 LLM
        coordinator.execute_agent = MagicMock(return_value={
            "success": True,
            "status": "completed",
            "agent_id": "sequential-agent",
            "content": "done",
            "tool_calls": [],
        })

        # Execute team in sequential mode
        agents = ["sequential-agent"]
        results = coordinator.execute_team(
            agents=agents,
            task="test sequential execution",
            parallel=False
        )

        # Verify results
        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["agent_id"] == "sequential-agent"
