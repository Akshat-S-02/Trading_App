import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../widgets/ltp_widget.dart';
import '../services/api_service.dart';
import '../providers/trading_provider.dart';

class MarketWidget extends StatefulWidget {
  const MarketWidget({super.key});

  @override
  State<MarketWidget> createState() => _MarketWidgetState();
}

class _MarketWidgetState extends State<MarketWidget> {
  // Local state removed, using Provider


  
  // Search state
  List<dynamic> _searchResults = [];
  bool _isSearching = false;
  final TextEditingController _searchController = TextEditingController();
  final ApiService _api = ApiService(backendBase: 'http://10.0.2.2:8000/api/market'); // Adjust base URL if needed

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Search Bar
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: TextField(
            controller: _searchController,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              hintText: "Search stocks (e.g. RELIANCE)...",
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
                         _performSearch("");
                      },
                    )
                  : null,
            ),
            onChanged: (val) => _performSearch(val),
          ),
        ),

        // Results List
        Expanded(
          child: _isSearching 
            ? _buildSearchResults() 
            : _buildWatchlist(),
        ),
      ],
    );
  }

  Future<void> _performSearch(String query) async {
    if (query.isEmpty) {
      setState(() {
        _isSearching = false;
        _searchResults = [];
      });
      return;
    }

    try {
      final results = await _api.searchStocks(query);
      setState(() {
        _isSearching = true;
        _searchResults = results;
      });
    } catch (e) {
      print("Search failed: $e");
    }
  }

  void _addToWatchlist(String symbol) {
    String s = symbol.endsWith(".NS") ? symbol : "$symbol.NS";
    
    // Add to provider (which handles persistence and uniqueness)
    context.read<TradingProvider>().addToWatchlist(s);
    
    setState(() {
        _searchController.clear();
        _isSearching = false;
        _searchResults = [];
    });
  }

  void _removeFromWatchlist(String symbol) {
    context.read<TradingProvider>().removeFromWatchlist(symbol);
  }

  Widget _buildWatchlist() {
    final watchlist = context.watch<TradingProvider>().watchlist;
    
    if (watchlist.isEmpty) {
      return const Center(
        child: Text("Watchlist is empty", style: TextStyle(color: Colors.white54)),
      );
    }

    return ListView.builder(
      physics: const BouncingScrollPhysics(parent: AlwaysScrollableScrollPhysics()),
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
        return const Center(child: Text("No results found", style: TextStyle(color: Colors.white54)));
    }

    return ListView.builder(
      physics: const BouncingScrollPhysics(parent: AlwaysScrollableScrollPhysics()),
      padding: const EdgeInsets.only(bottom: 80),
      itemCount: _searchResults.length,
      itemBuilder: (context, index) {
        final item = _searchResults[index];
        final symbol = item['symbol'] ?? "";
        final name = item['name'] ?? "";
        final exchange = item['exchange'] ?? "";

        return ListTile(
          leading: CircleAvatar(
             backgroundColor: Colors.indigoAccent,
             child: Text(symbol.isNotEmpty ? symbol[0] : "?", style: const TextStyle(color: Colors.white)),
          ),
          title: Text(symbol, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          subtitle: Text("$name • $exchange", style: const TextStyle(color: Colors.white70)),
          trailing: IconButton(
            icon: const Icon(Icons.add_circle, color: Colors.greenAccent),
            onPressed: () => _addToWatchlist(symbol),
          ),
        );
      },
    );
  }
}
