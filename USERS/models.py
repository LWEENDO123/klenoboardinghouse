from pydantic import BaseModel, EmailStr, constr, validator, Field
from typing import Literal, Optional
from typing import Annotated


# ✅ Inline constraints using Annotated
NameStr = Annotated[str, constr(min_length=1, max_length=25, pattern=r'^[A-Za-z]+$')]
PasswordStr = Annotated[str, constr(min_length=8, max_length=25)]
PhoneStr = Annotated[str, constr(max_length=10, pattern=r'^\d+$')]




class StudentSignup(BaseModel):
    first_name: NameStr
    last_name: NameStr
    university: str
    email: EmailStr
    password: PasswordStr
    phone_number: PhoneStr
    pinned: str
    referal_code: str
    role: Literal["free"] = "free"
    

class LandlordSignup(BaseModel):
    first_name: NameStr
    last_name: NameStr
    boarding_house: str
    email: EmailStr
    password: PasswordStr
    phone_number: PhoneStr
    university:str

class LoginInput(BaseModel):
    email: EmailStr
    password: PasswordStr
    university: Optional[str] = None

    @validator("email", "password", pre=True)
    def strip_and_check_empty(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Field cannot be empty")
        return v


