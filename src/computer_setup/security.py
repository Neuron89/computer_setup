"""
Utilities for encrypting and decrypting short secrets using the Windows
Data Protection API (DPAPI).
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import POINTER, Structure, byref, c_void_p
from ctypes.wintypes import BOOL, DWORD, LPWSTR

CRYPTPROTECT_LOCAL_MACHINE = 0x4


class DATA_BLOB(Structure):
    _fields_ = [("cbData", DWORD), ("pbData", POINTER(ctypes.c_ubyte))]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _raise_last_error() -> None:
    code = ctypes.get_last_error()
    raise OSError(code, ctypes.FormatError(code))


def _to_blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buf = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buf, POINTER(ctypes.c_ubyte)))
    return blob, buf


def _from_blob(blob: DATA_BLOB) -> bytes:
    buffer = ctypes.cast(blob.pbData, POINTER(ctypes.c_char))
    try:
        return ctypes.string_at(buffer, blob.cbData)
    finally:
        _kernel32.LocalFree(blob.pbData)


def protect_string(secret: str) -> str:
    """
    Encrypt *secret* using the local machine DPAPI scope and return it as a
    Base64 string suitable for storage.
    """

    if not isinstance(secret, str):
        raise TypeError("secret must be a string")

    data = secret.encode("utf-16-le")
    in_blob, _buffer = _to_blob(data)
    out_blob = DATA_BLOB()

    result = _crypt32.CryptProtectData(
        byref(in_blob),
        LPWSTR("computer-setup"),
        None,
        None,
        None,
        CRYPTPROTECT_LOCAL_MACHINE,
        byref(out_blob),
    )
    if result != BOOL(True):
        _raise_last_error()

    protected = _from_blob(out_blob)
    return base64.b64encode(protected).decode("ascii")


def unprotect_string(protected: str) -> str:
    """
    Decrypt a Base64 encoded string produced by :func:`protect_string`.
    """

    if not isinstance(protected, str):
        raise TypeError("protected must be a string")

    raw = base64.b64decode(protected.encode("ascii"))
    in_blob, _buffer = _to_blob(raw)
    out_blob = DATA_BLOB()
    description = LPWSTR()

    result = _crypt32.CryptUnprotectData(
        byref(in_blob),
        byref(description),
        None,
        None,
        None,
        0,
        byref(out_blob),
    )
    if result != BOOL(True):
        _raise_last_error()

    try:
        decrypted = _from_blob(out_blob)
    finally:
        if description:
            _kernel32.LocalFree(description)

    return decrypted.decode("utf-16-le")

