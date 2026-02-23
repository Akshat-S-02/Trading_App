// import 'package:flutter/material.dart';
// import 'dart:async';
// import '../services/api_service.dart';
//
// class TradingProvider extends ChangeNotifier {
//   final ApiService _api = ApiService();
//   List<dynamic> _stocks = [];
//   List<dynamic> _portfolio = [];
//   List<dynamic> _history = [];
//   bool _isLoading = false;
//   Timer? _refreshTimer;
//   bool _isCached = false;
//
//   DateTime? _lastUpdated; // ✅ Add this
//   DateTime? get lastUpdated => _lastUpdated; // ✅ Getter
//
//   List<dynamic> get stocks => _stocks;
//   List<dynamic> get portfolio => _portfolio;
//   List<dynamic> get history => _history;
//   bool get isLoading => _isLoading;
//   bool get isCached => _isCached;
//
//
//
//   TradingProvider() {
//     loadStocks();
//     loadPortfolio();
//     loadHistory();
//
//     // Auto-refresh stock prices every 60 seconds
//     _refreshTimer = Timer.periodic(const Duration(seconds: 60), (timer) {
//       loadStocks();
//     });
//   }
//
//   Future<void> loadStocks() async {
//     try {
//       _isLoading = true;
//       notifyListeners();
//
//       final response = await _api.getStockList();
//       _stocks = response.data['stocks'];
//       _lastUpdated = DateTime.now(); // ✅ Set timestamp when new data comes
//       print("✅ Last updated set to $_lastUpdated");
//       _isCached = false;
//     } catch (e) {
//       print("Error loading stocks: $e");
//       _isCached = true;
//     } finally {
//       _isLoading = false;
//       notifyListeners(); // ✅ Trigger rebuild so UI updates
//     }
//   }
//
//   Future<void> loadPortfolio() async {
//     try {
//       final response = await _api.getPortfolio();
//       _portfolio = response.data['portfolio'];
//       notifyListeners();
//     } catch (e) {
//       print("Error loading portfolio: $e");
//     }
//   }
//
//   Future<void> loadHistory() async {
//     try {
//       final response = await _api.getHistory();
//       _history = response.data['history'];
//       notifyListeners();
//     } catch (e) {
//       print("Error loading history: $e");
//     }
//   }
//
//   @override
//   void dispose() {
//     _refreshTimer?.cancel();
//     super.dispose();
//   }
//
//   ApiService get api => _api;
//
//
// }


import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../services/websocket_service.dart';


class TradingProvider with ChangeNotifier {
  final Map<String, dynamic> _prices = {};
  Map<String, dynamic> get prices => _prices;

  // User Limits & Balance
  double _dailyLimit = 0;
  double _monthlyLimit = 0;
  double _dailySpent = 0;
  double _monthlySpent = 0;
  double _balance = 0;

  List<dynamic> _portfolio = [];
  List<dynamic> get portfolio => _portfolio;

  List<dynamic> _trades = [];
  List<dynamic> get trades => _trades;

  double get dailyLimit => _dailyLimit;
  double get monthlyLimit => _monthlyLimit;
  double get dailySpent => _dailySpent;
  double get monthlySpent => _monthlySpent;
  double get balance => _balance;

  final String _baseUrl = "http://10.0.2.2:8000"; // Android Emulator: 10.0.2.2, iOS: 127.0.0.1
  late WebSocketService _wsService;

  // Watchlist State
  List<String> _watchlist = [];
  List<String> get watchlist => _watchlist;

  TradingProvider() {
    _loadWatchlist(); // Load watchlist on startup
    fetchUserLimits();
    fetchPortfolio();
    fetchTrades();

    // Initialize WebSocket
    _wsService = WebSocketService(
      url: "ws://10.0.2.2:8000/ws/market", 
      onMessage: ingest,
      onDone: () => debugPrint("WS Done"),
      onError: (e) => debugPrint("WS Error: $e"),
    );
    _wsService.connect();
  }

  Future<void> _loadWatchlist() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final List<String>? savedDetails = prefs.getStringList('watchlist');
      if (savedDetails != null && savedDetails.isNotEmpty) {
        _watchlist = savedDetails;
      } else {
        // Default watchlist if nothing saved
        _watchlist = [
          "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS",
          "SBIN.NS", "ICICIBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS",
          "ITC.NS", "LT.NS", "BHARTIARTL.NS", "ASIANPAINT.NS",
          "MARUTI.NS", "HCLTECH.NS", "SUNPHARMA.NS", "TITAN.NS",
          "BAJFINANCE.NS", "ULTRACEMCO.NS", "M&M.NS", "TATASTEEL.NS"
        ];
        // Save defaults so they persist
        await pd_saveWatchlist(); 
      }
      notifyListeners();
      
      // Fetch prices for all valid symbols
      for (var sym in _watchlist) {
         // trigger HTTP fetch to ensure subscription on backend
         // We can use the ApiService for this if exposed, or just HTTP call
         // Ideally we use a method in this provider
         _ensureSubscription(sym); 
      }
      
    } catch (e) {
      debugPrint("Error loading watchlist: $e");
    }
  }

  Future<void> pd_saveWatchlist() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList('watchlist', _watchlist);
    } catch (e) {
      debugPrint("Error saving watchlist: $e");
    }
  }

  void addToWatchlist(String symbol) {
    if (!_watchlist.contains(symbol)) {
      _watchlist.insert(0, symbol);
      pd_saveWatchlist();
      notifyListeners();
      _ensureSubscription(symbol);
    }
  }

  void removeFromWatchlist(String symbol) {
    if (_watchlist.contains(symbol)) {
      _watchlist.remove(symbol);
      pd_saveWatchlist();
      notifyListeners();
    }
  }
  
  // Helper to ensure backend subscribes
  Future<void> _ensureSubscription(String symbol) async {
    try {
       // We can iterate api fetchLtp here. 
       // Since _api is not directly here (it was in other file), we use raw http or call the one we have if we merge.
       // The previous ApiService code handled this. 
       // Let's assume we can make a simple HTTP generic call or use the one from main.dart's pattern?
       // Actually, we can just use http.get here as we have http imported.
       final url = "$_baseUrl/api/market/ltp/$symbol"; 
       await http.get(Uri.parse(url));
    } catch (e) {
       debugPrint("Failed to ensure subscription for $symbol: $e");
    }
  }


  @override
  void dispose() {
    _wsService.dispose();
    super.dispose();
  }

  void ingest(dynamic msg) {
    try {
      final data = msg is String ? jsonDecode(msg) : msg;
      
      debugPrint("📥 WS Message: $data");
      
      // Handle List of Ticks (which is what market_ws sends)
      if (data is List) {
        debugPrint("📊 Processing ${data.length} ticks");
        for (var item in data) {
          if (item is Map && item.containsKey('symbol') && item.containsKey('LTP')) {
            debugPrint("💰 Updating ${item['symbol']} = ${item['LTP']}");
            _updatePrice(item['symbol'], item['LTP']);
          }
        }
        notifyListeners();
        debugPrint("✅ notifyListeners() called");
      } 
      // Handle Single Tick
      else if (data is Map && data.containsKey('symbol') && data.containsKey('LTP')) {
        _updatePrice(data['symbol'], data['LTP']);
        notifyListeners();
      }
    } catch (e) {
      debugPrint("⚠️ WebSocket ingest error: $e");
    }
  }

  void _updatePrice(String symbol, dynamic ltp) {
    // Backend sends "RELIANCE" but Frontend expects "RELIANCE.NS"
    // Normalize by adding .NS if missing
    String normalized = symbol;
    if (!normalized.endsWith('.NS')) {
      normalized = "$normalized.NS";
    }
    
    // Also store raw just in case
    _prices[symbol] = ltp; 
    _prices[normalized] = ltp;
  }

  double? getPrice(String symbol) {
    return _prices[symbol];
  }

  Future<void> fetchPortfolio() async {
    try {
      final response = await http.get(Uri.parse('$_baseUrl/api/portfolio'));
      if (response.statusCode == 200) {
        _portfolio = jsonDecode(response.body);
        notifyListeners();
      }
    } catch (e) {
      debugPrint("Error fetching portfolio: $e");
    }
  }

  Future<void> fetchTrades() async {
    try {
      final response = await http.get(Uri.parse('$_baseUrl/api/trades'));
      if (response.statusCode == 200) {
        _trades = jsonDecode(response.body);
        notifyListeners();
      }
    } catch (e) {
      debugPrint("Error fetching trades: $e");
    }
  }

  Future<void> fetchUserLimits() async {
    try {
      final response = await http.get(Uri.parse('$_baseUrl/api/admin/limits'));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _dailyLimit = (data['daily_limit'] ?? 0).toDouble();
        _monthlyLimit = (data['monthly_limit'] ?? 0).toDouble();
        _dailySpent = (data['daily_spent'] ?? 0).toDouble();
        _monthlySpent = (data['monthly_spent'] ?? 0).toDouble();
        _balance = (data['tokens'] ?? 0).toDouble();
        notifyListeners();
      } else {
        debugPrint("Failed to fetch limits: ${response.statusCode}");
      }
    } catch (e) {
      debugPrint("Error fetching limits: $e");
    }
  }

  Future<bool> setLimits(double daily, double monthly) async {
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/admin/limits'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'daily_limit': daily,
          'monthly_limit': monthly,
        }),
      );
      if (response.statusCode == 200) {
        await fetchUserLimits(); // Refresh
        return true;
      } else {
        debugPrint("Failed to set limits. Status: ${response.statusCode}, Body: ${response.body}");
      }
    } catch (e) {
      debugPrint("Error setting limits: $e");
    }
    return false;
  }
}
