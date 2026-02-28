// // TODO Implement this library.
//
// import 'package:flutter/material.dart';
// import 'screens/login_screen.dart';
// import 'screens/dashboard_screen.dart';
// import 'screens/admin_screen.dart';
//
// class MyApp extends StatelessWidget {
//   @override
//   Widget build(BuildContext context) {
//     return MaterialApp(
//       title: 'AI Stock Trader Alpha',
//       theme: ThemeData(
//         primarySwatch: Colors.indigo,
//       ),
//       initialRoute: '/',
//       routes: {
//         '/': (c) => LoginScreen(),
//         '/dashboard': (c) => DashboardScreen(),
//         '/admin': (c) => AdminScreen(),
//       },
//     );
//   }
// }


import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'screens/dashboard_screen.dart';

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    final baseTheme = ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
      useMaterial3: true,
    );

    return MaterialApp(
      title: 'Live LTP',
      debugShowCheckedModeBanner: false,
      theme: baseTheme.copyWith(
        textTheme: GoogleFonts.interTextTheme(baseTheme.textTheme),
      ),
      home: const DashboardScreen(),
    );
  }
}

//
// import 'package:flutter/material.dart';
// import 'package:google_fonts/google_fonts.dart';
// import 'package:provider/provider.dart';
//
// import 'providers/ltp_provider.dart';
// import 'widgets/ltp_widget.dart';
//
// void main() {
//   runApp(const MyApp());
// }
//
// class MyApp extends StatelessWidget {
//   const MyApp({super.key});
//
//   @override
//   Widget build(BuildContext context) {
//     final baseTheme = ThemeData.dark();
//
//     return MultiProvider(
//       providers: [
//         ChangeNotifierProvider(create: (_) => LtpProvider()),
//       ],
//       child: MaterialApp(
//         debugShowCheckedModeBanner: false,
//         title: 'Live LTP',
//         theme: baseTheme.copyWith(
//           textTheme: GoogleFonts.interTextTheme(baseTheme.textTheme),
//           scaffoldBackgroundColor: const Color(0xFF050816),
//           useMaterial3: true,
//           colorScheme: baseTheme.colorScheme.copyWith(
//             primary: const Color(0xFF6366F1),
//             secondary: const Color(0xFF22C55E),
//           ),
//         ),
//         home: const LtpScreen(),
//       ),
//     );
//   }
// }
