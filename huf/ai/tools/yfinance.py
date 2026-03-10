import json
import frappe


def _get_ticker(symbol):
	try:
		import yfinance as yf
	except ImportError:
		raise ImportError("yfinance is required. Install with: pip install yfinance")
	return yf.Ticker(symbol)


def handle_get_stock_price(**kwargs):
	"""Get the current stock price for a symbol."""
	try:
		symbol = kwargs.get("symbol")
		if not symbol:
			return json.dumps({"success": False, "error": "Symbol is required"})
			
		ticker = _get_ticker(symbol)
		info = ticker.info
		return json.dumps({
			"success": True,
			"results": {
				"symbol": symbol,
				"price": info.get("currentPrice") or info.get("regularMarketPrice"),
				"currency": info.get("currency", "USD"),
				"market_cap": info.get("marketCap"),
				"volume": info.get("volume"),
			}
		})
	except Exception as e:
		frappe.log_error(f"YFinance Error (Stock Price): {str(e)}", "YFinance Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_get_company_info(**kwargs):
	"""Get company information for a stock symbol."""
	try:
		symbol = kwargs.get("symbol")
		if not symbol:
			return json.dumps({"success": False, "error": "Symbol is required"})
			
		info = _get_ticker(symbol).info
		return json.dumps({
			"success": True,
			"results": {
				"symbol": symbol,
				"name": info.get("longName", ""),
				"sector": info.get("sector", ""),
				"industry": info.get("industry", ""),
				"market_cap": info.get("marketCap"),
				"employees": info.get("fullTimeEmployees"),
				"website": info.get("website", ""),
				"summary": (info.get("longBusinessSummary") or "")[:1000],
			}
		})
	except Exception as e:
		frappe.log_error(f"YFinance Error (Company Info): {str(e)}", "YFinance Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_get_historical_prices(**kwargs):
	"""Get historical stock prices."""
	try:
		symbol = kwargs.get("symbol")
		if not symbol:
			return json.dumps({"success": False, "error": "Symbol is required"})
			
		ticker = _get_ticker(symbol)
		period = kwargs.get("period", "1mo")
		interval = kwargs.get("interval", "1d")
		hist = ticker.history(period=period, interval=interval)
		records = []
		for date, row in hist.iterrows():
			records.append({
				"date": str(date.date()),
				"open": round(row["Open"], 2),
				"high": round(row["High"], 2),
				"low": round(row["Low"], 2),
				"close": round(row["Close"], 2),
				"volume": int(row["Volume"]),
			})
		return json.dumps({
			"success": True,
			"results": {
				"symbol": symbol, 
				"period": period, 
				"data": records[-30:]
			}
		})
	except Exception as e:
		frappe.log_error(f"YFinance Error (Historical): {str(e)}", "YFinance Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_get_analyst_recommendations(**kwargs):
	"""Get analyst recommendations for a stock."""
	try:
		symbol = kwargs.get("symbol")
		if not symbol:
			return json.dumps({"success": False, "error": "Symbol is required"})
			
		ticker = _get_ticker(symbol)
		recs = ticker.recommendations
		if recs is None or recs.empty:
			return json.dumps({"success": True, "results": {"symbol": symbol, "recommendations": []}})
		
		# Convert to records and handle non-serializable objects if any
		recent = recs.tail(10).to_dict(orient="records")
		return json.dumps({
			"success": True,
			"results": {
				"symbol": symbol, 
				"recommendations": recent
			}
		})
	except Exception as e:
		frappe.log_error(f"YFinance Error (Recommendations): {str(e)}", "YFinance Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_get_company_news(**kwargs):
	"""Get recent news for a stock symbol."""
	try:
		symbol = kwargs.get("symbol")
		if not symbol:
			return json.dumps({"success": False, "error": "Symbol is required"})
			
		ticker = _get_ticker(symbol)
		news = ticker.news
		if not news:
			return json.dumps({"success": True, "results": {"symbol": symbol, "news": []}})
		
		num = int(kwargs.get("num_stories", 5))
		items = [
			{"title": n.get("title", ""), "publisher": n.get("publisher", ""), "link": n.get("link", "")}
			for n in news[:num]
		]
		return json.dumps({
			"success": True,
			"results": {
				"symbol": symbol, 
				"news": items
			}
		})
	except Exception as e:
		frappe.log_error(f"YFinance Error (News): {str(e)}", "YFinance Tool")
		return json.dumps({"success": False, "error": str(e)})
