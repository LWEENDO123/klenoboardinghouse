# Store/security.py
"""
This module simply re‑exports the security dependencies from core/security
so Store endpoints can use the same JWT validation and role checks.
"""

from CUZ.core.security import (
    get_current_user,
    get_current_admin,
    get_current_landlord,
    get_premium_student,
    get_premium_student_or_admin,
    get_admin_or_landlord,
    get_student_or_admin,
    get_student_union_or_higher,
)
