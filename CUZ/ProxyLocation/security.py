from fastapi import Depends, HTTPException
from CUZ.USERS.security import (
    get_current_user,
    get_student_or_admin,
    get_premium_student_or_admin,
)
