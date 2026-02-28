from fastapi import APIRouter
import yfinance as yf

router = APIRouter()

@router.get("/stocks")
def get_stocks():
    # Define stock symbols (Indian NSE symbols end with .NS)
    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "SBIN.NS"]

    data = []
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        current_price = info.get("currentPrice") or info.get("lastPrice") or 0
        data.append({
            "symbol": symbol.replace(".NS", ""),
            "price": round(current_price, 2)
        })

    return {"stocks": data}
