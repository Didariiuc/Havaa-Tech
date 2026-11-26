"""SolarWise proposal-aligned supervisor and specialist agents.
Uses Gemini primary -> Gemini lite -> OpenRouter fallback. Deterministic mode keeps the demo usable offline.
"""
from typing import TypedDict
import re, json
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from ..config import settings
from ..models import Order, ReturnCase, Product
from ..security import injection_detected, redact_pii
POLICIES=[
 {'vendor':'marketplace','document':'SolarWise Buyer Protection','section':'1.2','text':'Havaa Tech buyers may request assistance for damaged, incorrect or materially misdescribed solar products. Installation and electrical work must be inspected by a qualified technician. Refunds above BDT 2,000 require administrator approval.'},
 {'vendor':'marketplace','document':'SolarWise Returns and Disputes','section':'2.1','text':'A buyer should report transit damage within 48 hours of delivery with order evidence and photographs. Uninstalled standard stock products may be considered for return within 7 days, subject to vendor inspection and stated exclusions.'},
 {'vendor':'SunGrid BD','document':'SunGrid BD Solar Product Policy','section':'3.1','text':'SunGrid BD accepts requests for damaged panels and inverters reported within 48 hours of delivery. Installed, physically modified or serial-number-mismatched products are excluded unless verified as defective under warranty.'},
 {'vendor':'SunGrid BD','document':'SunGrid BD Battery Warranty','section':'4.2','text':'LiFePO4 battery warranty claims require serial number, BMS diagnostics and installer report. Battery capacity degradation is assessed under manufacturer warranty terms; consumable wear and misuse are excluded.'},
 {'vendor':'GreenVolt','document':'GreenVolt Returns','section':'2.3','text':'GreenVolt allows unopened accessories to be returned within 7 days. Solar panels and batteries are non-returnable after installation, except verified transit damage or manufacturer defect.'},
]
class State(TypedDict): message:str; user_id:int; role:str; db:Session; route:str; answer:str; citations:list; calls:int

def retrieve_policy(query,vendor=None):
    q=query.lower(); rows=[]
    for p in POLICIES:
        if vendor and vendor.lower() not in ('marketplace',p['vendor'].lower()): continue
        score=sum(w in p['text'].lower() for w in q.split() if len(w)>3)
        score+=sum(w in p['document'].lower() for w in q.split() if len(w)>3)
        if score: rows.append((score,p))
    rows.sort(key=lambda x:x[0],reverse=True)
    return [p for _,p in rows[:3]]

def make_llm():
    models=[]
    if settings.google_api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            models.append(ChatGoogleGenerativeAI(model=settings.primary_model,google_api_key=settings.google_api_key,temperature=0.2))
            models.append(ChatGoogleGenerativeAI(model=settings.gemini_fallback_model,google_api_key=settings.google_api_key,temperature=0.2))
        except Exception: pass
    if settings.openrouter_api_key:
        try:
            from langchain_openai import ChatOpenAI
            models.append(ChatOpenAI(model=settings.openrouter_model,api_key=settings.openrouter_api_key,base_url=settings.openrouter_base_url,temperature=0.2))
        except Exception: pass
    return models

def answer_with_model(prompt):
    for llm in make_llm():
        try: return llm.invoke(prompt).content
        except Exception: continue
    return None
# For Solar Load
def estimate_solar_load(message: str):
    """Transparent illustrative sizing; ask for actual wattage/runtime before final design."""
    q=message.lower()
    # Conservative illustrative appliance assumptions, explicitly disclosed.
    appliances=[
        ('fan', r'(\d+)\s*(?:fans?|টি\s*ফ্যান|ফ্যান)', 60, 8),
        ('light', r'(\d+)\s*(?:lights?|টি\s*লাইট|লাইট)', 10, 6),
        ('refrigerator', r'(?:one|1|একটি|এক)\s*(?:refrigerator|fridge|ফ্রিজ)', 150, 10),
        ('TV', r'(?:one|1|একটি|এক)\s*(?:tv|টিভি)', 100, 5),
    ]
    rows=[]
    for name,pat,watt,hours in appliances:
        m=re.search(pat,q)
        if m:
            qty=int(m.group(1)) if m.lastindex else 1
            rows.append((name,qty,watt,hours,qty*watt,qty*watt*hours/1000))
    if not rows: return None
    daily=sum(r[5] for r in rows)
    peak=sum(r[4] for r in rows)
    pv_kw=daily/(4.2*0.78)
    panel_count=max(1,int(__import__('math').ceil(pv_kw*1000/615)))
    battery_kwh=daily*0.5/0.85
    inverter_kw=max(1.0, peak*1.25/1000)
    detail='\n'.join(f'- {n}: {qty} × {w}W × {h}h = {e:.2f} kWh/day' for n,qty,w,h,_,e in rows)
    return (f"Illustrative solar sizing (not a final engineering design):\n{detail}\n"
            f"Estimated daily energy: {daily:.2f} kWh/day; estimated simultaneous load: {peak} W.\n"
            f"PV array estimate: {pv_kw:.2f} kW; approximately {panel_count} × 615W panels ({panel_count*615/1000:.2f} kW).\n"
            f"Illustrative inverter starting point: at least {inverter_kw:.2f} kW before surge/starting-current checks.\n"
            f"For about 50% daily-energy backup: roughly {battery_kwh:.2f} kWh nominal battery capacity at 85% usable energy.\n"
            "Assumptions: fans 60W for 8h, lights 10W for 6h, refrigerator 150W average for 10h, TV 100W for 5h; Bangladesh peak-sun-hours 4.2, system derate 78%. Actual appliance labels, duty cycles, backup hours, roof shading, phase and surge current must be confirmed by a site survey.")

def battery_comparison():
    return ("LiFePO4 vs Lead-Acid (general technical comparison; verify exact model datasheets):\n"
            "- Usable capacity: LiFePO4 commonly supports a deeper usable discharge; lead-acid usually needs a shallower discharge to preserve life.\n"
            "- Cycle life: LiFePO4 generally offers substantially more charge/discharge cycles when operated within its BMS limits.\n"
            "- Efficiency: LiFePO4 generally has higher round-trip efficiency.\n"
            "- Weight/space: LiFePO4 is usually lighter and more compact for the same usable energy.\n"
            "- Upfront cost: lead-acid is usually cheaper initially; LiFePO4 often has a higher initial price but may offer lower lifetime cost.\n"
            "- Maintenance: sealed LiFePO4 packs with a suitable BMS are typically lower-maintenance; flooded tubular lead-acid may require ventilation and maintenance.\n"
            "Choose LiFePO4 for frequent cycling and longer-term performance if budget and compatible BMS/inverter allow. Choose lead-acid when upfront cost dominates and cycling is occasional. This is general product knowledge, not a warranty or vendor-policy statement.")

def build_graph():
    def safety(s):
        s['message']=redact_pii(s['message'])
        if injection_detected(s['message']): s['answer']='I can help with Havaa Tech orders and policies, but I cannot ignore platform safeguards or bypass approval.'; s['route']='blocked'
        return s
    def supervisor(s):
        if s.get('route')=='blocked': return s
        m=s['message'].lower().strip()
        greetings={'hi','hello','hey','হাই','হ্যালো','আসসালামু আলাইকুম','সালাম'}
        if m in greetings:
            s['route']='greeting'
        elif s['role']=='vendor' and any(x in m for x in ['vendor case','my cases','seller dashboard','pending return','আমার কেস']):
            s['route']='vendor'
        # Specific solar intents must be classified before generic policy fallback.
        elif any(x in m for x in ['difference between','compare','comparison','vs ','versus','পার্থক্য','তুলনা']) and any(x in m for x in ['battery','lifepo4','lead-acid','lead acid','ব্যাটারি','লিথিয়াম']):
            s['route']='comparison'
        elif any(x in m for x in ['fans','fan','lights','light','refrigerator','fridge','tv','load','backup','hours of backup','চালাতে','ফ্যান','লাইট','ফ্রিজ','টিভি','লোড','ব্যাকআপ']):
            s['route']='sizing'
        elif any(x in m for x in ['order','return','refund','delivery','deliver','track','shipping','ship','sent','send','dispatch','courier','অর্ডার','রিটার্ন','রিফান্ড','ডেলিভারি','পাঠাবে','পাঠানো','কবে যাবে','কবে আসবে']):
            s['route']='order'
        elif any(x in m for x in ['panel','solar panel','inverter','battery','package','price','watt','কত টাকা','দাম','প্যানেল','ইনভার্টার','ব্যাটারি','প্যাকেজ','সোলার সিস্টেম','recommend','best for','কোনটা','কোন প্যানেল']):
            s['route']='product'
        elif any(x in m for x in ['policy','warranty','return window','refund rule','নীতিমালা','ওয়ারেন্টি','ওয়ারেন্টি','রিটার্ন পলিসি']):
            s['route']='policy'
        else:
            s['route']='general'
        return s
    def greeting(s):
        s['answer']='Hello! Welcome to Havaa Tech. You can ask me about solar panels, inverters, batteries, packages, product prices, system sizing, orders, returns or vendor policies.'
        return s
    def product(s):
        from .tools import search_products
        rows=search_products(s['db'], s['message'])
        if not rows:
            s['answer']='I could not find a matching product in the current Havaa Tech catalog. Please try a product type such as solar panel, inverter, battery or package.'
        else:
            s['answer']=f"I searched the live Havaa Tech product database. Found {len(rows)} matching in-stock catalog item(s). Prices are stored catalog prices; confirm final availability with the seller:\n"+'\n'.join(f"• {r['name']} — {r['brand']} / {r['model']}; BDT {r['price_min']:,.0f}–{r['price_max']:,.0f}; Specs: {r['specs']}" for r in rows)+"\n\n[Tool executed: search_products | Source: SQL database | Results: "+str(len(rows))+"]"
        return s
    def policy(s):
        from .tools import search_policies, SearchPoliciesInput
        docs=search_policies(s['db'], SearchPoliciesInput(question=s['message']))
        s['citations']=[{'document':p['document'],'section':p['section'],'vendor':p['vendor']} for p in docs]
        if not docs: s['answer']='I could not find sufficient approved policy evidence to confirm this. Please contact Havaa Tech support or an administrator.'; return s
        context='\n'.join(f"[{p['document']}, §{p['section']}] {p['text']}" for p in docs)
        prompt=f"You are Havaa Tech Policy Specialist. Answer only from evidence. Mention source document and section. If evidence is insufficient say so.\nQuestion: {s['message']}\nEvidence:\n{context}"
        s['answer']=answer_with_model(prompt) or ('Based on the retrieved policy: '+ ' '.join(p['text'] for p in docs)+' Sources: '+', '.join(f"{p['document']} §{p['section']}" for p in docs))
        return s
    def order(s):
        # Order access is always scoped to the authenticated buyer. A typed order ID
        # is only a selector; it never grants access to another buyer's order.
        from .tools import list_my_orders, ListMyOrdersInput
        buyer_orders=s['db'].query(Order).filter_by(buyer_id=s['user_id']).order_by(Order.id.desc()).limit(20).all()
        if not buyer_orders:
            s['answer']='There are no orders on your account yet. Place an order first, or sign in with the account used to place it.'
            return s
        match=re.search(r'(?:order\s*#?\s*|#)(\d+)', s['message'], re.I)
        order_id=int(match.group(1)) if match else None
        selected=next((o for o in buyer_orders if o.id==order_id), None) if order_id else buyer_orders[0]
        if order_id and not selected:
            s['answer']=f'I could not find order #{order_id} in your account. I can only access orders placed by your signed-in account.'
            return s
        # If the user is simply asking when it will be sent, use their latest order
        # as context; explicitly state which order is being discussed.
        status=(selected.status or 'processing').lower()
        if status in ('processing','pending','confirmed'):
            s['answer']=(f'Order #{selected.id} is currently {status}. It has not been marked as dispatched yet. '
                         'There is no estimated dispatch date recorded in the order system at the moment, so I cannot confirm when it will be sent. '
                         'Please check again later or contact the seller/support for an updated dispatch estimate.')
        elif status in ('shipped','dispatched','in_transit','in transit'):
            details=[]
            if selected.dispatched_at: details.append('Dispatch date: '+selected.dispatched_at.strftime('%d %b %Y'))
            if selected.courier_name: details.append('Courier: '+selected.courier_name)
            if selected.tracking_number: details.append('Tracking number: '+selected.tracking_number)
            if selected.estimated_delivery_at: details.append('Estimated delivery: '+selected.estimated_delivery_at.strftime('%d %b %Y'))
            s['answer']=f'Order #{selected.id} has been marked as {status.replace("_"," ")}. '+(' | '.join(details) if details else 'Courier and tracking details have not been added yet.')
        elif status in ('delivered','completed'):
            when=selected.delivered_at.strftime('%d %b %Y') if selected.delivered_at else 'not recorded'
            s['answer']=f'Order #{selected.id} is marked {status}. Delivery date: {when}.'
        else:
            s['answer']=f'Order #{selected.id} status is {status}. No further shipping update is recorded yet.'
        s['answer']+='\n\n[Route: Order & Shipping Specialist | Source: authenticated order database]'
        return s
    def vendor(s):
        from .tools import get_vendor_cases, VendorCasesInput
        rows=get_vendor_cases(s['db'], s['user_id'], VendorCasesInput())
        cases=[s['db'].get(ReturnCase, row['id']) for row in rows]
        s['answer']='Your return cases: '+('; '.join(f'Case #{c.id}, order #{c.order_id}: {c.status}, BDT {c.amount:,.0f}' for c in cases) if cases else 'No open cases found.')
        return s
    def comparison(s):
        s['answer']=battery_comparison()+"\n\n[Route: Battery Comparison Specialist]"
        return s
    def sizing(s):
        result=estimate_solar_load(s['message'])
        if result:
            s['answer']=result+"\n\n[Route: Solar Sizing Specialist | Calculation: deterministic estimate]"
        else:
            s['answer']='I can estimate your system. Please provide appliance quantity, wattage (or model), daily usage hours and required backup hours.'
        return s
    def general(s):
        s['answer']='I am Havaa Tech AI. Ask me about solar products, battery comparisons, system sizing, packages, orders, returns or vendor policies.'
        return s
    def approval(s):
        # Approval is deliberately not exposed as an agent tool.
        return s
    g=StateGraph(State); g.add_node('safety',safety); g.add_node('supervisor',supervisor); g.add_node('greeting',greeting); g.add_node('product',product); g.add_node('policy',policy); g.add_node('order',order); g.add_node('vendor',vendor); g.add_node('comparison',comparison); g.add_node('sizing',sizing); g.add_node('general',general); g.add_node('approval',approval)
    g.set_entry_point('safety'); g.add_edge('safety','supervisor')
    g.add_conditional_edges('supervisor',lambda s: 'blocked' if s.get('route')=='blocked' else s['route'],{'blocked':'approval','greeting':'greeting','product':'product','policy':'policy','order':'order','vendor':'vendor','comparison':'comparison','sizing':'sizing','general':'general'})
    for n in ['greeting','product','policy','order','vendor','comparison','sizing','general','approval']: g.add_edge(n,END)
    return g.compile()
GRAPH=build_graph()
def run_agent(db,user,message):
    result=GRAPH.invoke({'message':message,'user_id':user.id,'role':user.role,'db':db,'route':'','answer':'','citations':[],'calls':0})
    return {'answer':result['answer'],'citations':result.get('citations',[]),'route':result.get('route','unknown')}
