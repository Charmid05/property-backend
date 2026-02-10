from enum import Enum

from os import path



class EnumWithChoices(Enum):

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]
    
def generate_document_filepath(instance, filename: str) -> str:
    filename, extension = path.splitext(filename)
    return f"{instance.__class__.__name__.lower()}/{filename}_{instance.id or ''}{extension}"
