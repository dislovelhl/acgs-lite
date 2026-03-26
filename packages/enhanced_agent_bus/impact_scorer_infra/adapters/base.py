"""
Impact scoring adapters for backend execution.
Constitutional Hash: 608508a9bd224290
"""

from abc import ABC, abstractmethod


class BaseImpactAdapter(ABC):
    @abstractmethod
    def execute(self, _model_input: object) -> object:
        pass


class ONNXImpactAdapter(BaseImpactAdapter):
    def execute(self, _model_input: object) -> object:
        # ONNX runtime execution logic
        pass


class PyTorchImpactAdapter(BaseImpactAdapter):
    def execute(self, _model_input: object) -> object:
        # PyTorch model execution logic
        pass
