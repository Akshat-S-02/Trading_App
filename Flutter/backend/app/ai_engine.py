import asyncio
import yfinance as yf
from .db import SessionLocal
from . import crud, models
import random
import datetime
import uuid
import time
from .logger import trade_logger, execution_logger, error_logger, system_logger
from .risk_engine import RiskManager
from .order_manager import OrderManager

# NSE Holidays 2026 (YYYY-MM-DD)
NSE_HOLIDAYS_2026 = [
    datetime.date(2026, 1, 26),  # Republic Day
    datetime.date(2026, 3, 3),   # Holi
    datetime.date(2026, 3, 26),  # Ram Navami
    datetime.date(2026, 3, 31),  # Mahavir Jayanti
    datetime.date(2026, 4, 3),   # Good Friday
    datetime.date(2026, 4, 14),  # Ambedkar Jayanti
    datetime.date(2026, 5, 1),   # Maharashtra Day
    datetime.date(2026, 6, 26),  # Muharram (Tentative)
    datetime.date(2026, 8, 15),  # Independence Day (Saturday)
    datetime.date(2026, 10, 2),  # Gandhi Jayanti
    datetime.date(2026, 11, 1),  # Diwali (Sunday)
    datetime.date(2026, 12, 25)  # Christmas
]

async def check_stop_losses(db):
    try:
        active_trades = db.query(models.Trade).filter(models.Trade.side == 'BUY', models.Trade.is_active == 1).all()
        risk_manager = RiskManager(db)
        order_manager = OrderManager(db)
        
        for trade in active_trades:
            if not trade.stop_loss: continue
            
            try:
                t = yf.Ticker(trade.symbol)
                # Feed Integrity Check
                tick_start = time.time()
                history = await asyncio.to_thread(t.history, period='1d', interval='1m')
                tick_end = time.time()
                
                if history.empty: continue
                
                # Check Feed Integrity
                if not risk_manager.check_feed_integrity(tick_start, tick_end): # Simplified: verifying fetch time
                    continue

                current_price = float(history['Close'].iloc[-1])
                
                if current_price <= trade.stop_loss:
                    system_logger.info(f"🛑 STOP LOSS TRIGGERED for {trade.symbol} @ {current_price} (SL: {trade.stop_loss})")
                    
                    # Generate Idempotency Key
                    order_id = order_manager.generate_order_id()
                    if order_manager.is_order_processed(order_id):
                        system_logger.warning(f"Order {order_id} already processed. Skipping.")
                        continue

                    # Update Holdings
                    holding = db.query(models.Holding).filter(models.Holding.user_id == trade.user_id, models.Holding.symbol == trade.symbol).first()
                    if holding:
                        if holding.qty >= trade.qty:
                            holding.qty -= trade.qty
                            if holding.qty == 0:
                                db.delete(holding)
                            else:
                                db.add(holding)
                                
                            # Credit tokens
                            user = db.query(models.User).filter(models.User.id == trade.user_id).first()
                            value = trade.qty * current_price
                            user.tokens += value
                            db.add(user)
                            
                            # Create Sell Trade with Order ID
                            sell_trade = models.Trade(
                                user_id=trade.user_id,
                                symbol=trade.symbol,
                                qty=trade.qty,
                                price=current_price,
                                side='SELL',
                                is_active=0,
                                pnl = value - (trade.qty * trade.price),
                                order_id=order_id
                            )
                            db.add(sell_trade)
                            
                            # Mark original trade as closed
                            trade.is_active = 0
                            db.add(trade)
                            db.commit()
                            
                            execution_logger.info(f"SL Executed: SOLD {trade.symbol} Qty {trade.qty} @ {current_price} | PnL: {sell_trade.pnl} | OrderID: {order_id}")
            except Exception as e:
                error_logger.error(f"Error checking SL for {trade.symbol}: {e}")
    except Exception as e:
        error_logger.error(f"Error in check_stop_losses: {e}")

async def get_market_trend():
    """
    Returns 'BULL', 'BEAR', or 'NEUTRAL' based on Nifty 50 performance.
    """
    try:
        nifty = yf.Ticker("^NSEI")
        hist = await asyncio.to_thread(nifty.history, period="1mo", interval="1d")
        if hist.empty: return 'NEUTRAL'
        
        sma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        current = hist['Close'].iloc[-1]
        
        if current > sma20 * 1.01: return 'BULL'
        if current < sma20 * 0.99: return 'BEAR'
        return 'NEUTRAL'
    except Exception as e:
        error_logger.error(f"Error fetching market trend: {e}")
        return 'NEUTRAL'

async def analyze_news(symbol):
    try:
        t = yf.Ticker(symbol)
        news = await asyncio.to_thread(lambda: t.news)
        if not news: return 0.0
        
        score = 0
        count = 0
        positive_words = ['growth', 'profit', 'rise', 'up', 'bull', 'gain', 'high', 'win', 'deal', 'strong']
        negative_words = ['loss', 'fall', 'down', 'bear', 'drop', 'low', 'weak', 'risk', 'fail', 'crash']
        
        for item in news[:5]: 
            title = item.get('title', '').lower()
            if not title: continue
            
            for word in positive_words:
                if word in title: score += 1
            for word in negative_words:
                if word in title: score -= 1
            count += 1
            
        if count == 0: return 0.0
        return max(min(score / count, 1.0), -1.0)
        
    except Exception as e:
        error_logger.error(f"Error analyzing news for {symbol}: {e}")
        return 0.0

def check_diversification(db, user_id, symbol, potential_investment):
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user: return False
        
        holdings = db.query(models.Holding).filter(models.Holding.user_id == user_id).all()
        
        equity_value = 0.0
        stock_value = 0.0
        
        for h in holdings:
            val = h.qty * h.avg_price
            equity_value += val
            if h.symbol == symbol:
                stock_value += val
                
        total_value = user.tokens + equity_value
        new_stock_value = stock_value + potential_investment
        new_total_value = total_value 
        
        if new_total_value == 0: return True # Edge case

        exposure_pct = new_stock_value / new_total_value
        
        if exposure_pct > 0.20:
            system_logger.warning(f"Diversification Check Failed for {symbol}: Exposure {exposure_pct:.2%} > 20%")
            return False
            
        return True
    except Exception as e:
        error_logger.error(f"Error in diversification check: {e}")
        return False

def is_market_open():
    try:
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        ist_now = utc_now + datetime.timedelta(minutes=330)
        today_date = ist_now.date()
        
        if today_date in NSE_HOLIDAYS_2026:
            return False

        if ist_now.weekday() >= 5: 
            return False
            
        current_time = ist_now.time()
        start_time = datetime.time(8, 55)
        end_time = datetime.time(15, 30) 
        
        if start_time <= current_time <= end_time:
            return True
            
        return False
    except Exception as e:
        error_logger.error(f"Error checking market hours: {e}")
        return True 

async def reconcile_state(db):
    """
    Simulates Broker Reconciliation.
    In a real system, this would fetch positions from the broker and compare with local DB.
    """
    system_logger.info("⚔️ Broker Reconciliation: Sandbox Mode (Internal DB is source of truth)")
    return True

async def simple_momentum_loop(interval_seconds: int = 60):
    system_logger.info("🚀 AI Agent Started (Safe Mode)")
    
    # Initial Reconciliation
    db = SessionLocal()
    await reconcile_state(db)
    db.close()

    while True:
        if not is_market_open():
            system_logger.info("zzz Market Closed. AI sleeping...")
            await asyncio.sleep(300) 
            continue

        db = SessionLocal()
        try:
            risk_manager = RiskManager(db)
            order_manager = OrderManager(db)

            # 1. Check Stop Losses
            await check_stop_losses(db)
            
            # 2. Market Trend
            market_trend = await get_market_trend()
            
            symbols = ['RELIANCE.NS','TCS.NS','INFY.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'SBIN.NS', 'BHARTIARTL.NS', 'ITC.NS', 'KOTAKBANK.NS', 'LICI.NS']
            
            user = crud.get_user(db, 'admin')
            if not user: 
                system_logger.critical("No admin user for AI")
                continue

            for s in symbols:
                try:
                    t = yf.Ticker(s)
                    tick_start = time.time()
                    hist = await asyncio.to_thread(t.history, period='60d', interval='1d')
                    tick_end = time.time()
                    
                    if hist.empty or hist.shape[0] < 50: continue
                    
                    if not risk_manager.check_feed_integrity(tick_start, tick_end):
                        continue

                    # Technical Indicators
                    sma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                    sma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
                    latest = float(hist['Close'].iloc[-1])
                    rsi = 50 
                    
                    delta = hist['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    if not loss.iloc[-1] == 0:
                        rs = gain.iloc[-1] / loss.iloc[-1]
                        rsi = 100 - (100 / (1 + rs))
                    
                    sentiment_score = await analyze_news(s)
                    
                    decision = 'HOLD'
                    confidence = 0.0
                    
                   # --- BUY LOGIC ---
                    if latest > sma20 and market_trend != 'BEAR' and rsi < 70 and sentiment_score >= 0:
                        decision = 'BUY'
                        confidence = 0.6 + (0.1 if latest > sma50 else 0) + (0.1 if sentiment_score > 0 else 0) + (0.1 if rsi < 60 else 0)
                        
                    # --- SELL LOGIC ---
                    elif latest < sma20 or rsi > 80 or sentiment_score < -0.3:
                        decision = 'SELL'
                        confidence = 0.7
                    
                    # Store AI Action & Log
                    order_id = order_manager.generate_order_id()
                    ai = models.AIAction(
                        symbol=s, 
                        decision=decision, 
                        confidence=confidence, 
                        meta={
                            'market': market_trend,
                            'sentiment': sentiment_score, 
                            'rsi': rsi,
                            'sma20': sma20,
                            'price': latest
                        },
                        order_id=order_id,
                        latency_ms=(time.time() - tick_start)*1000
                    )
                    db.add(ai)
                    db.commit()
                    trade_logger.info(f"AI Signal: {decision} {s} | Conf: {confidence:.2f} | ID: {order_id}")
                    
                    # Execute Trade
                    if decision == 'BUY' and confidence >= 0.75:
                        # 4. Position Sizing (Risk Based)
                        stop_loss_price = latest * 0.95 # 5% Stop Loss
                        risk_per_trade_pct = 1.0 # 1% Risk
                        
                        qty = risk_manager.calculate_position_size(user.tokens, risk_per_trade_pct, latest, stop_loss_price)
                        value = latest * qty
                        
                        if qty > 0:
                            # 5. Portfolio Versatility Check
                            if check_diversification(db, user.id, s, value):
                                # 6. Capital Limits Check
                                if risk_manager.check_capital_limits(user, value): # Using value as proxy for loss metric if needed, or simple limit checks
                                    
                                    # 7. Check Balance
                                    if user.tokens >= value:
                                        
                                        # 8. Idempotency Check
                                        if order_manager.is_order_processed(order_id):
                                             system_logger.warning(f"Order {order_id} skipped (Duplicate)")
                                             continue

                                        user.tokens -= value
                                        user.daily_spent += value
                                        user.monthly_spent += value
                                        db.add(user)
                                        
                                        # Create Holding
                                        holding = db.query(models.Holding).filter(models.Holding.user_id == user.id, models.Holding.symbol == s).first()
                                        if holding:
                                            total_qty = holding.qty + qty
                                            new_avg = ((holding.qty * holding.avg_price) + (qty * latest)) / total_qty
                                            holding.qty = total_qty
                                            holding.avg_price = new_avg
                                        else:
                                            holding = models.Holding(user_id=user.id, symbol=s, qty=qty, avg_price=latest)
                                        db.add(holding)
                                        
                                        # Create Trade
                                        new_trade = models.Trade(
                                            user_id=user.id,
                                            symbol=s,
                                            qty=qty,
                                            price=latest,
                                            side='BUY',
                                            stop_loss=stop_loss_price,
                                            is_active=1,
                                            order_id=order_id 
                                        )
                                        db.add(new_trade)
                                        db.commit()
                                        execution_logger.info(f"BUY Executed: {s} Qty {qty} @ {latest} | RiskAlloc: {risk_per_trade_pct}% | OrderID: {order_id}")
                                    else:
                                        system_logger.warning(f"Insufficient funds for {s}: Needed {value}, Have {user.tokens}")
                                else:
                                    system_logger.warning(f"Capital Limit Hit for {s}")
                            else:
                                system_logger.warning(f"Diversification Fail for {s}")
                        else:
                            system_logger.warning(f"Position Size 0 for {s} (Risk too high?)")

                except Exception as inner_e:
                    error_logger.error(f"AI error processing {s}: {inner_e}")
                    
        except Exception as e:
            error_logger.error(f"AI loop global error: {e}")
        finally:
            db.close()
        await asyncio.sleep(interval_seconds)
