#!/usr/bin/env python3
"""PAM authentication via ctypes (no sudo, no extra packages).

The lock screen uses this so that exactly the account password is accepted,
through the same PAM stack (pam_unix) that the greeter uses.

The response array and its strings are allocated with libc calloc/strdup,
because PAM frees them with free().
"""
import ctypes
import getpass
import os

PAM_SUCCESS = 0
PAM_PROMPT_ECHO_OFF = 1
PAM_PROMPT_ECHO_ON = 2

_libpam = ctypes.CDLL("libpam.so.0")
_libc = ctypes.CDLL("libc.so.6")
_libc.calloc.restype = ctypes.c_void_p
_libc.calloc.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
_libc.strdup.restype = ctypes.c_void_p
_libc.strdup.argtypes = [ctypes.c_char_p]


class PamMessage(ctypes.Structure):
    _fields_ = [("msg_style", ctypes.c_int), ("msg", ctypes.c_char_p)]


class PamResponse(ctypes.Structure):
    _fields_ = [("resp", ctypes.c_void_p), ("resp_retcode", ctypes.c_int)]


CONV_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.POINTER(PamMessage)),
    ctypes.POINTER(ctypes.POINTER(PamResponse)),
    ctypes.c_void_p,
)


class PamConv(ctypes.Structure):
    _fields_ = [("conv", CONV_FUNC), ("appdata_ptr", ctypes.c_void_p)]


_libpam.pam_start.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                              ctypes.POINTER(PamConv),
                              ctypes.POINTER(ctypes.c_void_p)]
_libpam.pam_start.restype = ctypes.c_int
_libpam.pam_authenticate.argtypes = [ctypes.c_void_p, ctypes.c_int]
_libpam.pam_authenticate.restype = ctypes.c_int
_libpam.pam_acct_mgmt.argtypes = [ctypes.c_void_p, ctypes.c_int]
_libpam.pam_acct_mgmt.restype = ctypes.c_int
_libpam.pam_end.argtypes = [ctypes.c_void_p, ctypes.c_int]
_libpam.pam_end.restype = ctypes.c_int

_current = {"pw": b""}


def _conv(n, messages, responses, _data):
    arr = _libc.calloc(n, ctypes.sizeof(PamResponse))
    ptr = ctypes.cast(arr, ctypes.POINTER(PamResponse))
    for i in range(n):
        style = messages[i].contents.msg_style
        if style in (PAM_PROMPT_ECHO_OFF, PAM_PROMPT_ECHO_ON):
            ptr[i].resp = _libc.strdup(_current["pw"])
        else:
            ptr[i].resp = None
        ptr[i].resp_retcode = 0
    responses[0] = ptr
    return PAM_SUCCESS


_CONV = PamConv(CONV_FUNC(_conv), None)


def authenticate(password, service="login", user=None):
    """Return True when PAM accepts user + password."""
    if not password:
        return False
    user = user or getpass.getuser() or os.environ.get("USER", "")
    if not user:
        return False

    _current["pw"] = password.encode()
    handle = ctypes.c_void_p()
    rc = _libpam.pam_start(service.encode(), user.encode(),
                           ctypes.byref(_CONV), ctypes.byref(handle))
    if rc != PAM_SUCCESS:
        return False
    try:
        rc = _libpam.pam_authenticate(handle, 0)
        if rc != PAM_SUCCESS:
            return False
        rc = _libpam.pam_acct_mgmt(handle, 0)
        return rc == PAM_SUCCESS
    finally:
        _libpam.pam_end(handle, rc)


if __name__ == "__main__":
    import sys

    print("user:", getpass.getuser())
    print("result:", authenticate(sys.argv[1] if len(sys.argv) > 1 else ""))
