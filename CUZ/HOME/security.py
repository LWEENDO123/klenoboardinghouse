# HOME/security.py
"""
This module is a thin wrapper around core/security.py.
All token creation, validation, and role helpers are centralized in core/security.
Do NOT redefine SECRET_KEY or duplicate get_current_user here.
"""

from CUZ.core.security import (
    create_access_token,
    get_current_user,
    get_admin_credentials,
    get_current_admin,
    get_current_landlord,
    get_premium_student,
    get_student_or_admin,
    get_premium_student_or_admin,
    get_admin_or_landlord,
    get_student_union_or_higher,
    create_location_token,
    decode_location_token,
    
)
