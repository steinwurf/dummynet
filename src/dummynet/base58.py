# Base58 alphabet
BASE58_ALPHABET: str = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def int_to_base58(num: int) -> str:
    base = len(BASE58_ALPHABET)
    if num == 0:
        return BASE58_ALPHABET[0]
    chars = []
    while num > 0:
        num, rem = divmod(num, base)
        chars.append(BASE58_ALPHABET[rem])
    return "".join(reversed(chars))


def base58_to_int(s: str) -> int:
    base = len(BASE58_ALPHABET)
    num = 0
    for char in s:
        num = num * base + BASE58_ALPHABET.index(char)
    return num
