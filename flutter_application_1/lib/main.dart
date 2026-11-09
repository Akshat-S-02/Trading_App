import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'providers/auth_provider.dart';
import 'providers/market_data_provider.dart';
import 'providers/trading_provider.dart';
import 'providers/health_provider.dart';
import 'screens/dashboard_screen.dart';
import 'screens/login_screen.dart';
import 'services/auth_service.dart';
import 'ui/theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Require password on every cold start for security
  await AuthService.logout();
  AuthService.onSessionExpired = () {
    _navigatorKey.currentState?.pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen(sessionExpired: true)),
      (_) => false,
    );
  };
  runApp(const MyApp(isLoggedIn: false));
}

final _navigatorKey = GlobalKey<NavigatorState>();

class MyApp extends StatelessWidget {
  final bool isLoggedIn;
  const MyApp({super.key, required this.isLoggedIn});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => AuthProvider(isLoggedIn: isLoggedIn),
        ),
        ChangeNotifierProvider(
          create: (_) => MarketDataProvider(),
        ),
        ChangeNotifierProvider(
          create: (_) => TradingProvider(),
        ),
        ChangeNotifierProvider(
          create: (_) => HealthProvider(),
        ),
      ],
      child: MaterialApp(
        navigatorKey: _navigatorKey,
        debugShowCheckedModeBanner: false,
        title: 'AI Stock Trader (Sandbox)',
        theme: buildAppTheme(),
        themeMode: ThemeMode.dark,
        home: isLoggedIn ? const DashboardScreen() : const LoginScreen(),
      ),
    );
  }
}
