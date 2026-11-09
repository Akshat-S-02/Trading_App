import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../services/websocket_service.dart';
import '../services/auth_service.dart';
import '../app_config.dart';

/// Owns everything related to live market data:
///   - WebSocket connection + price map
///   - Watchlist (with SharedPreferences persistence)
///   - Snapshot HTTP fetch to seed prices immediately
class MarketDataProvider with ChangeNotifier {
  // ── Price map ────────────────────────────────────────────────────────────────
  final Map<String, dynamic> _prices = {};
  Map<String, dynamic> get prices => _prices;

  double? getPrice(String symbol) => (_prices[symbol] as num?)?.toDouble();

  // ── Watchlist ────────────────────────────────────────────────────────────────
  List<String> _watchlist = [];
  List<String> get watchlist => _watchlist;

  // ── WebSocket ────────────────────────────────────────────────────────────────
  WebSocketService? _wsService;
  bool _initialized = false;

  final String _baseUrl = kHttpBase;

  MarketDataProvider() {
    _loadWatchlist();
  }

  /// Start WebSocket and subscribe all current watchlist symbols.
  /// Idempotent — safe to call multiple times (e.g. from both LoginScreen and DashboardScreen).
  void initialize() {
    if (_initialized) return;
    _initialized = true;
    _connectWebSocket();
  }

  Future<void> _connectWebSocket() async {
    if (_disposed) return;
    // Fresh token each attempt: after a re-login the old one is gone.
    final token = await AuthService.getToken();
    final query = token != null ? '?token=$token' : '';
    _wsService?.dispose();
    _wsService = WebSocketService(
      url: '$kWsBase/ws/market$query',
      onMessage: (msg) {
        _reconnectDelay = _minReconnectDelay; // data is flowing again
        _ingest(msg);
      },
      onDone: () => _scheduleReconnect('closed'),
      onError: (e) => _scheduleReconnect('error: $e'),
    );
    _wsService!.connect();
  }

  // The socket drops on server deploys, network changes and phone sleep.
  // Without this the price map silently freezes until the app restarts.
  static const _minReconnectDelay = Duration(seconds: 2);
  static const _maxReconnectDelay = Duration(seconds: 30);
  Duration _reconnectDelay = _minReconnectDelay;
  Timer? _reconnectTimer;
  bool _disposed = false;

  void _scheduleReconnect(String why) {
    if (_disposed || (_reconnectTimer?.isActive ?? false)) return;
    debugPrint('MarketData WS $why; reconnecting in ${_reconnectDelay.inSeconds}s');
    _reconnectTimer = Timer(_reconnectDelay, _connectWebSocket);
    final next = _reconnectDelay * 2;
    _reconnectDelay = next > _maxReconnectDelay ? _maxReconnectDelay : next;
  }

  @override
  void dispose() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _wsService?.dispose();
    super.dispose();
  }

  // ── Watchlist persistence ────────────────────────────────────────────────────

  Future<void> _loadWatchlist() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getStringList('watchlist');
      if (saved != null && saved.isNotEmpty) {
        _watchlist = saved;
      } else {
        _watchlist = [
          'RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS',
          'SBIN.NS', 'ICICIBANK.NS', 'AXISBANK.NS', 'KOTAKBANK.NS',
          'ITC.NS', 'LT.NS', 'BHARTIARTL.NS', 'ASIANPAINT.NS',
          'MARUTI.NS', 'HCLTECH.NS', 'SUNPHARMA.NS', 'TITAN.NS',
          'BAJFINANCE.NS', 'ULTRACEMCO.NS', 'M&M.NS', 'TATASTEEL.NS',
        ];
        await _saveWatchlist();
      }
      notifyListeners();

      // Seed prices for all watchlist symbols in one fast batch request
      _seedWatchlistPricesBatch();
    } catch (e) {
      debugPrint('Error loading watchlist: $e');
    }
  }

  Future<void> _seedWatchlistPricesBatch() async {
    if (_watchlist.isEmpty) return;

    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/market/ltp/batch'),
        headers: await AuthService.authHeaders(),
        body: jsonEncode({'symbols': _watchlist}),
      );

      AuthService.checkAuth(response);

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final results = data['results'] as Map<String, dynamic>?;
        if (results != null) {
          bool updated = false;
          results.forEach((bareSymbol, info) {
            final ltp = info['ltp'];
            if (ltp != null && ltp != 0) {
              final price = (ltp is num) ? ltp.toDouble() : double.tryParse(ltp.toString());
              if (price != null && price > 0) {
                _prices['$bareSymbol.NS'] = price;
                _prices[bareSymbol] = price;
                updated = true;
              }
            }
          });
          if (updated) notifyListeners();
        }
      }
    } catch (e) {
      debugPrint('Batch subscription failed: $e');
    }
  }

  Future<void> _saveWatchlist() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList('watchlist', _watchlist);
    } catch (e) {
      debugPrint('Error saving watchlist: $e');
    }
  }

  void addToWatchlist(String symbol) {
    if (!_watchlist.contains(symbol)) {
      _watchlist.insert(0, symbol);
      _saveWatchlist();
      notifyListeners();
      
      // For a single symbol added by the user, we can still use the batch API
      // just with an array of 1, to keep it simple.
      _seedSinglePrice(symbol);
    }
  }

  void removeFromWatchlist(String symbol) {
    if (_watchlist.remove(symbol)) {
      _saveWatchlist();
      notifyListeners();
    }
  }

  /// Undo a removal: put [symbol] back at its old position.
  void restoreToWatchlist(String symbol, int index) {
    if (_watchlist.contains(symbol)) return;
    _watchlist.insert(index.clamp(0, _watchlist.length), symbol);
    _saveWatchlist();
    notifyListeners();
  }

  /// [newIndex] is already adjusted for the removed item (onReorderItem).
  void reorderWatchlist(int oldIndex, int newIndex) {
    final item = _watchlist.removeAt(oldIndex);
    _watchlist.insert(newIndex, item);
    _saveWatchlist();
    notifyListeners();
  }

  /// Make sure [symbol] has a price (and that the backend subscribes to it),
  /// e.g. when trading a stock that isn't in the watchlist.
  void ensurePrice(String symbol) {
    if (getPrice(symbol) == null) _seedSinglePrice(symbol);
  }

  // ── HTTP snapshot to seed price + tell backend to subscribe ─────────────────

  Future<void> _seedSinglePrice(String symbol) async {
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/market/ltp/batch'),
        headers: await AuthService.authHeaders(),
        body: jsonEncode({'symbols': [symbol]}),
      );
      AuthService.checkAuth(response);
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final results = data['results'] as Map<String, dynamic>?;
        if (results != null) {
          results.forEach((bareSymbol, info) {
            final ltp = info['ltp'];
            if (ltp != null && ltp != 0) {
              final price = (ltp is num) ? ltp.toDouble() : double.tryParse(ltp.toString());
              if (price != null && price > 0) {
                _prices['$bareSymbol.NS'] = price;
                _prices[bareSymbol] = price;
                notifyListeners();
              }
            }
          });
        }
      }
    } catch (e) {
      debugPrint('Single subscription failed for $symbol: $e');
    }
  }

  // ── WebSocket message ingestion ──────────────────────────────────────────────

  void _ingest(dynamic msg) {
    try {
      final data = msg is String ? jsonDecode(msg) : msg;

      if (data is List) {
        for (final item in data) {
          if (item is Map && item.containsKey('symbol') && item.containsKey('LTP')) {
            _updatePrice(item['symbol'] as String, item['LTP']);
          }
        }
        notifyListeners();
      } else if (data is Map && data.containsKey('symbol') && data.containsKey('LTP')) {
        _updatePrice(data['symbol'] as String, data['LTP']);
        notifyListeners();
      }
    } catch (e) {
      debugPrint('⚠️ MarketData WS ingest error: $e');
    }
  }

  void _updatePrice(String symbol, dynamic ltp) {
    // Backend sends bare symbol (e.g. "RELIANCE"). Store both variants so
    // widgets can look up by either "RELIANCE" or "RELIANCE.NS".
    final normalized = symbol.endsWith('.NS') ? symbol : '$symbol.NS';
    _prices[symbol] = ltp;
    _prices[normalized] = ltp;
  }
}
