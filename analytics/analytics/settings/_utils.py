def string_to_list(value: str, separator=",") -> list:
    """Attempt to parse a string as a list of separated values."""
    split_value = [v.strip() for v in value.strip().split(separator)]
    return list(filter(None, split_value))


def string_to_bool(value: str) -> bool:
    true_values = ("yes", "y", "true", "1")
    false_values = ("no", "n", "false", "0", "")

    normalized_value = value.strip().lower()
    if normalized_value in true_values:
        return True
    if normalized_value in false_values:
        return False

    raise ValueError("Cannot interpret " "boolean value {!r}".format(value))
