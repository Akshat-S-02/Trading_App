# AI Stock Trader (Sandbox)

A comprehensive paper trading and market data application built with a separate Flutter frontend and a scalable FastAPI backend. The app integrates with the **Dhan API** for live market streams and provides a full JWT-secured sandbox trading environment.

## 🚀 Capabilities & Functionality

### 1. Security & Authentication
- **JWT-Based Auth:** The entire system is secured with access tokens. The application forces the user to log in on every cold start.
- **Dhan Token Rotation:** The backend includes a background chron-job to automatically refresh Dhan API access tokens every morning before the market opens, avoiding manual token regeneration.

### 2. Live Market Data (Tick Stream)
- **Live Websocket Integration:** Connects to Dhan's live binary WebSocket to stream top 5,000 NSE_EQ instruments in real-time.
- **Smart Reconnecting:** Reconnects with exponential backoff if the socket drops. Dynamically resubscribes to runtime-added symbols so user lists never "go dark".
- **Batch Data Loading:** App startup time is under `1s`. The backend utilizes Dhan's batch Quote REST API to seed the entire user watchlist in a single parallel call if WebSocket ticks aren't in the cache yet.

### 3. Risk Management
- **Spend Limits:** Users can set and save Daily and Monthly maximum spend limits.
- **Persistent Rules:** These limits are stored in the backend (PostgreSQL) and seamlessly loaded into the Flutter State (via `TradingProvider`) on app boot.

### 4. Sandbox Trading & Portfolio
- **Virtual Funds:** Users start with a virtual sandbox balance (e.g., ₹50,000).
- **Watchlist Persistence:** Users can search and add stocks to their personal watchlist, saved on the device.
- **State Management:** Fully separated frontend architecture using Flutter's `Provider`:
  - `AuthProvider`: Auth state / Login.
  - `MarketDataProvider`: Websocket ticks, Watchlist, Search.
  - `TradingProvider`: Orders, Portfolio, Wallet Balance, Risk Management.

## 🛠️ Technology Stack

- **Frontend:** Flutter (Dart) using `provider` for state management, `http` for REST, and `web_socket_channel` for streaming.
- **Backend:** Python 3, FastAPI, Uvicorn, SQLAlchemy ORM, Pydantic, httpx.
- **Database:** PostgreSQL (replacing SQLite for concurrency safety).
- **Data Provider:** Dhan APIHQ (REST and Websocket).

## ⚠️ Limitations & Future Work

While fully functional as a simulated sandbox, the project has the following limitations:

1. **Simulated Execution Tracking:** The order endpoints currently return stubs. Deep integrations with actual backend P&L ledgers matching Live Dhan order executions need to be completed before switching off "Sandbox" mode.
2. **Missing Real-Time Portfolio Sync:** Portfolio metrics update manually rather than passively listening to an active WebSocket ticker for *owned* shares.
3. **Hardware Constraints:** Pushing thousands of ticks a second to a Flutter frontend can get heavy. The Python backend currently buffers and broadcasts updates on a `500ms` loop to prevent overwhelming the device CPU.
4. **Single-User Focus:** Although Authentication is implemented and the DB supports multiple users, the frontend assumes a single sandbox account (`admin`) on boot. User registration flows would be needed for a SaaS product.

---

### Setup Instructions

1. Configure `.env` inside `backend/`:
   ```env
   DHAN_CLIENT_ID="..."
   DHAN_API_KEY="..."
   DHAN_API_SECRET="..."
   JWT_SECRET="..."
   APP_PASSWORD="..."
   DATABASE_URL="postgresql://postgres:password@localhost:5432/trading_sandbox"
   ```
2. Run Backend: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
3. Run App: `cd flutter_application_1 && flutter run`