import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import '../widgets/market_widget.dart';
import '../widgets/portfolio_widget.dart';
import '../widgets/orders_widget.dart';
import '../widgets/settings_dialog.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  int _selectedIndex = 0;

  @override
  void initState() {
    super.initState();
    // Handles the auto-login path: user had a stored token so they skip
    // LoginScreen. Both initialize() calls are idempotent.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<MarketDataProvider>().initialize();
      context.read<TradingProvider>().initialize();
    });
  }

  final List<Widget> _pages = [
    const MarketWidget(),
    const PortfolioWidget(),
    const OrdersWidget(),
  ];

  void _onItemTapped(int index) {
    setState(() => _selectedIndex = index);
    final trading = context.read<TradingProvider>();
    if (index == 1) trading.fetchPortfolio();
    if (index == 2) trading.fetchTrades();
  }

  @override
  Widget build(BuildContext context) {
    final trading = context.watch<TradingProvider>();

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('AI Stock Trader (Sandbox)'),
        centerTitle: true,
        backgroundColor: Colors.indigo,
        foregroundColor: Colors.white,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              showDialog(
                context: context,
                builder: (_) => const SettingsDialog(),
              );
            },
          ),
        ],
      ),
      body: Column(
        children: [
          // Balance & Limits header
          Container(
            padding: const EdgeInsets.all(16),
            decoration: const BoxDecoration(
              color: Colors.indigo,
              borderRadius: BorderRadius.only(
                bottomLeft: Radius.circular(24),
                bottomRight: Radius.circular(24),
              ),
            ),
            child: Column(
              children: [
                const Text(
                  'Sandbox Balance',
                  style: TextStyle(color: Colors.white70, fontSize: 14),
                ),
                Text(
                  '₹${trading.balance.toStringAsFixed(2)}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 32,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 16),
                _buildProgressBar('Daily Limit',
                    trading.dailySpent, trading.dailyLimit, Colors.orangeAccent),
                const SizedBox(height: 8),
                _buildProgressBar('Monthly Limit',
                    trading.monthlySpent, trading.monthlyLimit, Colors.purpleAccent),
              ],
            ),
          ),

          Expanded(child: _pages[_selectedIndex]),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        backgroundColor: Colors.grey[900],
        selectedItemColor: Colors.indigoAccent,
        unselectedItemColor: Colors.white54,
        currentIndex: _selectedIndex,
        onTap: _onItemTapped,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.candlestick_chart),
            label: 'Market',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.pie_chart),
            label: 'Portfolio',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.history),
            label: 'Orders',
          ),
        ],
      ),
    );
  }

  Widget _buildProgressBar(
      String label, double spent, double limit, Color color) {
    final progress = limit > 0 ? (spent / limit).clamp(0.0, 1.0) : 0.0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: const TextStyle(color: Colors.white70, fontSize: 12)),
            Text(
              '₹${spent.toStringAsFixed(0)} / ₹${limit.toStringAsFixed(0)}',
              style: const TextStyle(color: Colors.white, fontSize: 12),
            ),
          ],
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(
          value: progress,
          backgroundColor: Colors.white24,
          color: color,
          borderRadius: BorderRadius.circular(4),
        ),
      ],
    );
  }
}
