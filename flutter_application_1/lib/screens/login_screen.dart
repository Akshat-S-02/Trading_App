import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import '../app_config.dart';
import 'dashboard_screen.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

class LoginScreen extends StatefulWidget {
  /// True when shown because a 401 ended the session (token expired).
  final bool sessionExpired;
  const LoginScreen({super.key, this.sessionExpired = false});

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
    final success = await auth.login(AppConfig.username, _passwordCtrl.text.trim());
    if (!success) HapticFeedback.heavyImpact();
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
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 28),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: AutofillGroup(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Center(
                      child: Container(
                        width: 76,
                        height: 76,
                        decoration: ShapeDecoration(
                          shape: rounded(20),
                          gradient: const LinearGradient(
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                            colors: [Color(0xFF3B9BFF), AppColors.accent, AppColors.indigo],
                          ),
                        ),
                        child: const Icon(Icons.show_chart_rounded, color: Colors.white, size: 40),
                      ),
                    ),
                    const SizedBox(height: 24),
                    const Text('Trading Sandbox', textAlign: TextAlign.center, style: AppText.largeTitle),
                    const SizedBox(height: 6),
                    Text(
                        widget.sessionExpired
                            ? 'Your session expired. Enter your password to continue.'
                            : 'Enter your password to continue.',
                        textAlign: TextAlign.center,
                        style: AppText.callout),
                    const SizedBox(height: 36),
                    // Single-account backend: username is fixed, shown for context only.
                    TextFormField(
                      initialValue: AppConfig.username,
                      readOnly: true,
                      enabled: false,
                      decoration: const InputDecoration(
                        labelText: 'Username',
                        prefixIcon: Icon(Icons.person_outline_rounded),
                        suffixIcon: Icon(Icons.lock_rounded, size: 18),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _passwordCtrl,
                      autofocus: true,
                      obscureText: _obscure,
                      autofillHints: const [AutofillHints.password],
                      textInputAction: TextInputAction.go,
                      onSubmitted: (_) => _login(),
                      decoration: InputDecoration(
                        labelText: 'Password',
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
                        suffixIcon: IconButton(
                          tooltip: _obscure ? 'Show password' : 'Hide password',
                          icon: Icon(_obscure ? Icons.visibility_off_outlined : Icons.visibility_outlined),
                          onPressed: () => setState(() => _obscure = !_obscure),
                        ),
                      ),
                    ),
                    AnimatedSize(
                      duration: motionDuration(context, 220),
                      curve: motionCurve,
                      alignment: Alignment.topCenter,
                      child: auth.error == null
                          ? const SizedBox(width: double.infinity)
                          : Padding(
                              padding: const EdgeInsets.only(top: 12, left: 4),
                              child: Text(auth.error!, style: AppText.footnote.copyWith(color: AppColors.red)),
                            ),
                    ),
                    const SizedBox(height: 24),
                    FilledButton(
                      onPressed: auth.loading ? null : _login,
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        textStyle: AppText.headline,
                      ),
                      child: auth.loading
                          ? const SizedBox(
                              width: 22, height: 22,
                              child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5))
                          : const Text('Unlock'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
