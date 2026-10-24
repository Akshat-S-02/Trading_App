import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import 'dashboard_screen.dart';
import '../theme/brutal_theme.dart';
import '../widgets/brutal/brutal.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _passwordCtrl = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    final auth = context.read<AuthProvider>();
    final success = await auth.login('admin', _passwordCtrl.text.trim());
    if (success && mounted) {
      // Initialize market data and trading data now that we're authenticated
      context.read<MarketDataProvider>().initialize();
      context.read<TradingProvider>().initialize();
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const DashboardScreen()),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    return Scaffold(
      body: Stack(
        children: [
          // Oversized background type — pure brutalist texture.
          Positioned(
            left: -12,
            bottom: -40,
            child: IgnorePointer(
              child: Text(
                'TRADE',
                style: Brutal.display(
                  size: 200,
                  weight: FontWeight.w900,
                  color: Brutal.ink.withValues(alpha: 0.06),
                ),
              ),
            ),
          ),
          Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: BrutalBox(
                  shadow: 8,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const BrutalStrip(index: '00', title: 'Access Terminal'),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Row(
                              children: [
                                Container(
                                  width: 52,
                                  height: 52,
                                  color: Brutal.accent,
                                  child: const Icon(Icons.candlestick_chart,
                                      color: Brutal.ink, size: 30),
                                ),
                                const SizedBox(width: 14),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text('TRADING\nSANDBOX',
                                          style: Brutal.display(
                                              size: 28, weight: FontWeight.w900)),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 20),
                            Container(height: Brutal.border, color: Brutal.ink),
                            const SizedBox(height: 16),
                            Text('USER: ADMIN  //  PAPER MONEY ONLY',
                                style: Brutal.label()),
                            const SizedBox(height: 16),
                            TextField(
                              controller: _passwordCtrl,
                              obscureText: _obscure,
                              autofocus: true,
                              style: Brutal.mono(size: 16, weight: FontWeight.w700),
                              onSubmitted: (_) => _login(),
                              decoration: InputDecoration(
                                labelText: 'PASSWORD',
                                prefixIcon: const Icon(Icons.lock_outline,
                                    color: Brutal.ink),
                                suffixIcon: IconButton(
                                  tooltip: _obscure ? 'Show password' : 'Hide password',
                                  icon: Icon(
                                      _obscure
                                          ? Icons.visibility_off
                                          : Icons.visibility,
                                      color: Brutal.ink),
                                  onPressed: () =>
                                      setState(() => _obscure = !_obscure),
                                ),
                              ),
                            ),
                            if (auth.error != null) ...[
                              const SizedBox(height: 12),
                              Container(
                                padding: const EdgeInsets.all(10),
                                color: Brutal.down,
                                child: Text(auth.error!.toUpperCase(),
                                    style: Brutal.mono(
                                        size: 12,
                                        color: Brutal.white,
                                        weight: FontWeight.w800)),
                              ),
                            ],
                            const SizedBox(height: 20),
                            BrutalButton(
                              label: 'Unlock →',
                              expand: true,
                              height: 54,
                              fontSize: 16,
                              loading: auth.loading,
                              onPressed: auth.loading ? null : _login,
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
