import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../widgets/ltp_widget.dart';
import '../services/api_service.dart';
import '../providers/market_data_provider.dart';
import '../app_config.dart';
import '../theme/brutal_theme.dart';
import 'brutal/brutal.dart';

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
        // Search Bar
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 20, 12),
          child: TextField(
            controller: _searchController,
            style: Brutal.mono(size: 15, weight: FontWeight.w700),
            textCapitalization: TextCapitalization.characters,
            decoration: InputDecoration(
              hintText: 'SEARCH — e.g. RELIANCE',
              prefixIcon: const Icon(Icons.search, color: Brutal.ink),
              suffixIcon: _searchController.text.isNotEmpty
                  ? IconButton(
                      tooltip: 'Clear search',
                      icon: const Icon(Icons.close, color: Brutal.ink),
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
      return const BrutalEmpty(
        title: 'Watchlist is empty',
        subtitle: 'Search above to add NSE stocks',
        icon: Icons.playlist_add,
      );
    }

    return ListView.builder(
      physics: const BouncingScrollPhysics(
          parent: AlwaysScrollableScrollPhysics()),
      padding: const EdgeInsets.only(left: 16, right: 20, bottom: 24),
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
      return const BrutalEmpty(title: 'No results found', icon: Icons.search_off);
    }

    return ListView.builder(
      physics: const BouncingScrollPhysics(
          parent: AlwaysScrollableScrollPhysics()),
      padding: const EdgeInsets.only(bottom: 24),
      itemCount: _searchResults.length,
      itemBuilder: (context, index) {
        final item = _searchResults[index];
        final symbol   = item['symbol'] ?? '';
        final name     = item['name']   ?? '';
        final exchange = item['exchange'] ?? '';

        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 20, 10),
          child: BrutalBox(
            shadow: 3,
            padding: const EdgeInsets.fromLTRB(10, 8, 6, 8),
            child: Row(
              children: [
                Container(
                  width: 38,
                  height: 38,
                  alignment: Alignment.center,
                  color: Brutal.ink,
                  child: Text(symbol.isNotEmpty ? symbol[0] : '?',
                      style: Brutal.display(
                          size: 18, weight: FontWeight.w900, color: Brutal.accent)),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(symbol,
                          style: Brutal.display(size: 15, weight: FontWeight.w800)),
                      const SizedBox(height: 2),
                      Text('$name • $exchange',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Brutal.mono(size: 11, color: Brutal.muted)),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Add $symbol to watchlist',
                  icon: const Icon(Icons.add_box, color: Brutal.ink, size: 28),
                  onPressed: () => _addToWatchlist(symbol),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
