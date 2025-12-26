from .base import DocumentParser
from .xp import XPParser
from .danfe import DanfeParser
from .itau import ItauParser
from .generic import GenericLLMParser

class ParserFactory:
    @staticmethod
    def get_parser(text: str) -> DocumentParser:
        if ItauParser.detect(text):
            return ItauParser()

        if XPParser.detect(text):
            return XPParser()
        
        if DanfeParser.detect(text):
            return DanfeParser()
        
        return GenericLLMParser()
