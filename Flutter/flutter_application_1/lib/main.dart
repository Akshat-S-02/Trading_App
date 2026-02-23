// // // // import 'package:flutter/material.dart';
// // // //
// // // // void main() {
// // // //   runApp(const MyApp());
// // // // }
// // // //
// // // // class MyApp extends StatelessWidget {
// // // //   const MyApp({super.key});
// // // //
// // // //   // This widget is the root of your application.
// // // //   @override
// // // //   Widget build(BuildContext context) {
// // // //     return MaterialApp(
// // // //       title: 'Flutter Demo',
// // // //       theme: ThemeData(
// // // //         // This is the theme of your application.
// // // //         //
// // // //         // TRY THIS: Try running your application with "flutter run". You'll see
// // // //         // the application has a purple toolbar. Then, without quitting the app,
// // // //         // try changing the seedColor in the colorScheme below to Colors.green
// // // //         // and then invoke "hot reload" (save your changes or press the "hot
// // // //         // reload" button in a Flutter-supported IDE, or press "r" if you used
// // // //         // the command line to start the app).
// // // //         //
// // // //         // Notice that the counter didn't reset back to zero; the application
// // // //         // state is not lost during the reload. To reset the state, use hot
// // // //         // restart instead.
// // // //         //
// // // //         // This works for code too, not just values: Most code changes can be
// // // //         // tested with just a hot reload.
// // // //         colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
// // // //       ),
// // // //       home: const MyHomePage(title: 'Flutter Demo Home Page'),
// // // //     );
// // // //   }
// // // // }
// // // //
// // // // class MyHomePage extends StatefulWidget {
// // // //   const MyHomePage({super.key, required this.title});
// // // //
// // // //   // This widget is the home page of your application. It is stateful, meaning
// // // //   // that it has a State object (defined below) that contains fields that affect
// // // //   // how it looks.
// // // //
// // // //   // This class is the configuration for the state. It holds the values (in this
// // // //   // case the title) provided by the parent (in this case the App widget) and
// // // //   // used by the build method of the State. Fields in a Widget subclass are
// // // //   // always marked "final".
// // // //
// // // //   final String title;
// // // //
// // // //   @override
// // // //   State<MyHomePage> createState() => _MyHomePageState();
// // // // }
// // // //
// // // // class _MyHomePageState extends State<MyHomePage> {
// // // //   int _counter = 0;
// // // //
// // // //   void _incrementCounter() {
// // // //     setState(() {
// // // //       // This call to setState tells the Flutter framework that something has
// // // //       // changed in this State, which causes it to rerun the build method below
// // // //       // so that the display can reflect the updated values. If we changed
// // // //       // _counter without calling setState(), then the build method would not be
// // // //       // called again, and so nothing would appear to happen.
// // // //       _counter++;
// // // //     });
// // // //   }
// // // //
// // // //   @override
// // // //   Widget build(BuildContext context) {
// // // //     // This method is rerun every time setState is called, for instance as done
// // // //     // by the _incrementCounter method above.
// // // //     //
// // // //     // The Flutter framework has been optimized to make rerunning build methods
// // // //     // fast, so that you can just rebuild anything that needs updating rather
// // // //     // than having to individually change instances of widgets.
// // // //     return Scaffold(
// // // //       appBar: AppBar(
// // // //         // TRY THIS: Try changing the color here to a specific color (to
// // // //         // Colors.amber, perhaps?) and trigger a hot reload to see the AppBar
// // // //         // change color while the other colors stay the same.
// // // //         backgroundColor: Theme.of(context).colorScheme.inversePrimary,
// // // //         // Here we take the value from the MyHomePage object that was created by
// // // //         // the App.build method, and use it to set our appbar title.
// // // //         title: Text(widget.title),
// // // //       ),
// // // //       body: Center(
// // // //         // Center is a layout widget. It takes a single child and positions it
// // // //         // in the middle of the parent.
// // // //         child: Column(
// // // //           // Column is also a layout widget. It takes a list of children and
// // // //           // arranges them vertically. By default, it sizes itself to fit its
// // // //           // children horizontally, and tries to be as tall as its parent.
// // // //           //
// // // //           // Column has various properties to control how it sizes itself and
// // // //           // how it positions its children. Here we use mainAxisAlignment to
// // // //           // center the children vertically; the main axis here is the vertical
// // // //           // axis because Columns are vertical (the cross axis would be
// // // //           // horizontal).
// // // //           //
// // // //           // TRY THIS: Invoke "debug painting" (choose the "Toggle Debug Paint"
// // // //           // action in the IDE, or press "p" in the console), to see the
// // // //           // wireframe for each widget.
// // // //           mainAxisAlignment: MainAxisAlignment.center,
// // // //           children: <Widget>[
// // // //             const Text('You have pushed the button this many times:'),
// // // //             Text(
// // // //               '$_counter',
// // // //               style: Theme.of(context).textTheme.headlineMedium,
// // // //             ),
// // // //           ],
// // // //         ),
// // // //       ),
// // // //       floatingActionButton: FloatingActionButton(
// // // //         onPressed: _incrementCounter,
// // // //         tooltip: 'Increment',
// // // //         child: const Icon(Icons.add),
// // // //       ), // This trailing comma makes auto-formatting nicer for build methods.
// // // //     );
// // // //   }
// // // // }
// // //
// // // import 'package:flutter/material.dart';
// // // import 'package:provider/provider.dart';
// // // import 'providers/trading_provider.dart';
// // // import 'screens/dashboard_screen.dart';
// // //
// // // void main() {
// // //   WidgetsFlutterBinding.ensureInitialized();
// // //   runApp(
// // //     MultiProvider(
// // //       providers: [
// // //         ChangeNotifierProvider(create: (_) => TradingProvider()),
// // //       ],
// // //       child: const MyApp(),
// // //     ),
// // //   );
// // // }
// // //
// // // class MyApp extends StatelessWidget {
// // //   const MyApp({super.key});
// // //   @override
// // //   Widget build(BuildContext context) {
// // //     return MaterialApp(
// // //       debugShowCheckedModeBanner: false,
// // //       title: 'AI Stock Trader (Alpha)',
// // //       theme: ThemeData.dark(),
// // //       home: const DashboardScreen(),
// // //     );
// // //   }
// // // }
// // //
// // //
// // //
// // //
// // //
// // //
// //
// // // main.dart (snippet)
// // import 'package:flutter/material.dart';
// // import 'package:provider/provider.dart';
// // import 'websocket_service.dart';
// // import 'trading_provider.dart';
// // import 'api_service.dart';
// // import 'dashboard_screen.dart';
// //
// // void main() {
// //   runApp(MyApp());
// // }
// //
// // class MyApp extends StatefulWidget {
// //   @override State<MyApp> createState() => _MyAppState();
// // }
// //
// // class _MyAppState extends State<MyApp> {
// //   late WebsocketService wsService;
// //   late TradingProvider tradingProvider;
// //
// //   @override
// //   void initState() {
// //     super.initState();
// //     tradingProvider = TradingProvider();
// //     wsService = WebsocketService('wss://stream.dhan.co/ws/market'); // replace
// //     wsService.connect();
// //     wsService.stream.listen((msg) {
// //       tradingProvider.ingest(msg);
// //     }, onError: (e) {
// //       // handle
// //     });
// //   }
// //
// //   @override
// //   void dispose() {
// //     wsService.disconnect();
// //     super.dispose();
// //   }
// //
// //   @override
// //   Widget build(BuildContext context) {
// //     final api = ApiService(backendBase: 'https://api.dhan.co/'        ); // replace
// //
// //     return MultiProvider(
// //       providers: [
// //         ChangeNotifierProvider.value(value: tradingProvider),
// //         Provider.value(value: api),
// //       ],
// //       child: MaterialApp(
// //         home: DashboardScreen(),
// //       ),
// //     );
// //   }
// // }
//
//
// import 'dart:async';
// import 'dart:convert';
//
// import 'package:flutter/material.dart';
// import 'package:provider/provider.dart';
// import 'package:websocket_channel/websocket_channel.dart';
// import 'package:http/http.dart' as http;
//
// /// CONFIG - change these to your backend
// const String WS_URL = "ws://127.0.0.1:8000/ws/ticks"; // or wss://... for TLS
// const String HTTP_LTP_BASE = "http://127.0.0.1:8000/ltp/"; // fallback
//
// /// Simple data model
// class Tick {
//   final String symbol;
//   final double ltp;
//   final double timestamp;
//
//   Tick({required this.symbol, required this.ltp, required this.timestamp});
//
//   factory Tick.fromJson(Map<String, dynamic> j) {
//     return Tick(
//       symbol: (j['symbol'] ?? '').toString(),
//       ltp: (j['ltp'] is num) ? (j['ltp'] as num).toDouble() : double.parse(j['ltp'].toString()),
//       timestamp: (j['timestamp'] is num) ? (j['timestamp'] as num).toDouble() : double.parse(j['timestamp'].toString()),
//     );
//   }
// }
//
// /// Provider that stores last ticks and handles connection
// class LtpProvider extends ChangeNotifier {
//   final Map<String, Tick> _ticks = {};
//   Map<String, Tick> get ticks => Map.unmodifiable(_ticks);
//
//   WebSocketChannel? _channel;
//   StreamSubscription? _sub;
//   Timer? _heartbeatTimer;
//   bool _manuallyStopped = false;
//
//   // Reconnect/backoff state
//   int _reconnectAttempts = 0;
//   bool get connected => _channel != null;
//
//   /// Start WS connection
//   void startWebSocket({String url = WS_URL}) {
//     _manuallyStopped = false;
//     _connect(url);
//   }
//
//   /// Stop WS connection
//   void stopWebSocket() {
//     _manuallyStopped = true;
//     _heartbeatTimer?.cancel();
//     _sub?.cancel();
//     _channel?.sink.close();
//     _channel = null;
//     _sub = null;
//     notifyListeners();
//   }
//
//   void _connect(String url) {
//     try {
//       _channel = WebSocketChannel.connect(Uri.parse(url));
//       _reconnectAttempts = 0;
//       _sub = _channel!.stream.listen(_onMessage,
//           onDone: _onDone, onError: _onError, cancelOnError: true);
//
//       // Optional: send a subscription message if your backend expects it
//       // _channel!.sink.add(jsonEncode({"action":"subscribe","symbols":["RELIANCE","TCS"]}));
//
//       // heartbeat to keep socket alive (if needed)
//       _heartbeatTimer?.cancel();
//       _heartbeatTimer = Timer.periodic(const Duration(seconds: 25), (_) {
//         try {
//           _channel?.sink.add('{"type":"ping"}');
//         } catch (_) {}
//       });
//
//       notifyListeners();
//     } catch (e) {
//       _scheduleReconnect();
//     }
//   }
//
//   void _onMessage(dynamic message) {
//     // Accept strings and JSON
//     try {
//       if (message is String) {
//         final j = jsonDecode(message);
//         if (j is Map<String, dynamic>) {
//           final tick = Tick.fromJson(j);
//           _ticks[tick.symbol.toUpperCase()] = tick;
//           notifyListeners();
//         }
//       } else if (message is List<int>) {
//         final s = utf8.decode(message);
//         final j = jsonDecode(s);
//         final tick = Tick.fromJson(j as Map<String, dynamic>);
//         _ticks[tick.symbol.toUpperCase()] = tick;
//         notifyListeners();
//       }
//     } catch (e) {
//       // ignore malformed messages but log in debug
//       debugPrint("WS parse error: $e | msg: $message");
//     }
//   }
//
//   void _onDone() {
//     debugPrint("WebSocket done.");
//     _channel = null;
//     _sub = null;
//     _heartbeatTimer?.cancel();
//     if (!_manuallyStopped) _scheduleReconnect();
//     notifyListeners();
//   }
//
//   void _onError(Object err) {
//     debugPrint("WebSocket error: $err");
//     _channel = null;
//     _sub = null;
//     _heartbeatTimer?.cancel();
//     if (!_manuallyStopped) _scheduleReconnect();
//     notifyListeners();
//   }
//
//   void _scheduleReconnect() {
//     _reconnectAttempts++;
//     final delay = _computeBackoff(_reconnectAttempts);
//     debugPrint("Reconnecting in ${delay.inSeconds}s (attempt $_reconnectAttempts)");
//     Future.delayed(delay, () {
//       if (!_manuallyStopped) _connect(WS_URL);
//     });
//   }
//
//   Duration _computeBackoff(int attempts) {
//     // exponential with cap
//     final base = 2;
//     final seconds = (attempts <= 0) ? 1 : (base * attempts);
//     final capped = seconds.clamp(1, 60);
//     return Duration(seconds: capped);
//   }
//
//   /// manual HTTP poll fallback for a symbol
//   Future<Tick?> fetchLtpViaHttp(String symbol) async {
//     final s = symbol.toUpperCase().trim();
//     final url = "$HTTP_LTP_BASE$s";
//     try {
//       final r = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 5));
//       if (r.statusCode == 200) {
//         final j = jsonDecode(r.body);
//         return Tick.fromJson(j);
//       }
//     } catch (e) {
//       debugPrint("HTTP LTP fetch error: $e");
//     }
//     return null;
//   }
//
//   /// Helpful helper to get one symbol either from map or via HTTP fallback
//   Future<Tick?> getLtpFor(String symbol, {bool httpFallback = true}) async {
//     final s = symbol.toUpperCase().trim();
//     if (_ticks.containsKey(s)) return _ticks[s];
//
//     if (httpFallback) {
//       return await fetchLtpViaHttp(s);
//     }
//     return null;
//   }
//
//   @override
//   void dispose() {
//     stopWebSocket();
//     super.dispose();
//   }
// }
//
// void main() {
//   runApp(
//     ChangeNotifierProvider(
//       create: (_) => LtpProvider()..startWebSocket(),
//       child: const MyApp(),
//     ),
//   );
// }
//
// class MyApp extends StatelessWidget {
//   const MyApp({super.key});
//   @override
//   Widget build(BuildContext context) {
//     return MaterialApp(
//       title: 'Live LTP',
//       theme: ThemeData.dark(),
//       home: const LtpHomePage(),
//     );
//   }
// }
//
// class LtpHomePage extends StatefulWidget {
//   const LtpHomePage({super.key});
//   @override
//   State<LtpHomePage> createState() => _LtpHomePageState();
// }
//
// class _LtpHomePageState extends State<LtpHomePage> {
//   final _manualSymbolCtrl = TextEditingController();
//
//   @override
//   void dispose() {
//     _manualSymbolCtrl.dispose();
//     super.dispose();
//   }
//
//   @override
//   Widget build(BuildContext context) {
//     final provider = context.watch<LtpProvider>();
//     final ticks = provider.ticks.values.toList()
//       ..sort((a, b) => b.timestamp.compareTo(a.timestamp));
//
//     return Scaffold(
//       appBar: AppBar(
//         title: const Text('Live LTP'),
//         actions: [
//           IconButton(
//             icon: Icon(provider.connected ? Icons.cloud_done : Icons.cloud_off),
//             onPressed: () {
//               // toggle manual restart/stop
//               if (provider.connected) {
//                 provider.stopWebSocket();
//               } else {
//                 provider.startWebSocket();
//               }
//             },
//             tooltip: provider.connected ? 'Disconnect' : 'Connect',
//           ),
//           const SizedBox(width: 8),
//         ],
//       ),
//       body: Column(
//         children: [
//           _buildControlRow(context),
//           Expanded(
//             child: RefreshIndicator(
//               onRefresh: () async {
//                 // quick manual refresh: nothing to do for WS; we could call HTTP fallback for a sample symbol
//                 // leave empty or call provider.fetchLtpViaHttp for selected symbol
//               },
//               child: ListView.builder(
//                 itemCount: ticks.length,
//                 itemBuilder: (context, i) {
//                   final t = ticks[i];
//                   return ListTile(
//                     title: Text(t.symbol, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
//                     subtitle: Text("Updated: ${DateTime.fromMillisecondsSinceEpoch((t.timestamp * 1000).toInt())}"),
//                     trailing: Text(t.ltp.toStringAsFixed(2), style: const TextStyle(fontSize: 18)),
//                   );
//                 },
//               ),
//             ),
//           ),
//         ],
//       ),
//     );
//   }
//
//   Widget _buildControlRow(BuildContext context) {
//     final provider = context.read<LtpProvider>();
//     return Padding(
//       padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
//       child: Row(
//         children: [
//           Expanded(
//             child: TextField(
//               controller: _manualSymbolCtrl,
//               textCapitalization: TextCapitalization.characters,
//               decoration: const InputDecoration(
//                 labelText: 'Symbol (e.g., RELIANCE)',
//                 border: OutlineInputBorder(),
//               ),
//             ),
//           ),
//           const SizedBox(width: 8),
//           ElevatedButton(
//             child: const Text('Fetch (HTTP)'),
//             onPressed: () async {
//               final sym = _manualSymbolCtrl.text.trim();
//               if (sym.isEmpty) return;
//               final tick = await provider.fetchLtpViaHttp(sym);
//               if (tick != null) {
//                 // show small snackbar
//                 if (!mounted) return;
//                 ScaffoldMessenger.of(context).showSnackBar(
//                   SnackBar(content: Text('${tick.symbol} → ${tick.ltp.toStringAsFixed(2)}')),
//                 );
//               } else {
//                 if (!mounted) return;
//                 ScaffoldMessenger.of(context).showSnackBar(
//                   const SnackBar(content: Text('No data (HTTP)')),
//                 );
//               }
//             },
//           ),
//         ],
//       ),
//     );
//   }
// }
//
//
// import 'package:flutter/material.dart';
// import 'package:provider/provider.dart';
// import 'providers/ltp_provider.dart';
// import 'widgets/ltp_widget.dart';
//
// void main() {
//   runApp(
//     MultiProvider(
//       providers: [
//         ChangeNotifierProvider(
//           create: (_) => LtpProvider("RELIANCE"),
//         ),
//       ],
//       child: const MyApp(),
//     ),
//   );
// }
//
//
// class MyApp extends StatelessWidget {
//   const MyApp({super.key});
//
//   @override
//   Widget build(BuildContext context) {
//     return MaterialApp(
//       title: 'Live LTP',
//       home: Scaffold(
//         appBar: AppBar(title: const Text("Live Market Price")),
//         body: const Center(
//           child: LtpWidget(),
//         ),
//       ),
//     );
//   }
// }



//
// import 'package:flutter/material.dart';
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
//     return MaterialApp(
//       debugShowCheckedModeBanner: false,
//       home: Scaffold(
//         appBar: AppBar(title: const Text("Live LTP")),
//         body: const Center(
//           child: LtpWidget(symbol: "RELIANCE"),
//         ),
//       ),
//     );
//   }
// }

//
// import 'package:flutter/material.dart';
// import 'package:provider/provider.dart';
//
// import 'app.dart';
// import 'providers/ltp_provider.dart';
//
// void main() {
//   WidgetsFlutterBinding.ensureInitialized();
//
//   runApp(
//     MultiProvider(
//       providers: [
//         ChangeNotifierProvider(
//           create: (_) => LtpProvider()..connect("RELIANCE"),
//         ),
//       ],
//       child: const MyApp(),
//     ),
//   );
// }


import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'providers/trading_provider.dart';
import 'screens/dashboard_screen.dart';

void main() {
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => TradingProvider()),
      ],
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: const DashboardScreen(),
    );
  }
}
