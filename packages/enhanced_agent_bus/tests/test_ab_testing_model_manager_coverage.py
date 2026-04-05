"""
Tests for ab_testing_infra/model_manager.py
Constitutional Hash: 608508a9bd224290
"""

import logging
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from enhanced_agent_bus.ab_testing_infra.model_manager import (
    MODEL_LOAD_ERRORS,
    ABTestModelManager,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager():
    """Default ABTestModelManager instance."""
    return ABTestModelManager(
        champion_alias="champion",
        candidate_alias="candidate",
        model_registry_name="governance_impact_scorer",
    )


def _mock_model(name: str = "model") -> MagicMock:
    """Return a simple mock that satisfies MLModelProtocol (has .predict)."""
    m = MagicMock()
    m.predict.return_value = 1
    m.__repr__ = lambda self: name
    return m


def _make_mlflow_mocks(champion_version="1", candidate_version="2"):
    """Return (mock_mlflow_sklearn, mock_mlflow_client_cls, champion_mv, candidate_mv)."""
    champion_mv = MagicMock()
    champion_mv.version = champion_version

    candidate_mv = MagicMock()
    candidate_mv.version = candidate_version

    mock_client_instance = MagicMock()
    mock_client_instance.get_model_version_by_alias.side_effect = [
        champion_mv,
        candidate_mv,
    ]

    mock_client_cls = MagicMock(return_value=mock_client_instance)

    mock_mlflow_sklearn = MagicMock()
    champion_model = _mock_model("champion_model")
    candidate_model = _mock_model("candidate_model")
    mock_mlflow_sklearn.load_model.side_effect = [champion_model, candidate_model]

    return (
        mock_mlflow_sklearn,
        mock_client_cls,
        mock_client_instance,
        champion_mv,
        candidate_mv,
        champion_model,
        candidate_model,
    )


# ===========================================================================
# 1. MODEL_LOAD_ERRORS constant
# ===========================================================================


class TestModelLoadErrors:
    def test_is_tuple(self):
        assert isinstance(MODEL_LOAD_ERRORS, tuple)

    def test_contains_import_error(self):
        assert ImportError in MODEL_LOAD_ERRORS

    def test_contains_module_not_found_error(self):
        assert ModuleNotFoundError in MODEL_LOAD_ERRORS

    def test_contains_attribute_error(self):
        assert AttributeError in MODEL_LOAD_ERRORS

    def test_contains_runtime_error(self):
        assert RuntimeError in MODEL_LOAD_ERRORS

    def test_contains_value_error(self):
        assert ValueError in MODEL_LOAD_ERRORS

    def test_contains_type_error(self):
        assert TypeError in MODEL_LOAD_ERRORS

    def test_contains_os_error(self):
        assert OSError in MODEL_LOAD_ERRORS

    def test_length_is_seven(self):
        assert len(MODEL_LOAD_ERRORS) == 7


# ===========================================================================
# 2. __init__ — attribute initialisation
# ===========================================================================


class TestABTestModelManagerInit:
    def test_champion_alias_stored(self, manager):
        assert manager.champion_alias == "champion"

    def test_candidate_alias_stored(self, manager):
        assert manager.candidate_alias == "candidate"

    def test_model_registry_name_stored(self, manager):
        assert manager.model_registry_name == "governance_impact_scorer"

    def test_champion_model_none(self, manager):
        assert manager.champion_model is None

    def test_candidate_model_none(self, manager):
        assert manager.candidate_model is None

    def test_champion_version_none(self, manager):
        assert manager.champion_version is None

    def test_candidate_version_none(self, manager):
        assert manager.candidate_version is None

    def test_models_loaded_false(self, manager):
        assert manager.models_loaded is False

    def test_custom_aliases(self):
        m = ABTestModelManager("prod", "beta", "my_registry")
        assert m.champion_alias == "prod"
        assert m.candidate_alias == "beta"
        assert m.model_registry_name == "my_registry"

    def test_is_ready_false_on_init(self, manager):
        assert manager.is_ready() is False


# ===========================================================================
# 3. load_models — success path
# ===========================================================================


class TestLoadModelsSuccess:
    def test_returns_true_on_success(self, manager):
        import types

        mock_sklearn, mock_client_cls, _, _, _, _, _ = _make_mlflow_mocks("1", "2")
        fake_mlflow = types.ModuleType("mlflow")
        fake_mlflow.sklearn = mock_sklearn
        fake_tracking = types.ModuleType("mlflow.tracking")
        fake_tracking.MlflowClient = mock_client_cls

        with patch.dict(
            sys.modules,
            {
                "mlflow": fake_mlflow,
                "mlflow.sklearn": mock_sklearn,
                "mlflow.tracking": fake_tracking,
            },
        ):
            result = manager.load_models()

        assert result is True

    def test_models_loaded_set_to_true(self, manager):
        import types

        (
            mock_sklearn,
            mock_client_cls,
            _mock_client_instance,
            _,
            _champion_model,
            _candidate_model,
            _,
        ) = _make_mlflow_mocks()
        fake_mlflow = types.ModuleType("mlflow")
        fake_mlflow.sklearn = mock_sklearn
        fake_tracking = types.ModuleType("mlflow.tracking")
        fake_tracking.MlflowClient = mock_client_cls

        with patch.dict(
            sys.modules,
            {
                "mlflow": fake_mlflow,
                "mlflow.sklearn": mock_sklearn,
                "mlflow.tracking": fake_tracking,
            },
        ):
            manager.load_models()

        assert manager.models_loaded is True

    def test_champion_model_assigned(self, manager):
        import types

        mock_sklearn, mock_client_cls, _, _, _, champion_model, _ = _make_mlflow_mocks()
        fake_mlflow = types.ModuleType("mlflow")
        fake_mlflow.sklearn = mock_sklearn
        fake_tracking = types.ModuleType("mlflow.tracking")
        fake_tracking.MlflowClient = mock_client_cls

        with patch.dict(
            sys.modules,
            {
                "mlflow": fake_mlflow,
                "mlflow.sklearn": mock_sklearn,
                "mlflow.tracking": fake_tracking,
            },
        ):
            manager.load_models()

        assert manager.champion_model is champion_model

    def test_candidate_model_assigned(self, manager):
        import types

        mock_sklearn, mock_client_cls, _, _, _, _, candidate_model = _make_mlflow_mocks()
        fake_mlflow = types.ModuleType("mlflow")
        fake_mlflow.sklearn = mock_sklearn
        fake_tracking = types.ModuleType("mlflow.tracking")
        fake_tracking.MlflowClient = mock_client_cls

        with patch.dict(
            sys.modules,
            {
                "mlflow": fake_mlflow,
                "mlflow.sklearn": mock_sklearn,
                "mlflow.tracking": fake_tracking,
            },
        ):
            manager.load_models()

        assert manager.candidate_model is candidate_model

    def test_champion_version_assigned(self, manager):
        import types

        mock_sklearn, mock_client_cls, _, _champion_mv, _, _, _ = _make_mlflow_mocks("42", "99")
        fake_mlflow = types.ModuleType("mlflow")
        fake_mlflow.sklearn = mock_sklearn
        fake_tracking = types.ModuleType("mlflow.tracking")
        fake_tracking.MlflowClient = mock_client_cls

        with patch.dict(
            sys.modules,
            {
                "mlflow": fake_mlflow,
                "mlflow.sklearn": mock_sklearn,
                "mlflow.tracking": fake_tracking,
            },
        ):
            manager.load_models()

        assert manager.champion_version == "42"

    def test_candidate_version_assigned(self, manager):
        import types

        mock_sklearn, mock_client_cls, _, _, _candidate_mv, _, _ = _make_mlflow_mocks("42", "99")
        fake_mlflow = types.ModuleType("mlflow")
        fake_mlflow.sklearn = mock_sklearn
        fake_tracking = types.ModuleType("mlflow.tracking")
        fake_tracking.MlflowClient = mock_client_cls

        with patch.dict(
            sys.modules,
            {
                "mlflow": fake_mlflow,
                "mlflow.sklearn": mock_sklearn,
                "mlflow.tracking": fake_tracking,
            },
        ):
            manager.load_models()

        assert manager.candidate_version == "99"

    def test_is_ready_after_successful_load(self, manager):
        import types

        mock_sklearn, mock_client_cls, _, _, _, _, _ = _make_mlflow_mocks()
        fake_mlflow = types.ModuleType("mlflow")
        fake_mlflow.sklearn = mock_sklearn
        fake_tracking = types.ModuleType("mlflow.tracking")
        fake_tracking.MlflowClient = mock_client_cls

        with patch.dict(
            sys.modules,
            {
                "mlflow": fake_mlflow,
                "mlflow.sklearn": mock_sklearn,
                "mlflow.tracking": fake_tracking,
            },
        ):
            manager.load_models()

        assert manager.is_ready() is True

    def test_load_model_uri_uses_registry_name_and_champion_alias(self, manager):
        import types

        mock_sklearn, mock_client_cls, _, _, _, _, _ = _make_mlflow_mocks()
        fake_mlflow = types.ModuleType("mlflow")
        fake_mlflow.sklearn = mock_sklearn
        fake_tracking = types.ModuleType("mlflow.tracking")
        fake_tracking.MlflowClient = mock_client_cls

        with patch.dict(
            sys.modules,
            {
                "mlflow": fake_mlflow,
                "mlflow.sklearn": mock_sklearn,
                "mlflow.tracking": fake_tracking,
            },
        ):
            manager.load_models()

        calls = mock_sklearn.load_model.call_args_list
        assert calls[0] == call("models:/governance_impact_scorer@champion")

    def test_load_model_uri_uses_registry_name_and_candidate_alias(self, manager):
        import types

        mock_sklearn, mock_client_cls, _, _, _, _, _ = _make_mlflow_mocks()
        fake_mlflow = types.ModuleType("mlflow")
        fake_mlflow.sklearn = mock_sklearn
        fake_tracking = types.ModuleType("mlflow.tracking")
        fake_tracking.MlflowClient = mock_client_cls

        with patch.dict(
            sys.modules,
            {
                "mlflow": fake_mlflow,
                "mlflow.sklearn": mock_sklearn,
                "mlflow.tracking": fake_tracking,
            },
        ):
            manager.load_models()

        calls = mock_sklearn.load_model.call_args_list
        assert calls[1] == call("models:/governance_impact_scorer@candidate")


# ===========================================================================
# 4. load_models — each error type causes return False
# ===========================================================================


def _run_load_models_with_error(error_cls):
    """Helper: trigger load_models with a given exception raised during import."""
    import types

    mock_sklearn = MagicMock()
    mock_sklearn.load_model.side_effect = error_cls("simulated error")

    mock_client_instance = MagicMock()
    mock_client_instance.get_model_version_by_alias.side_effect = error_cls("simulated error")
    mock_client_cls = MagicMock(return_value=mock_client_instance)

    fake_mlflow = types.ModuleType("mlflow")
    fake_mlflow.sklearn = mock_sklearn
    fake_tracking = types.ModuleType("mlflow.tracking")
    fake_tracking.MlflowClient = mock_client_cls

    manager = ABTestModelManager("champion", "candidate", "registry")
    with patch.dict(
        sys.modules,
        {"mlflow": fake_mlflow, "mlflow.sklearn": mock_sklearn, "mlflow.tracking": fake_tracking},
    ):
        result = manager.load_models()
    return result, manager


class TestLoadModelsErrorHandling:
    @pytest.mark.parametrize(
        "error_cls",
        [
            ImportError,
            ModuleNotFoundError,
            AttributeError,
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
        ],
    )
    def test_returns_false_on_error(self, error_cls):
        result, _ = _run_load_models_with_error(error_cls)
        assert result is False

    @pytest.mark.parametrize(
        "error_cls",
        [
            ImportError,
            ModuleNotFoundError,
            AttributeError,
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
        ],
    )
    def test_models_loaded_false_on_error(self, error_cls):
        _, manager = _run_load_models_with_error(error_cls)
        assert manager.models_loaded is False

    @pytest.mark.parametrize(
        "error_cls",
        [
            ImportError,
            ModuleNotFoundError,
            AttributeError,
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
        ],
    )
    def test_is_ready_false_on_error(self, error_cls):
        _, manager = _run_load_models_with_error(error_cls)
        assert manager.is_ready() is False

    def test_error_logged(self, manager, caplog):
        """Verify logger.error is called when load fails."""
        import types

        mock_sklearn = MagicMock()
        mock_sklearn.load_model.side_effect = RuntimeError("boom")
        mock_client_instance = MagicMock()
        mock_client_instance.get_model_version_by_alias.side_effect = RuntimeError("boom")
        mock_client_cls = MagicMock(return_value=mock_client_instance)
        fake_mlflow = types.ModuleType("mlflow")
        fake_mlflow.sklearn = mock_sklearn
        fake_tracking = types.ModuleType("mlflow.tracking")
        fake_tracking.MlflowClient = mock_client_cls

        with caplog.at_level(
            logging.ERROR, logger="enhanced_agent_bus.ab_testing_infra.model_manager"
        ):
            with patch.dict(
                sys.modules,
                {
                    "mlflow": fake_mlflow,
                    "mlflow.sklearn": mock_sklearn,
                    "mlflow.tracking": fake_tracking,
                },
            ):
                manager.load_models()

        assert any("Failed to load models" in r.message for r in caplog.records)

    def test_import_error_on_mlflow_itself(self, manager):
        """If mlflow cannot be imported at all, load_models returns False."""
        with patch.dict(
            sys.modules, {"mlflow": None, "mlflow.sklearn": None, "mlflow.tracking": None}
        ):
            result = manager.load_models()
        assert result is False

    def test_models_still_none_after_error(self, manager):
        _result, m = _run_load_models_with_error(RuntimeError)
        assert m.champion_model is None
        assert m.candidate_model is None


# ===========================================================================
# 5. set_champion_model
# ===========================================================================


class TestSetChampionModel:
    def test_sets_champion_model(self, manager):
        model = _mock_model()
        manager.set_champion_model(model)
        assert manager.champion_model is model

    def test_sets_champion_version_when_provided(self, manager):
        model = _mock_model()
        manager.set_champion_model(model, version="v3")
        assert manager.champion_version == "v3"

    def test_sets_champion_version_none_by_default(self, manager):
        model = _mock_model()
        manager.set_champion_model(model)
        assert manager.champion_version is None

    def test_sets_champion_version_integer(self, manager):
        model = _mock_model()
        manager.set_champion_model(model, version=7)
        assert manager.champion_version == 7

    def test_models_loaded_false_when_no_candidate(self, manager):
        """models_loaded stays False if candidate is not yet set."""
        manager.set_champion_model(_mock_model())
        assert manager.models_loaded is False

    def test_models_loaded_true_when_candidate_already_set(self, manager):
        """After candidate is set, adding champion flips models_loaded."""
        manager.candidate_model = _mock_model()
        manager.set_champion_model(_mock_model())
        assert manager.models_loaded is True

    def test_models_loaded_stays_true_if_already_true(self, manager):
        """If models_loaded was already True, it stays True."""
        manager.models_loaded = True
        manager.set_champion_model(_mock_model())
        assert manager.models_loaded is True

    def test_overwrites_existing_champion(self, manager):
        first_model = _mock_model("first")
        second_model = _mock_model("second")
        manager.set_champion_model(first_model)
        manager.set_champion_model(second_model)
        assert manager.champion_model is second_model


# ===========================================================================
# 6. set_candidate_model
# ===========================================================================


class TestSetCandidateModel:
    def test_sets_candidate_model(self, manager):
        model = _mock_model()
        manager.set_candidate_model(model)
        assert manager.candidate_model is model

    def test_sets_candidate_version_when_provided(self, manager):
        model = _mock_model()
        manager.set_candidate_model(model, version="v9")
        assert manager.candidate_version == "v9"

    def test_sets_candidate_version_none_by_default(self, manager):
        model = _mock_model()
        manager.set_candidate_model(model)
        assert manager.candidate_version is None

    def test_sets_candidate_version_integer(self, manager):
        model = _mock_model()
        manager.set_candidate_model(model, version=42)
        assert manager.candidate_version == 42

    def test_models_loaded_false_when_no_champion(self, manager):
        manager.set_candidate_model(_mock_model())
        assert manager.models_loaded is False

    def test_models_loaded_true_when_champion_already_set(self, manager):
        manager.champion_model = _mock_model()
        manager.set_candidate_model(_mock_model())
        assert manager.models_loaded is True

    def test_models_loaded_stays_true_if_already_true(self, manager):
        manager.models_loaded = True
        manager.set_candidate_model(_mock_model())
        assert manager.models_loaded is True

    def test_overwrites_existing_candidate(self, manager):
        first_model = _mock_model("first")
        second_model = _mock_model("second")
        manager.set_candidate_model(first_model)
        manager.set_candidate_model(second_model)
        assert manager.candidate_model is second_model


# ===========================================================================
# 7. get_champion_model / get_candidate_model
# ===========================================================================


class TestGetModels:
    def test_get_champion_returns_none_initially(self, manager):
        assert manager.get_champion_model() is None

    def test_get_candidate_returns_none_initially(self, manager):
        assert manager.get_candidate_model() is None

    def test_get_champion_returns_set_model(self, manager):
        model = _mock_model()
        manager.champion_model = model
        assert manager.get_champion_model() is model

    def test_get_candidate_returns_set_model(self, manager):
        model = _mock_model()
        manager.candidate_model = model
        assert manager.get_candidate_model() is model

    def test_get_champion_independent_of_candidate(self, manager):
        champ = _mock_model("champ")
        cand = _mock_model("cand")
        manager.champion_model = champ
        manager.candidate_model = cand
        assert manager.get_champion_model() is champ
        assert manager.get_candidate_model() is cand


# ===========================================================================
# 8. is_ready
# ===========================================================================


class TestIsReady:
    def test_false_when_no_models_no_flag(self, manager):
        assert manager.is_ready() is False

    def test_false_when_flag_true_but_both_models_none(self, manager):
        manager.models_loaded = True
        assert manager.is_ready() is False

    def test_false_when_flag_true_champion_set_candidate_none(self, manager):
        manager.models_loaded = True
        manager.champion_model = _mock_model()
        assert manager.is_ready() is False

    def test_false_when_flag_true_candidate_set_champion_none(self, manager):
        manager.models_loaded = True
        manager.candidate_model = _mock_model()
        assert manager.is_ready() is False

    def test_false_when_both_models_set_flag_false(self, manager):
        manager.champion_model = _mock_model()
        manager.candidate_model = _mock_model()
        manager.models_loaded = False
        assert manager.is_ready() is False

    def test_true_when_flag_true_and_both_models_set(self, manager):
        manager.models_loaded = True
        manager.champion_model = _mock_model()
        manager.candidate_model = _mock_model()
        assert manager.is_ready() is True

    def test_true_after_both_set_via_setters(self, manager):
        manager.champion_model = _mock_model()  # pre-set so candidate setter triggers flag
        manager.set_candidate_model(_mock_model(), version=1)
        # models_loaded only becomes True if champion was already present
        assert manager.models_loaded is True
        assert manager.is_ready() is True

    def test_true_after_both_set_reverse_order(self, manager):
        manager.candidate_model = _mock_model()
        manager.set_champion_model(_mock_model(), version=1)
        assert manager.models_loaded is True
        assert manager.is_ready() is True


# ===========================================================================
# 9. Interaction / integration-style
# ===========================================================================


class TestInteraction:
    def test_full_manual_setup_then_ready(self, manager):
        manager.set_champion_model(_mock_model(), version="1")
        assert manager.is_ready() is False  # candidate still missing
        manager.candidate_model = _mock_model()
        manager.set_candidate_model(manager.candidate_model, version="2")
        # After first setter with no partner, models_loaded may be False —
        # both setters re-evaluate; set champion again to trigger
        manager.set_champion_model(_mock_model(), version="1")
        assert manager.is_ready() is True

    def test_replacing_models_does_not_break_ready(self, manager):
        manager.models_loaded = True
        manager.champion_model = _mock_model()
        manager.candidate_model = _mock_model()
        assert manager.is_ready() is True
        # Replace champion
        manager.set_champion_model(_mock_model(), version="99")
        # models_loaded stays True (was True)
        assert manager.is_ready() is True

    def test_set_champion_version_string_and_int(self):
        m1 = ABTestModelManager("a", "b", "r")
        m1.set_champion_model(_mock_model(), version="v1")
        assert isinstance(m1.champion_version, str)

        m2 = ABTestModelManager("a", "b", "r")
        m2.set_champion_model(_mock_model(), version=1)
        assert isinstance(m2.champion_version, int)

    def test_multiple_instances_are_independent(self):
        m1 = ABTestModelManager("a", "b", "r1")
        m2 = ABTestModelManager("x", "y", "r2")
        m1.set_champion_model(_mock_model())
        assert m2.champion_model is None
