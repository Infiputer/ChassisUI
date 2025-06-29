from pydantic import BaseModel, EmailStr, constr

class UserSignup(BaseModel):
    email: EmailStr
    password: constr(min_length=8)
    name: str = "Unknown User"  # Optional field with default value

class UserLogin(BaseModel):
    email: EmailStr
    password: constr(min_length=8)

class MessageCreate(BaseModel):
    prompt: str

class ModelBase(BaseModel):
    name: str
    short_description: str
    long_description: str

class ModelCreate(ModelBase):
    pass

class ModelUpdate(ModelBase):
    pass