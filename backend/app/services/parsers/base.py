from abc import ABC, abstractmethod
from typing import Any, Dict

class DocumentParser(ABC):
    @abstractmethod
    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extracts structured data from raw text.
        Returns a dictionary with keys: doc_type, date, amount, merchant_or_bank.
        """
        pass

    @classmethod
    @abstractmethod
    def detect(cls, text: str) -> bool:
        """
        Returns True if this parser is suitable for the given text.
        """
        pass
