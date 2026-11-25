from datetime import datetime, timedelta, timezone
import json
from .db import Base,engine,SessionLocal
from .models import User,Product,Order
from .security import hash_password
from .data.catalog import PRODUCTS
Base.metadata.create_all(engine)
db=SessionLocal()
accounts=[('admin@solarwise.local','Havaa Tech Admin','admin','Admin123!',None),('vendor@solarwise.local','Havaa Tech Demo Vendor','vendor','Vendor123!','SunGrid BD'),('buyer@solarwise.local','Havaa Tech Demo Buyer','buyer','Buyer123!',None)]
for email,name,role,pw,vname in accounts:
    if not db.query(User).filter_by(email=email).first():db.add(User(name=name,email=email,role=role,password_hash=hash_password(pw),vendor_name=vname))
for i in range(1,9):
    email=f'vendor{i}@solarwise.local';name=f'Solar Vendor {i}';vname=['SunGrid BD','GreenVolt','BrightRoof Energy','EcoSpark Solar','SunPeak Technologies','Dhaka Solar Mart','RenewGen BD','Helio Power'][i-1]
    if not db.query(User).filter_by(email=email).first():db.add(User(name=name,email=email,role='vendor',vendor_name=vname,password_hash=hash_password('Vendor123!')))
for i in range(1,21):
    email=f'buyer{i}@solarwise.local'
    if not db.query(User).filter_by(email=email).first():db.add(User(name=f'Demo Buyer {i}',email=email,role='buyer',password_hash=hash_password('Buyer123!')))
db.commit()
vendors=db.query(User).filter_by(role='vendor').order_by(User.id).all();buyers=db.query(User).filter_by(role='buyer').order_by(User.id).all()
# Idempotent catalog seeding: fill missing products even when the database
# already contains user-created or previously seeded products. Never delete or
# overwrite existing products, stock, prices, or vendor assignments.
n_added=0
for idx,(n,b,m,c,s,p1,p2) in enumerate(PRODUCTS):
    existing=db.query(Product).filter(Product.name==n).first()
    if existing:
        continue
    v=vendors[idx%len(vendors)]
    db.add(Product(name=n,brand=b,model=m,category=c,specs=json.dumps(s),price_min=p1,price_max=p2,stock=15+(idx%12),vendor_id=v.id,description=f'{b} {m}. Indicative Bangladesh market price; verify warranty and availability.'))
    n_added+=1
    if n_added % 10 == 0:
        db.flush()
db.commit()
if db.query(Order).count()==0:
    catalog=db.query(Product).all()
    for i in range(200):
        buyer=buyers[i%len(buyers)];product=catalog[i%len(catalog)];qty=1+(i%2);price=(product.price_min+product.price_max)/2
        status=['delivered','processing','shipped','completed'][i%4]
        created=datetime.now(timezone.utc)-timedelta(days=(i%50)+1)
        delivered=created+timedelta(days=3) if status in ('delivered','completed') else None
        db.add(Order(buyer_id=buyer.id,vendor_id=product.vendor_id,total=price*qty,status=status,items_json=json.dumps([{'product_id':product.id,'name':product.name,'quantity':qty,'unit_price':price}]),created_at=created,delivered_at=delivered))
    db.commit()
print(f'Seed complete: {len(vendors)} vendors, {len(buyers)} buyers, {db.query(Product).count()} products ({n_added} catalog products added), {db.query(Order).count()} orders.')
print('Demo accounts: admin@solarwise.local / Admin123!; vendor@solarwise.local / Vendor123!; buyer@solarwise.local / Buyer123!')
db.close()
