def encode_noid(num=None):
    """Encode an integer as a NOID string, including final checksum
    character."""
    if num is None:
        num = random_num()
    digits = _digits(num)
    digits.append(_checksum(digits))
    return "".join([ALPHABET[digit] for digit in digits])
