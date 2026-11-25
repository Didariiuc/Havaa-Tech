# SolarWise AI — Solar multi-vendor commerce + agent platform

A runnable MVP scaffold based on the uploaded MarketWise proposal, adapted to solar commerce. Frontend: React + Vite + Tailwind. Backend: FastAPI + SQLAlchemy/SQLite + JWT. Agent layer: LangGraph/LangChain with Gemini 3.8 Flash primary and provider/model fallbacks. Qdrant is optional; local keyword retrieval works without it.

## Features included
- Buyer / Vendor / Admin role-aware experiences and protected API routes
- Signup/login, hashed passwords, JWT sessions
- Solar catalog seeded with 22 supplied panels, inverters, batteries and packages (idempotent seed)
- Vendor product CRUD, buyer cart/order flow, order history
- Solar sizing estimator (load kWh, peak watts, backup hours)
- Six proposal-aligned tools: `search_policies`, `get_order`, `list_my_orders`, `check_return_eligibility`, `create_return_request`, `get_vendor_cases`
- Three specialist agents (Policy, Order, Vendor Desk) under a LangGraph supervisor
- Policy citations, vendor-scoped retrieval, safety checks, tool limits, duplicate request protection
- Admin refund review gate at BDT 2,000; agent cannot approve/release refunds
- SQLite conversation persistence starter; Qdrant integration switch; LangSmith tracing switch
- Seed demo accounts and solar products

## Quick start
### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.seed
python -m uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

### Frontend
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```
Open http://localhost:5173

## Demo accounts
- Admin: `admin@solarwise.local` / `Admin123!`
- Vendor: `vendor@solarwise.local` / `Vendor123!`
- Buyer: `buyer@solarwise.local` / `Buyer123!`

Change all demo credentials and JWT secret before deployment. Demo users and prices are synthetic / indicative. Confirm live supplier pricing, stock, warranties and certifications before taking real orders.

## AI configuration
Set `GOOGLE_API_KEY` for Gemini. Primary model defaults to `gemini-3.8-flash`; fallback order is Gemini 3.5 Flash Lite, OpenRouter `openai/gpt-oss-20b`, then deterministic local response. Configure model IDs in `.env`. A provider fallback is only available when its corresponding API key is configured.

## Proposal mapping
- C1: Pydantic schemas for chat, policy, order and return requests
- C2: model factory + fallback chain + optional LangSmith tracing
- C3: six named backend tools
- C4: SQLite chat thread storage (MVP persistence; summaries can be enabled/extended)
- C5: PII redaction, injection filtering, session-derived identity, tool-call limits, role checks
- C6: Qdrant-ready policy chunks with vendor/document/section metadata and citations; local fallback
- C7: LangGraph supervisor → specialist routing → approval gate → response
- Elective 1: supervisor multi-specialist routing
- Elective 2: consent-based buyer preference storage/deletion endpoints

## Important production work still required
Payment gateway integration, email/SMS OTP, image upload/object storage, production-grade migrations, rate limiting, audit-log retention, automated tests, deployment secrets, supplier verification, DPDP/privacy review and real shipping integration are not enabled in this MVP. No real refund is issued by this scaffold; admin review only changes case state.


## Routing fix (ROUTING-FIX build)
Battery comparisons now route to a dedicated comparison response; appliance-load questions route to a deterministic sizing estimator; policy retrieval is reserved for explicit policy/warranty/return-rule questions. Sizing assumptions are displayed and estimates are not final engineering designs.


## Order shipping assistant update
The Order & Shipping Specialist now answers dispatch/delivery questions from the signed-in buyer's own order record. If an order ID is supplied, it is checked against that buyer's orders; if the buyer asks a follow-up without an ID, the latest order is used and named in the response. Processing orders without a dispatch estimate are reported honestly rather than routed to policy retrieval. Optional order fields: `dispatched_at`, `estimated_delivery_at`, `courier_name`, `tracking_number`. Existing SQLite databases receive additive columns automatically at startup; no reset is required. Payment gateway integration is not included or required for this feature.


## Havaa Tech branding
The frontend now uses the supplied Havaa Tech logo and a charcoal/orange visual theme. Existing marketplace features, backend routes, and database are retained.


## Havaa Tech catalog setup (important)
Run `python -m app.seed` once from the `backend` directory before starting the API. The seed now adds any missing catalog entries even if the SQLite database already contains products; it does not delete or overwrite existing products, stock, prices, users or orders. The supplied catalog contains 22 solar items across panels, inverters, batteries and complete packages. After starting the API, verify at `http://127.0.0.1:8000/api/products` or `http://127.0.0.1:8000/docs`.

Demo buyer for agent testing: `buyer@solarwise.local` / `Buyer123!`. Demo admin: `admin@solarwise.local` / `Admin123!`. Demo vendor: `vendor@solarwise.local` / `Vendor123!`. These are demo credentials; change them before any public deployment.
