from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Any
class Signup(BaseModel): name:str=Field(min_length=2,max_length=120); email:EmailStr; password:str=Field(min_length=8); role:Literal['buyer','vendor']='buyer'; vendor_name:str|None=None
class Login(BaseModel): email:EmailStr; password:str
class ProductIn(BaseModel): name:str; brand:str; model:str; category:Literal['panel','inverter','battery','package','accessory']; specs:dict[str,Any]={}; price_min:float=Field(gt=0); price_max:float=Field(gt=0); stock:int=Field(ge=0); description:str=''; image:str=''
class OrderIn(BaseModel): items:list[dict[str,Any]]=Field(min_length=1)
class ChatIn(BaseModel): message:str=Field(min_length=1,max_length=4000); thread_id:str='default'
class ReturnIn(BaseModel): order_id:int; reason:str=Field(min_length=5,max_length=1000); amount:float=Field(gt=0)
class PolicyAnswer(BaseModel): answer:str; citations:list[dict[str,str]]=[]; sufficient_evidence:bool
class CaseRequest(BaseModel): order_id:int; reason:str; amount:float
