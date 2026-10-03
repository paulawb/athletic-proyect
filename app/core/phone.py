import re


def normalize_phone(value: str) -> str:
    normalized = re.sub(r"[\s().-]", "", value)
    if not re.fullmatch(r"\+?[0-9]{7,15}", normalized):
        raise ValueError("Ingresa un teléfono válido de 7 a 15 dígitos, opcionalmente con prefijo +")
    return normalized
