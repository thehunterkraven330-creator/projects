"""Phone numbers in the international form couriers want ('+2348122340000')."""


def to_e164(phone: str, country: str) -> str:
    """'0812 234 0000' + 'NG' -> '+2348122340000'. The number must be a real one for that country (a leading '+' means it names
    its own country). Raises ValueError with a message safe to show the person."""
    import phonenumbers  # in requirements.txt

    try:
        number = phonenumbers.parse(phone, None if phone.strip().startswith("+") else country.upper())
    except phonenumbers.NumberParseException as exc:
        raise ValueError("That phone number doesn't look right.") from exc
    if not phonenumbers.is_valid_number(number):
        raise ValueError("That phone number doesn't look right for the country selected.")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
