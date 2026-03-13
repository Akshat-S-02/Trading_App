import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../widgets/ltp_widget.dart';
import '../services/api_service.dart';
import '../providers/market_data_provider.dart';
import '../providers/health_provider.dart';
import '../app_config.dart';

class MarketWidget extends StatefulWidget {
  const MarketWidget({super.key});

  @override
  State<MarketWidget> createState() => _MarketWidgetState();
}

class _MarketWidgetState extends State<MarketWidget> {
  List<dynamic> _searchResults = [];
  bool _isSearching = false;
  final TextEditingController _searchController = TextEditingController();
  final ApiService _api = ApiService(backendBase: '$kHttpBase/api/market');

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Feed Freshness Indicator
        Consumer<HealthProvider>(
          builder: (context, health, child) {
            final isLive = health.isFeedHealthy;
            final isStale = health.isFeedConnected && !isLive;
            if (isLive) {
              return Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 16),
                color: Colors.green.withOpacity(0.1),
                child: const Text('Feed: 🟢 Live',
                  style: TextStyle(color: Colors.greenAccent, fontWeight: FontWeight.bold, fontSize: 12),
                  textAlign: TextAlign.center,
                ),
              );
            } else {
              return Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                color: Colors.red[900],
                child: Column(
                  children: [
                    const Text('🔴 MARKET DATA STALE',
                      style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14, letterSpacing: 1.2),
                    ),
                    const SizedBox(height: 4),
                    Text(isStale ? 'Last tick: ${health.lastTickAgeSec.toStringAsFixed(1)}s ago' : 'WebSocket is DISCONNECTED',
                      style: const TextStyle(color: Colors.white70, fontSize: 13),
                    ),
                  ],
                ),
              );
            }
          },
        ),

        // Search Bar
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: TextField(
            controller: _searchController,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              hintText: 'Search stocks (e.g. RELIANCE)...',
              hintStyle: const TextStyle(color: Colors.white54),
              prefixIcon: const Icon(Icons.search, color: Colors.white54),
              filled: true,
              fillColor: Colors.grey[900],
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
              suffixIcon: _searchController.text.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear, color: Colors.white54),
                      onPressed: () {
                        _searchController.clear();
                        _performSearch('');
                      },
                    )
                  : null,
            ),
            onChanged: _performSearch,
          ),
        ),

        Expanded(
          child: _isSearching ? _buildSearchResults() : _buildWatchlist(),
        ),
      ],
    );
  }

  Future<void> _performSearch(String query) async {
    if (query.isEmpty) {
      setState(() { _isSearching = false; _searchResults = []; });
      return;
    }
    try {
      final results = await _api.searchStocks(query);
      setState(() { _isSearching = true; _searchResults = results; });
    } catch (e) {
      debugPrint('Search failed: $e');
    }
  }

  void _addToWatchlist(String symbol) {
    final s = symbol.endsWith('.NS') ? symbol : '$symbol.NS';
    context.read<MarketDataProvider>().addToWatchlist(s);
    setState(() {
      _searchController.clear();
      _isSearching = false;
      _searchResults = [];
    });
  }

  void _removeFromWatchlist(String symbol) {
    context.read<MarketDataProvider>().removeFromWatchlist(symbol);
  }

  Widget _buildWatchlist() {
    final watchlist = context.watch<MarketDataProvider>().watchlist;

    if (watchlist.isEmpty) {
      return const Center(
        child: Text('Watchlist is empty',
            style: TextStyle(color: Colors.white54)),
      );
    }

    return ListView.builder(
      physics: const BouncingScrollPhysics(
          parent: AlwaysScrollableScrollPhysics()),
      padding: const EdgeInsets.only(left: 16, right: 16, bottom: 80),
      itemCount: watchlist.length,
      itemBuilder: (context, index) {
        final symbol = watchlist[index];
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: LtpWidget(
            symbol: symbol,
            onRemove: () => _removeFromWatchlist(symbol),
          ),
        );
      },
    );
  }

  Widget _buildSearchResults() {
    if (_searchResults.isEmpty) {
      return const Center(
          child: Text('No results found',
              style: TextStyle(color: Colors.white54)));
    }

    return ListView.builder(
      physics: const BouncingScrollPhysics(
          parent: AlwaysScrollableScrollPhysics()),
      padding: const EdgeInsets.only(bottom: 80),
      itemCount: _searchResults.length,
      itemBuilder: (context, index) {
        final item = _searchResults[index];
        final symbol   = item['symbol'] ?? '';
        final name     = item['name']   ?? '';
        final exchange = item['exchange'] ?? '';

        return ListTile(
          leading: CircleAvatar(
            backgroundColor: Colors.indigoAccent,
            child: Text(symbol.isNotEmpty ? symbol[0] : '?',
                style: const TextStyle(color: Colors.white)),
          ),
          title: Text(symbol,
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.bold)),
          subtitle: Text('$name • $exchange',
              style: const TextStyle(color: Colors.white70)),
          trailing: IconButton(
            icon: const Icon(Icons.add_circle, color: Colors.greenAccent),
            onPressed: () => _addToWatchlist(symbol),
          ),
        );
      },
    );
  }
}
