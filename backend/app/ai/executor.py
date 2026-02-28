import httpx

from app import config

async def execute_signal(symbol: str, decision: dict):
    """
    decision = {"action": "buy", "confidence": 0.85}
    """

    action = decision["action"]

    # Ignore if confidence too low
    if decision["confidence"] < 0.7:
        return

    print(f"📤 Executing order → {symbol} → {action}")

    # You will map symbol → SecurityId for order placement
    # This is just sample structure
    payload = {
        "transactionType": "BUY" if action == "buy" else "SELL",
        "exchangeSegment": "NSE_EQ",
        "securityId": "REPLACE_THIS",
        "quantity": 1,
        "productType": "INTRADAY",
        "orderType": "MARKET"
    }

    # Send order (mock for now)
    print(f"📝 Order Payload: {payload}")

    # TODO: uncomment when ready
    # async with httpx.AsyncClient() as client:
    #     response = await client.post(
    #         f"{config.DHAN_REST_BASE}/orders",
    #         headers={"access-token": config.ACCESS_TOKEN},
    #         json=payload
    #     )
    #     print("📥 Dhan Response:", response.text)
