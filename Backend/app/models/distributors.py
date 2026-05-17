from typing import Optional, List
from pydantic import BaseModel, Field


class Model(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    name: str = ""
    distributor_id: Optional[str] = None
    model_type: str = ""
    description: str = ""

    class Config:
        populate_by_name = True


class Distributor(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    name: str = ""
    description: str = ""
    models: List[Model] = Field(default_factory=list)

    class Config:
        populate_by_name = True
