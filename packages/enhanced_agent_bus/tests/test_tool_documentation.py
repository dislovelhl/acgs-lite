"""
Tests for Model-First Tool Documentation System.

Constitutional Hash: 608508a9bd224290
"""

from ..tool_documentation import (
    AGENT_TOOLS,
    CONSTITUTIONAL_HASH,
    CONSTITUTIONAL_TOOLS,
    GOVERNANCE_TOOLS,
    ToolCategory,
    ToolDefinition,
    ToolExample,
    ToolParameter,
    ToolRegistry,
    create_tool_registry,
    tool,
)

# =============================================================================
# Constitutional Hash Tests
# =============================================================================


class TestConstitutionalHash:
    """Test constitutional hash compliance."""

    def test_hash_value(self):
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_hash_in_tool_definitions(self):
        for tool_def in CONSTITUTIONAL_TOOLS:
            assert tool_def.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# ToolCategory Tests
# =============================================================================


class TestToolCategory:
    """Test tool categories."""

    def test_all_categories_exist(self):
        assert ToolCategory.CONSTITUTIONAL.value == "constitutional"
        assert ToolCategory.GOVERNANCE.value == "governance"
        assert ToolCategory.AGENT.value == "agent"
        assert ToolCategory.MEMORY.value == "memory"
        assert ToolCategory.RESEARCH.value == "research"
        assert ToolCategory.WORKFLOW.value == "workflow"
        assert ToolCategory.UTILITY.value == "utility"


# =============================================================================
# ToolParameter Tests
# =============================================================================


class TestToolParameter:
    """Test tool parameter definitions."""

    def test_basic_parameter(self):
        param = ToolParameter(
            name="action",
            type="string",
            description="The action to perform",
        )
        assert param.name == "action"
        assert param.type == "string"
        assert param.required

    def test_optional_parameter(self):
        param = ToolParameter(
            name="limit",
            type="integer",
            description="Maximum results",
            required=False,
            default=10,
        )
        assert not param.required
        assert param.default == 10

    def test_enum_parameter(self):
        param = ToolParameter(
            name="priority",
            type="string",
            description="Priority level",
            enum_values=["low", "medium", "high"],
        )
        assert param.enum_values == ["low", "medium", "high"]

    def test_to_dict(self):
        param = ToolParameter(
            name="test",
            type="string",
            description="Test param",
            examples=["example1", "example2"],
        )
        d = param.to_dict()
        assert d["name"] == "test"
        assert d["examples"] == ["example1", "example2"]

    def test_to_json_schema_string(self):
        param = ToolParameter(name="text", type="string", description="Some text")
        schema = param.to_json_schema()
        assert schema["type"] == "string"

    def test_to_json_schema_integer(self):
        param = ToolParameter(name="count", type="integer", description="Count")
        schema = param.to_json_schema()
        assert schema["type"] == "integer"

    def test_to_json_schema_boolean(self):
        param = ToolParameter(name="enabled", type="boolean", description="Enabled")
        schema = param.to_json_schema()
        assert schema["type"] == "boolean"

    def test_to_json_schema_with_enum(self):
        param = ToolParameter(
            name="level",
            type="string",
            description="Level",
            enum_values=["a", "b", "c"],
        )
        schema = param.to_json_schema()
        assert schema["enum"] == ["a", "b", "c"]


# =============================================================================
# ToolExample Tests
# =============================================================================


class TestToolExample:
    """Test tool examples."""

    def test_basic_example(self):
        example = ToolExample(
            description="Test example",
            input={"arg": "value"},
            output={"result": "success"},
        )
        assert example.description == "Test example"
        assert example.input["arg"] == "value"

    def test_example_with_notes(self):
        example = ToolExample(
            description="Example with notes",
            input={},
            output={},
            notes="Important note",
        )
        assert example.notes == "Important note"

    def test_to_dict(self):
        example = ToolExample(
            description="Dict test",
            input={"a": 1},
            output={"b": 2},
            notes="Note",
        )
        d = example.to_dict()
        assert d["description"] == "Dict test"
        assert d["notes"] == "Note"


# =============================================================================
# ToolDefinition Tests
# =============================================================================


class TestToolDefinition:
    """Test tool definitions."""

    def test_basic_definition(self):
        tool_def = ToolDefinition(
            name="test_tool",
            description="A test tool",
            category=ToolCategory.UTILITY,
        )
        assert tool_def.name == "test_tool"
        assert tool_def.category == ToolCategory.UTILITY

    def test_definition_with_use_when(self):
        tool_def = ToolDefinition(
            name="contextual_tool",
            description="Context-aware tool",
            category=ToolCategory.GOVERNANCE,
            use_when=["Condition A", "Condition B"],
            do_not_use_for=["Condition X"],
        )
        assert len(tool_def.use_when) == 2
        assert len(tool_def.do_not_use_for) == 1

    def test_definition_with_parameters(self):
        tool_def = ToolDefinition(
            name="param_tool",
            description="Tool with params",
            category=ToolCategory.AGENT,
            parameters=[
                ToolParameter(name="input", type="string", description="Input"),
                ToolParameter(name="count", type="integer", description="Count"),
            ],
        )
        assert len(tool_def.parameters) == 2

    def test_to_dict(self):
        tool_def = ToolDefinition(
            name="dict_tool",
            description="Dict conversion test",
            category=ToolCategory.MEMORY,
            returns="Some return value",
        )
        d = tool_def.to_dict()
        assert d["name"] == "dict_tool"
        assert d["category"] == "memory"
        assert d["returns"] == "Some return value"

    def test_to_prompt_format(self):
        tool_def = ToolDefinition(
            name="prompt_tool",
            description="Tool for prompt format testing",
            category=ToolCategory.CONSTITUTIONAL,
            use_when=["When you need to test"],
            do_not_use_for=["When testing is complete"],
            parameters=[
                ToolParameter(name="arg1", type="string", description="First argument"),
            ],
            returns="A test result",
        )
        prompt = tool_def.to_prompt_format()
        assert "### prompt_tool" in prompt
        assert "USE THIS WHEN:" in prompt
        assert "DO NOT USE FOR:" in prompt
        assert "PARAMETERS:" in prompt
        assert "RETURNS:" in prompt

    def test_to_openai_schema(self):
        tool_def = ToolDefinition(
            name="openai_tool",
            description="OpenAI schema test",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="required_param", type="string", description="Required"),
                ToolParameter(
                    name="optional_param", type="integer", description="Optional", required=False
                ),
            ],
        )
        schema = tool_def.to_openai_schema()
        assert schema["name"] == "openai_tool"
        assert "required_param" in schema["parameters"]["properties"]
        assert "required_param" in schema["parameters"]["required"]
        assert "optional_param" not in schema["parameters"]["required"]

    def test_to_anthropic_schema(self):
        tool_def = ToolDefinition(
            name="anthropic_tool",
            description="Anthropic schema test",
            category=ToolCategory.GOVERNANCE,
            use_when=["Testing Anthropic format"],
            parameters=[
                ToolParameter(name="input", type="object", description="Input data"),
            ],
        )
        schema = tool_def.to_anthropic_schema()
        assert schema["name"] == "anthropic_tool"
        assert "USE THIS WHEN:" in schema["description"]
        assert "input" in schema["input_schema"]["properties"]


# =============================================================================
# ToolRegistry Tests
# =============================================================================


class TestToolRegistry:
    """Test tool registry."""

    def test_create_empty_registry(self):
        registry = ToolRegistry()
        assert registry.list_tools() == []

    def test_register_tool(self):
        registry = ToolRegistry()
        tool_def = ToolDefinition(
            name="registered_tool",
            description="A registered tool",
            category=ToolCategory.UTILITY,
        )
        registry.register(tool_def)
        assert "registered_tool" in registry.list_tools()

    def test_get_tool(self):
        registry = ToolRegistry()
        tool_def = ToolDefinition(
            name="get_test",
            description="Get test",
            category=ToolCategory.AGENT,
        )
        registry.register(tool_def)

        retrieved = registry.get("get_test")
        assert retrieved is not None
        assert retrieved.name == "get_test"

    def test_get_nonexistent_tool(self):
        registry = ToolRegistry()
        result = registry.get("nonexistent")
        assert result is None

    def test_get_by_category(self):
        registry = ToolRegistry()

        # Register tools in different categories
        registry.register(
            ToolDefinition(
                name="governance1",
                description="Gov 1",
                category=ToolCategory.GOVERNANCE,
            )
        )
        registry.register(
            ToolDefinition(
                name="governance2",
                description="Gov 2",
                category=ToolCategory.GOVERNANCE,
            )
        )
        registry.register(
            ToolDefinition(
                name="agent1",
                description="Agent 1",
                category=ToolCategory.AGENT,
            )
        )

        gov_tools = registry.get_by_category(ToolCategory.GOVERNANCE)
        assert len(gov_tools) == 2

        agent_tools = registry.get_by_category(ToolCategory.AGENT)
        assert len(agent_tools) == 1

    def test_get_all(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(name="t1", description="T1", category=ToolCategory.UTILITY)
        )
        registry.register(ToolDefinition(name="t2", description="T2", category=ToolCategory.MEMORY))

        all_tools = registry.get_all()
        assert len(all_tools) == 2

    def test_to_prompt_format(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="prompt1",
                description="Prompt tool 1",
                category=ToolCategory.UTILITY,
            )
        )
        registry.register(
            ToolDefinition(
                name="prompt2",
                description="Prompt tool 2",
                category=ToolCategory.UTILITY,
            )
        )

        prompt = registry.to_prompt_format()
        assert "### prompt1" in prompt
        assert "### prompt2" in prompt

    def test_to_prompt_format_by_category(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(name="util", description="Util", category=ToolCategory.UTILITY)
        )
        registry.register(
            ToolDefinition(name="agent", description="Agent", category=ToolCategory.AGENT)
        )

        prompt = registry.to_prompt_format(category=ToolCategory.UTILITY)
        assert "### util" in prompt
        assert "### agent" not in prompt

    def test_to_openai_schemas(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(name="t1", description="T1", category=ToolCategory.UTILITY)
        )
        registry.register(
            ToolDefinition(name="t2", description="T2", category=ToolCategory.UTILITY)
        )

        schemas = registry.to_openai_schemas()
        assert len(schemas) == 2
        assert all("parameters" in s for s in schemas)

    def test_to_anthropic_schemas(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(name="t1", description="T1", category=ToolCategory.UTILITY)
        )

        schemas = registry.to_anthropic_schemas()
        assert len(schemas) == 1
        assert "input_schema" in schemas[0]

    def test_find_related(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="main_tool",
                description="Main",
                category=ToolCategory.UTILITY,
                related_tools=["helper_tool"],
            )
        )
        registry.register(
            ToolDefinition(
                name="helper_tool",
                description="Helper",
                category=ToolCategory.UTILITY,
            )
        )

        related = registry.find_related("main_tool")
        assert len(related) == 1
        assert related[0].name == "helper_tool"

    def test_find_related_nonexistent(self):
        registry = ToolRegistry()
        related = registry.find_related("nonexistent")
        assert related == []

    def test_get_stats(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(name="t1", description="T1", category=ToolCategory.CONSTITUTIONAL)
        )
        registry.register(
            ToolDefinition(name="t2", description="T2", category=ToolCategory.GOVERNANCE)
        )
        registry.register(
            ToolDefinition(name="t3", description="T3", category=ToolCategory.GOVERNANCE)
        )

        stats = registry.get_stats()
        assert stats["total_tools"] == 3
        assert stats["by_category"]["constitutional"] == 1
        assert stats["by_category"]["governance"] == 2
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Tool Decorator Tests
# =============================================================================


class TestToolDecorator:
    """Test the @tool decorator."""

    def test_basic_decorator(self):
        @tool(
            name="decorated_tool",
            description="A decorated tool",
            category=ToolCategory.UTILITY,
        )
        async def my_tool(arg1: str):
            return arg1

        assert hasattr(my_tool, "_tool_definition")
        assert my_tool._tool_definition.name == "decorated_tool"

    def test_decorator_extracts_parameters(self):
        @tool(
            name="param_tool",
            description="Tool with params",
            category=ToolCategory.AGENT,
        )
        async def param_tool(required_arg: str, _optional_arg: int = 10):
            return required_arg

        tool_def = param_tool._tool_definition
        assert len(tool_def.parameters) == 2

        param_names = [p.name for p in tool_def.parameters]
        assert "required_arg" in param_names
        assert "optional_arg" in param_names or "_optional_arg" in param_names

    def test_decorator_with_use_when(self):
        @tool(
            name="contextual",
            description="Contextual tool",
            category=ToolCategory.GOVERNANCE,
            use_when=["Condition A", "Condition B"],
            do_not_use_for=["Condition X"],
        )
        async def contextual():
            pass

        tool_def = contextual._tool_definition
        assert len(tool_def.use_when) == 2
        assert len(tool_def.do_not_use_for) == 1

    def test_decorator_preserves_function(self):
        @tool(
            name="preserved",
            description="Function preserved",
            category=ToolCategory.UTILITY,
        )
        def sync_tool(value: int):
            return value * 2

        # Function should still work
        result = sync_tool(21)
        assert result == 42


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateToolRegistry:
    """Test factory function."""

    def test_create_with_defaults(self):
        registry = create_tool_registry(include_defaults=True)
        assert len(registry.list_tools()) > 0

    def test_create_without_defaults(self):
        registry = create_tool_registry(include_defaults=False)
        assert len(registry.list_tools()) == 0

    def test_create_with_custom_hash(self):
        registry = create_tool_registry(
            constitutional_hash="custom123",
            include_defaults=False,
        )
        assert registry._constitutional_hash == "custom123"

    def test_default_tools_registered(self):
        registry = create_tool_registry(include_defaults=True)

        # Check constitutional tools
        assert registry.get("validate_constitutional_compliance") is not None

        # Check governance tools
        assert registry.get("create_governance_proposal") is not None

        # Check agent tools
        assert registry.get("spawn_agent") is not None


# =============================================================================
# Pre-defined Tool Tests
# =============================================================================


class TestConstitutionalTools:
    """Test pre-defined constitutional tools."""

    def test_constitutional_tools_defined(self):
        assert len(CONSTITUTIONAL_TOOLS) >= 2

    def test_validate_constitutional_compliance_tool(self):
        tool_def = next(
            (t for t in CONSTITUTIONAL_TOOLS if t.name == "validate_constitutional_compliance"),
            None,
        )
        assert tool_def is not None
        assert tool_def.category == ToolCategory.CONSTITUTIONAL
        assert len(tool_def.use_when) > 0
        assert len(tool_def.parameters) > 0
        assert len(tool_def.examples) > 0

    def test_get_constitutional_principles_tool(self):
        tool_def = next(
            (t for t in CONSTITUTIONAL_TOOLS if t.name == "get_constitutional_principles"), None
        )
        assert tool_def is not None
        assert len(tool_def.use_when) > 0


class TestGovernanceTools:
    """Test pre-defined governance tools."""

    def test_governance_tools_defined(self):
        assert len(GOVERNANCE_TOOLS) >= 2

    def test_create_governance_proposal_tool(self):
        tool_def = next(
            (t for t in GOVERNANCE_TOOLS if t.name == "create_governance_proposal"), None
        )
        assert tool_def is not None
        assert tool_def.category == ToolCategory.GOVERNANCE
        assert len(tool_def.parameters) >= 4

    def test_audit_action_tool(self):
        tool_def = next((t for t in GOVERNANCE_TOOLS if t.name == "audit_action"), None)
        assert tool_def is not None
        assert len(tool_def.examples) > 0


class TestAgentTools:
    """Test pre-defined agent tools."""

    def test_agent_tools_defined(self):
        assert len(AGENT_TOOLS) >= 2

    def test_spawn_agent_tool(self):
        tool_def = next((t for t in AGENT_TOOLS if t.name == "spawn_agent"), None)
        assert tool_def is not None
        assert tool_def.category == ToolCategory.AGENT
        assert len(tool_def.edge_cases) > 0
        assert len(tool_def.common_errors) > 0

    def test_assign_task_tool(self):
        tool_def = next((t for t in AGENT_TOOLS if t.name == "assign_task"), None)
        assert tool_def is not None
        assert len(tool_def.related_tools) > 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestToolDocumentationIntegration:
    """Integration tests for tool documentation system."""

    def test_full_workflow(self):
        """Test complete tool registration and retrieval workflow."""
        # Create registry
        registry = create_tool_registry(include_defaults=False)

        # Create custom tool
        tool_def = ToolDefinition(
            name="custom_tool",
            description="A custom integration test tool",
            category=ToolCategory.WORKFLOW,
            use_when=["Testing integration"],
            parameters=[
                ToolParameter(
                    name="input",
                    type="string",
                    description="Input data",
                    required=True,
                ),
            ],
            returns="Processed result",
            examples=[
                ToolExample(
                    description="Basic usage",
                    input={"input": "test"},
                    output={"result": "processed"},
                ),
            ],
        )

        # Register
        registry.register(tool_def)

        # Retrieve and validate
        retrieved = registry.get("custom_tool")
        assert retrieved is not None
        assert retrieved.constitutional_hash == CONSTITUTIONAL_HASH

        # Generate schemas
        openai = registry.to_openai_schemas()
        anthropic = registry.to_anthropic_schemas()
        prompt = registry.to_prompt_format()

        assert len(openai) == 1
        assert len(anthropic) == 1
        assert "custom_tool" in prompt

    def test_schema_compatibility(self):
        """Verify generated schemas are valid."""
        registry = create_tool_registry(include_defaults=True)

        for schema in registry.to_openai_schemas():
            assert "name" in schema
            assert "description" in schema
            assert "parameters" in schema
            assert schema["parameters"]["type"] == "object"

        for schema in registry.to_anthropic_schemas():
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            assert schema["input_schema"]["type"] == "object"

    def test_prompt_format_completeness(self):
        """Verify prompt format includes all sections."""
        tool_def = ToolDefinition(
            name="complete_tool",
            description="Complete tool for testing",
            category=ToolCategory.CONSTITUTIONAL,
            use_when=["Use condition"],
            do_not_use_for=["Don't use condition"],
            parameters=[
                ToolParameter(name="p1", type="string", description="Param 1"),
            ],
            returns="Return description",
            examples=[
                ToolExample(description="Example", input={}, output={}),
            ],
            edge_cases=["Edge case 1"],
            common_errors={"Error1": "Solution 1"},
            related_tools=["other_tool"],
        )

        prompt = tool_def.to_prompt_format()

        # All sections should be present
        assert "### complete_tool" in prompt
        assert "USE THIS WHEN:" in prompt
        assert "DO NOT USE FOR:" in prompt
        assert "PARAMETERS:" in prompt
        assert "RETURNS:" in prompt
        assert "EXAMPLES:" in prompt
        assert "EDGE CASES:" in prompt
        assert "COMMON ERRORS:" in prompt
        assert "RELATED:" in prompt
