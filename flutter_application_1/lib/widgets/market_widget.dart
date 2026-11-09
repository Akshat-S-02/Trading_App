import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../widgets/ltp_widget.dart';
import '../services/api_service.dart';
import '../providers/market_data_provider.dart';
import '../providers/health_provider.dart';
import '../utils/format.dart';
import '../app_config.dart';
import '../ui/components.dart';
import '../ui/theme.dart';
import '../screens/chart_screen.dart';

class MarketWidget extends StatefulWidget {
  const MarketWidget({super.key});

  @override
  State<MarketWidget> createState() => _MarketWidgetState();
}

class _MarketWidgetState extends State<MarketWidget> {
  List<dynamic> _searchResults = [];
  bool _isSearching = false;
  bool _loading = false;
  Timer? _debounce;
  final TextEditingController _searchController = TextEditingController();
  final ApiService _api = ApiService(backendBase: '$kHttpBase/api/market');

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _feedBanner(),

        // Search Bar
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: TextField(
            controller: _searchController,
            textCapitalization: TextCapitalization.characters,
            decoration: InputDecoration(
              hintText: 'Search stocks to add',
              isDense: true,
              contentPadding: const EdgeInsets.symmetric(vertical: 11),
              prefixIcon: const Icon(Icons.search_rounded),
              suffixIcon: _searchController.text.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.cancel_rounded, size: 20),
                      onPressed: () {
                        _searchController.clear();
                        _onQueryChanged('');
                      },
                    )
                  : null,
            ),
            onChanged: _onQueryChanged,
          ),
        ),
        SizedBox(
          height: 2,
          child: _loading ? const LinearProgressIndicator(minHeight: 2) : null,
        ),

        Expanded(
          child: _isSearching ? _buildSearchResults() : _buildWatchlist(),
        ),
      ],
    );
  }

  Widget _feedBanner() {
    return Consumer<HealthProvider>(
      builder: (context, health, child) {
        if (health.isFeedHealthy) return const SizedBox.shrink();
        final isStale = health.isFeedConnected;
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
          child: Surface(
            color: AppColors.red.withValues(alpha: 0.14),
            padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
            child: Row(
              children: [
                const Icon(Icons.wifi_off_rounded, size: 18, color: AppColors.red),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    isStale
                        ? 'Prices are stale. Last tick ${health.lastTickAgeSec.toStringAsFixed(0)}s ago.'
                        : 'Market feed disconnected. Prices may be out of date.',
                    style: AppText.footnote.copyWith(color: AppColors.label),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _onQueryChanged(String query) {
    setState(() {}); // refresh clear button
    _debounce?.cancel();
    if (query.trim().isEmpty) {
      setState(() {
        _isSearching = false;
        _searchResults = [];
        _loading = false;
      });
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 300), () => _performSearch(query.trim()));
  }

  Future<void> _performSearch(String query) async {
    setState(() => _loading = true);
    try {
      final results = await _api.searchStocks(query);
      if (!mounted || _searchController.text.trim() != query) return;
      setState(() {
        _isSearching = true;
        _searchResults = results;
      });
    } catch (e) {
      debugPrint('Search failed: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _normalized(String symbol) => symbol.endsWith('.NS') ? symbol : '$symbol.NS';

  void _addToWatchlist(String symbol) {
    context.read<MarketDataProvider>().addToWatchlist(_normalized(symbol));
    FocusScope.of(context).unfocus();
    setState(() {
      _searchController.clear();
      _isSearching = false;
      _searchResults = [];
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('${bareSymbol(symbol)} added to watchlist'),
          duration: const Duration(seconds: 2)),
    );
  }

  void _removeFromWatchlist(String symbol) {
    final market = context.read<MarketDataProvider>();
    final index = market.watchlist.indexOf(symbol);
    market.removeFromWatchlist(symbol);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text('${bareSymbol(symbol)} removed'),
      action: SnackBarAction(
        label: 'UNDO',
        onPressed: () => market.restoreToWatchlist(symbol, index),
      ),
    ));
  }

  Widget _buildWatchlist() {
    final watchlist = context.watch<MarketDataProvider>().watchlist;

    if (watchlist.isEmpty) {
      return const Center(
        child: EmptyState(
          icon: Icons.star_outline_rounded,
          title: 'No stocks yet',
          message: 'Search above to add stocks to your watchlist.',
        ),
      );
    }

    return Column(
      children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(20, 6, 20, 8),
          child: Text('Tap for chart · B/S to trade · swipe left to remove · hold to reorder',
              style: AppText.caption),
        ),
        Expanded(
          child: ReorderableListView.builder(
            padding: EdgeInsets.only(left: 16, right: 16, bottom: bottomInset(context)),
            proxyDecorator: (child, _, __) => Material(color: Colors.transparent, child: child),
            itemCount: watchlist.length,
            onReorderItem: (oldI, newI) =>
                context.read<MarketDataProvider>().reorderWatchlist(oldI, newI),
            itemBuilder: (context, index) {
              final symbol = watchlist[index];
              return Padding(
                key: ValueKey(symbol),
                padding: const EdgeInsets.only(bottom: 10),
                child: Dismissible(
                  key: ValueKey('dismiss_$symbol'),
                  direction: DismissDirection.endToStart,
                  background: Container(
                    alignment: Alignment.centerRight,
                    padding: const EdgeInsets.only(right: 24),
                    decoration: ShapeDecoration(color: AppColors.red, shape: rounded(16)),
                    child: const Text('Remove',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                  ),
                  onDismissed: (_) => _removeFromWatchlist(symbol),
                  child: LtpWidget(symbol: symbol),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildSearchResults() {
    if (_searchResults.isEmpty) {
      return const Center(
          child: EmptyState(icon: Icons.search_off_rounded, title: 'No matches',
              message: 'Try the NSE symbol, e.g. RELIANCE or TCS.'));
    }
    final watchlist = context.watch<MarketDataProvider>().watchlist;

    return ListView.builder(
      padding: EdgeInsets.only(bottom: bottomInset(context)),
      itemCount: _searchResults.length,
      itemBuilder: (context, index) {
        final item = _searchResults[index];
        final symbol   = (item['symbol'] ?? '').toString();
        final name     = (item['name']   ?? '').toString();
        final exchange = (item['exchange'] ?? '').toString();
        final inList = watchlist.contains(_normalized(symbol));

        return ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 20),
          leading: Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: ShapeDecoration(color: AppColors.elevated, shape: rounded(10)),
            child: Text(symbol.isNotEmpty ? symbol[0] : '?', style: AppText.headline),
          ),
          title: Text(symbol, style: AppText.headline),
          subtitle: Text('$name · $exchange', maxLines: 1, overflow: TextOverflow.ellipsis),
          onTap: () => openChart(context, _normalized(symbol)),
          trailing: IconButton(
            tooltip: inList ? 'In watchlist' : 'Add to watchlist',
            icon: Icon(inList ? Icons.check_circle_rounded : Icons.add_circle_rounded,
                color: inList ? AppColors.tertiary : AppColors.accent),
            onPressed: inList ? null : () => _addToWatchlist(symbol),
          ),
        );
      },
    );
  }
}
