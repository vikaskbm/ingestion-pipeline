from abc import ABC, abstractmethod
from typing import Any


class BaseEvaluator(ABC):
    @property
    @abstractmethod
    def evaluator_id(self) -> str:
        pass

    @property
    @abstractmethod
    def evaluator_name(self) -> str:
        pass

    @abstractmethod
    def evaluate(self, conversation: dict[str, Any]) -> dict[str, Any]:
        pass
