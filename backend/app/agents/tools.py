"""Six typed marketplace tools from MarketWise, adapted to SolarWise solar orders."""
from pydantic import BaseModel, Field
import re, json
from sqlalchemy.orm import Session
from ..models import Order,ReturnCase
from .graph import retrieve_policy
class SearchPoliciesInput(BaseModel): question:str; vendor:str|None=None
class GetOrderInput(BaseModel): order_id:int
class ListMyOrdersInput(BaseModel): status:str|None=None
class CheckEligibilityInput(BaseModel): order_id:int; reason:str
class CreateReturnInput(BaseModel): order_id:int; reason:str; amount:float=Field(gt=0)
class VendorCasesInput(BaseModel): status:str|None=None

def search_policies(db:Session, args:SearchPoliciesInput):
    # Vendor filter is resolved from trusted order context by caller; never from arbitrary buyer text.
    return [{'vendor':p['vendor'],'document':p['document'],'section':p['section'],'text':p['text']} for p in retrieve_policy(args.question,args.vendor)]

def get_order(db:Session, buyer_id:int, args:GetOrderInput):
    o=db.query(Order).filter_by(id=args.order_id,buyer_id=buyer_id).first()
    if not o:return {'error':'Order not found or not owned by current buyer'}
    return {'id':o.id,'status':o.status,'total':o.total,'items':o.items_json,'vendor_id':o.vendor_id}

def list_my_orders(db:Session,buyer_id:int,args:ListMyOrdersInput):
    q=db.query(Order).filter_by(buyer_id=buyer_id)
    if args.status:q=q.filter_by(status=args.status)
    return [{'id':o.id,'status':o.status,'total':o.total} for o in q.order_by(Order.id.desc()).limit(20)]

def check_return_eligibility(db:Session,buyer_id:int,args:CheckEligibilityInput):
    o=db.query(Order).filter_by(id=args.order_id,buyer_id=buyer_id).first()
    if not o:return {'eligible':False,'reason':'Order not found or not owned by current buyer'}
    existing=db.query(ReturnCase).filter_by(order_id=o.id,buyer_id=buyer_id).first()
    if existing:return {'eligible':False,'reason':f'Existing case #{existing.id} is {existing.status}'}
    return {'eligible':o.status in ('delivered','completed'),'reason':'Order must be delivered before return review' if o.status not in ('delivered','completed') else 'Eligible for policy review; final decision depends on vendor policy and inspection'}

def create_return_request(db:Session,buyer_id:int,args:CreateReturnInput,threshold:float=2000):
    o=db.query(Order).filter_by(id=args.order_id,buyer_id=buyer_id).first()
    if not o:return {'error':'Order not found or not owned by current buyer'}
    if args.amount>o.total:return {'error':'Requested amount exceeds order total'}
    if db.query(ReturnCase).filter_by(order_id=o.id,buyer_id=buyer_id).filter(ReturnCase.status.in_(['OPEN','WAITING_FOR_APPROVAL','APPROVED'])).first():return {'error':'Duplicate request blocked'}
    status='WAITING_FOR_APPROVAL' if args.amount>threshold else 'OPEN'
    c=ReturnCase(order_id=o.id,buyer_id=buyer_id,vendor_id=o.vendor_id,reason=args.reason,amount=args.amount,status=status);db.add(c);db.commit();db.refresh(c)
    return {'case_id':c.id,'status':c.status,'approval_required':status=='WAITING_FOR_APPROVAL'}

def get_vendor_cases(db:Session,vendor_id:int,args:VendorCasesInput):
    q=db.query(ReturnCase).filter_by(vendor_id=vendor_id)
    if args.status:q=q.filter_by(status=args.status)
    return [{'id':c.id,'order_id':c.order_id,'status':c.status,'amount':c.amount,'reason':c.reason} for c in q.order_by(ReturnCase.id.desc()).limit(50)]

def search_products(db:Session, question:str, limit:int=100):
    """Simple catalog search; product facts and prices come from the database, not the LLM."""
    from ..models import Product
    products=db.query(Product).filter(Product.active.is_(True), Product.stock > 0).all()
    q=question.lower()
    terms=[t for t in re.findall(r"[a-z0-9]+|[\u0980-\u09ff]+", q) if len(t)>1]
    aliases={
        'panel':['panel','panels','প্যানেল','মডিউল'],
        'inverter':['inverter','ইনভার্টার'],
        'battery':['battery','ব্যাটারি'],
        'package':['package','system','প্যাকেজ','সিস্টেম'],
    }
    expanded=set(terms)
    for key,vals in aliases.items():
        if any(v in q for v in vals): expanded.add(key)
    scored=[]
    for product in products:
        hay=(product.name+' '+product.brand+' '+product.model+' '+product.category+' '+product.specs+' '+product.description).lower()
        score=sum(1 for term in expanded if term in hay)
        if product.category in expanded: score+=4
        if score: scored.append((score,product))
    scored.sort(key=lambda x:x[0],reverse=True)
    # A broad solar recommendation should still show the catalog instead of a false policy-evidence error.
    if not scored and any(x in q for x in ['solar','সোলার','recommend','best','দাম','price']):
        scored=[(0,p) for p in products]
    result=[]
    for _,p in scored[:limit]:
        result.append({'name':p.name,'brand':p.brand,'model':p.model,'category':p.category,'specs':p.specs,'price_min':p.price_min,'price_max':p.price_max})
    return result
