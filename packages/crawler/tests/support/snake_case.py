import re


def snake_case(class_name: str) -> str:
    """The name of the file a port or a double lives in, from its class's."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
