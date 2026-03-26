from __future__ import annotations

import importlib

from ..observability.structured_logging import get_logger

logger = get_logger(__name__)
MODEL_LOAD_ERRORS = (
    ImportError,
    ModuleNotFoundError,
    AttributeError,
    RuntimeError,
    ValueError,
    TypeError,
    OSError,
)


class ABTestModelManager:
    def __init__(self, champion_alias: str, candidate_alias: str, model_registry_name: str) -> None:
        self.champion_alias = champion_alias
        self.candidate_alias = candidate_alias
        self.model_registry_name = model_registry_name
        self.champion_model = None
        self.candidate_model = None
        self.champion_version = None
        self.candidate_version = None
        self.models_loaded = False

    def load_models(self) -> bool:
        try:
            mlflow = importlib.import_module("mlflow")
            tracking = importlib.import_module("mlflow.tracking")
            client = tracking.MlflowClient()
            champion_mv = client.get_model_version_by_alias(
                self.model_registry_name, self.champion_alias
            )
            candidate_mv = client.get_model_version_by_alias(
                self.model_registry_name, self.candidate_alias
            )
            self.champion_model = mlflow.sklearn.load_model(
                f"models:/{self.model_registry_name}@{self.champion_alias}"
            )
            self.candidate_model = mlflow.sklearn.load_model(
                f"models:/{self.model_registry_name}@{self.candidate_alias}"
            )
            self.champion_version = champion_mv.version
            self.candidate_version = candidate_mv.version
            self.models_loaded = True
            return True
        except MODEL_LOAD_ERRORS as exc:
            logger.error("Failed to load models: %s", exc)
            self.models_loaded = False
            self.champion_model = None
            self.candidate_model = None
            return False

    def set_champion_model(self, model, version=None) -> None:
        self.champion_model = model
        self.champion_version = version
        if self.models_loaded or self.candidate_model is not None:
            self.models_loaded = True

    def set_candidate_model(self, model, version=None) -> None:
        self.candidate_model = model
        self.candidate_version = version
        if self.models_loaded or self.champion_model is not None:
            self.models_loaded = True

    def get_champion_model(self):
        return self.champion_model

    def get_candidate_model(self):
        return self.candidate_model

    def is_ready(self) -> bool:
        return bool(
            self.models_loaded
            and self.champion_model is not None
            and self.candidate_model is not None
        )
