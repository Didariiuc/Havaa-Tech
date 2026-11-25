import json, uuid, ast
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc, inspect, text
from .config import settings
from .db import Base,engine,get_db
from .models import User,Product,Order,ReturnCase,ChatMessage,Preference
from .schemas import Signup,Login,ProductIn,OrderIn,ChatIn,ReturnIn
from .security import hash_password,verify_password,token_for,current_user,require_roles
from .agents.graph import run_agent,retrieve_policy
Base.metadata.create_all(engine)
# Lightweight additive migration for existing SQLite demo databases.
# Keeps existing orders and users; no database reset is required.
with engine.begin() as conn:
    if engine.dialect.name == 'sqlite':
        existing = {col['name'] for col in inspect(engine).get_columns('orders')}
        for col_name, col_type in [
            ('dispatched_at', 'DATETIME'),
            ('estimated_delivery_at', 'DATETIME'),
            ('courier_name', 'VARCHAR(120)'),
            ('tracking_number', 'VARCHAR(120)'),
        ]:
            if col_name not in existing:
                conn.execute(text(f'ALTER TABLE orders ADD COLUMN {col_name} {col_type}'))
app=FastAPI(title=settings.app_name,version='1.0.0',description='Solar multi-vendor commerce and AI assistant')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
def user_out(u): return {'id':u.id,'name':u.name,'email':u.email,'role':u.role,'vendor_name':u.vendor_name}
def product_out(p):
    try: specs=ast.literal_eval(p.specs)
    except Exception: specs={}
    return {'id':p.id,'name':p.name,'brand':p.brand,'model':p.model,'category':p.category,'specs':specs,'price_min':p.price_min,'price_max':p.price_max,'stock':p.stock,'description':p.description,'image':p.image,'vendor_id':p.vendor_id}
@app.get('/api/health')
def health(): return {'ok':True,'service':'Havaa Tech','model':settings.primary_model}
@app.post('/api/auth/signup')
def signup(data:Signup,db:Session=Depends(get_db)):
    if db.query(User).filter_by(email=data.email).first(): raise HTTPException(409,'Email already registered')
    u=User(name=data.name,email=data.email,password_hash=hash_password(data.password),role=data.role,vendor_name=data.vendor_name if data.role=='vendor' else None)
    db.add(u);db.commit();db.refresh(u);return {'access_token':token_for(u),'token_type':'bearer','user':user_out(u)}
@app.post('/api/auth/login')
def login(data:Login,db:Session=Depends(get_db)):
    u=db.query(User).filter_by(email=data.email).first()
    if not u or not verify_password(data.password,u.password_hash): raise HTTPException(401,'Incorrect email or password')
    return {'access_token':token_for(u),'token_type':'bearer','user':user_out(u)}
@app.get('/api/auth/me')
def me(u:User=Depends(current_user)): return user_out(u)
@app.get('/api/products')
def products(category:str|None=None,q:str|None=None,db:Session=Depends(get_db)):
    query=db.query(Product).filter(Product.active==True)
    if category: query=query.filter(Product.category==category)
    if q: query=query.filter((Product.name.ilike(f'%{q}%'))|(Product.brand.ilike(f'%{q}%'))|(Product.model.ilike(f'%{q}%')))
    return [product_out(p) for p in query.order_by(Product.id).all()]
@app.post('/api/products')
def add_product(data:ProductIn,db:Session=Depends(get_db),u:User=Depends(require_roles('vendor','admin'))):
    payload=data.model_dump(); payload['specs']=json.dumps(data.specs); p=Product(**payload,vendor_id=u.id if u.role=='vendor' else None);db.add(p);db.commit();db.refresh(p);return product_out(p)
@app.patch('/api/products/{pid}')
def update_product(pid:int,data:ProductIn,db:Session=Depends(get_db),u:User=Depends(require_roles('vendor','admin'))):
    p=db.get(Product,pid)
    if not p or (u.role=='vendor' and p.vendor_id!=u.id): raise HTTPException(404,'Product not found')
    for k,v in data.model_dump().items(): setattr(p,k,json.dumps(v) if k=='specs' else v)
    db.commit();return product_out(p)
@app.get('/api/vendor/products')
def vendor_products(db:Session=Depends(get_db),u:User=Depends(require_roles('vendor','admin'))):
    q=db.query(Product)
    if u.role=='vendor':q=q.filter(Product.vendor_id==u.id)
    return [product_out(p) for p in q.all()]
@app.post('/api/orders')
def create_order(data:OrderIn,db:Session=Depends(get_db),u:User=Depends(require_roles('buyer'))):
    total=0; lines=[]; vendor_ids=set()
    for item in data.items:
        p=db.get(Product,int(item.get('product_id',0))); qty=int(item.get('quantity',0))
        if not p or not p.active or qty<1 or p.stock<qty: raise HTTPException(400,'Invalid product or insufficient stock')
        price=(p.price_min+p.price_max)/2; total+=price*qty;lines.append({'product_id':p.id,'name':p.name,'quantity':qty,'unit_price':price});p.stock-=qty
        if p.vendor_id:vendor_ids.add(p.vendor_id)
    o=Order(buyer_id=u.id,vendor_id=next(iter(vendor_ids)) if len(vendor_ids)==1 else None,total=total,status='processing',items_json=json.dumps(lines));db.add(o);db.commit();db.refresh(o);return {'id':o.id,'total':o.total,'status':o.status,'items':lines}
@app.get('/api/orders')
def my_orders(db:Session=Depends(get_db),u:User=Depends(current_user)):
    q=db.query(Order)
    if u.role=='buyer':q=q.filter(Order.buyer_id==u.id)
    elif u.role=='vendor':q=q.filter(Order.vendor_id==u.id)
    return [{'id':o.id,'buyer_id':o.buyer_id,'vendor_id':o.vendor_id,'total':o.total,'status':o.status,'items':json.loads(o.items_json),'created_at':o.created_at.isoformat(),'dispatched_at':o.dispatched_at.isoformat() if o.dispatched_at else None,'estimated_delivery_at':o.estimated_delivery_at.isoformat() if o.estimated_delivery_at else None,'courier_name':o.courier_name,'tracking_number':o.tracking_number,'delivered_at':o.delivered_at.isoformat() if o.delivered_at else None} for o in q.order_by(desc(Order.id)).all()]
@app.post('/api/returns')
def create_return(data:ReturnIn,db:Session=Depends(get_db),u:User=Depends(require_roles('buyer'))):
    o=db.get(Order,data.order_id)
    if not o or o.buyer_id!=u.id: raise HTTPException(404,'Order not found')
    existing=db.query(ReturnCase).filter_by(order_id=o.id,buyer_id=u.id).filter(ReturnCase.status.in_(['OPEN','WAITING_FOR_APPROVAL','APPROVED'])).first()
    if existing: raise HTTPException(409,'A return request already exists for this order')
    if data.amount>o.total: raise HTTPException(400,'Requested amount cannot exceed order total')
    status='WAITING_FOR_APPROVAL' if data.amount>settings.refund_approval_threshold else 'OPEN'
    case=ReturnCase(order_id=o.id,buyer_id=u.id,vendor_id=o.vendor_id,reason=data.reason,amount=data.amount,status=status)
    db.add(case);db.commit();db.refresh(case);return {'case_id':case.id,'status':case.status,'approval_required':status=='WAITING_FOR_APPROVAL'}
@app.get('/api/returns')
def returns(db:Session=Depends(get_db),u:User=Depends(current_user)):
    q=db.query(ReturnCase)
    if u.role=='buyer':q=q.filter(ReturnCase.buyer_id==u.id)
    elif u.role=='vendor':q=q.filter(ReturnCase.vendor_id==u.id)
    return [{'id':c.id,'order_id':c.order_id,'buyer_id':c.buyer_id,'vendor_id':c.vendor_id,'reason':c.reason,'amount':c.amount,'status':c.status,'created_at':c.created_at.isoformat()} for c in q.order_by(desc(ReturnCase.id)).all()]
@app.post('/api/admin/returns/{cid}/decision')
def decide_return(cid:int,decision:str,db:Session=Depends(get_db),u:User=Depends(require_roles('admin'))):
    if decision not in ('approve','reject','revise'):raise HTTPException(400,'Decision must be approve, reject or revise')
    c=db.get(ReturnCase,cid)
    if not c:raise HTTPException(404,'Case not found')
    if c.status!='WAITING_FOR_APPROVAL':raise HTTPException(409,'Case is not waiting for approval')
    c.status={'approve':'APPROVED','reject':'REJECTED','revise':'NEEDS_REVISION'}[decision];db.commit();return {'id':c.id,'status':c.status,'note':'This records the admin decision only; no payment is released.'}
@app.post('/api/agent/chat')
def chat(data:ChatIn,db:Session=Depends(get_db),u:User=Depends(current_user)):
    count=db.query(ChatMessage).filter_by(user_id=u.id,thread_id=data.thread_id).count()
    if count>=80:raise HTTPException(429,'Conversation limit reached. Start a new thread.')
    result=run_agent(db,u,data.message)
    db.add(ChatMessage(user_id=u.id,thread_id=data.thread_id,role='user',content=data.message));db.add(ChatMessage(user_id=u.id,thread_id=data.thread_id,role='assistant',content=result['answer']));db.commit()
    return result
@app.get('/api/agent/threads/{thread_id}')
def thread(thread_id:str,db:Session=Depends(get_db),u:User=Depends(current_user)):
    rows=db.query(ChatMessage).filter_by(user_id=u.id,thread_id=thread_id).order_by(ChatMessage.id).all();return [{'role':r.role,'content':r.content} for r in rows]
@app.get('/api/admin/overview')
def overview(db:Session=Depends(get_db),u:User=Depends(require_roles('admin'))):
    return {'users':db.query(User).count(),'products':db.query(Product).count(),'orders':db.query(Order).count(),'pending_approvals':db.query(ReturnCase).filter_by(status='WAITING_FOR_APPROVAL').count(),'revenue':sum(o.total for o in db.query(Order).all())}
@app.get('/api/admin/returns')
def admin_returns(db:Session=Depends(get_db),u:User=Depends(require_roles('admin'))):return returns_admin(db)
def returns_admin(db):return [{'id':c.id,'order_id':c.order_id,'buyer_id':c.buyer_id,'vendor_id':c.vendor_id,'reason':c.reason,'amount':c.amount,'status':c.status,'policy_evidence':c.policy_evidence} for c in db.query(ReturnCase).order_by(desc(ReturnCase.id)).all()]
@app.get('/api/vendor/cases')
def vendor_cases(db:Session=Depends(get_db),u:User=Depends(require_roles('vendor'))):return returns(db,u) if False else [{'id':c.id,'order_id':c.order_id,'reason':c.reason,'amount':c.amount,'status':c.status} for c in db.query(ReturnCase).filter_by(vendor_id=u.id).all()]
@app.put('/api/preferences')
def save_preferences(language:str='bn',delivery_area:str='',refund_method:str='',consent:bool=False,db:Session=Depends(get_db),u:User=Depends(require_roles('buyer'))):
    p=db.query(Preference).filter_by(user_id=u.id).first()
    if not consent:
        if p:db.delete(p);db.commit()
        return {'saved':False,'message':'Preferences deleted; consent is required to store them.'}
    if not p:p=Preference(user_id=u.id);db.add(p)
    p.language=language;p.delivery_area=delivery_area;p.refund_method=refund_method;p.consent=True;db.commit();return {'saved':True}
@app.delete('/api/preferences')
def delete_preferences(db:Session=Depends(get_db),u:User=Depends(require_roles('buyer'))):
    p=db.query(Preference).filter_by(user_id=u.id).first()
    if p:db.delete(p);db.commit()
    return {'deleted':True}
@app.get('/api/solar/estimate')
def estimate(daily_kwh:float=10,peak_kw:float=2,backup_hours:float=4,db:Session=Depends(get_db)):
    if min(daily_kwh,peak_kw,backup_hours)<=0:raise HTTPException(400,'All values must be positive')
    panel_kw=round(daily_kwh/4.2/0.78,2);battery_kwh=round(peak_kw*backup_hours/0.85,2)
    return {'recommended_panel_kw':panel_kw,'recommended_battery_kwh':battery_kwh,'estimated_panels_615w':int((panel_kw*1000+614)//615),'inverter_min_kw':round(peak_kw*1.25,2),'assumptions':'4.2 peak-sun-hours/day, 78% system derate, 85% usable battery energy. Final design requires site survey and load audit.'}
