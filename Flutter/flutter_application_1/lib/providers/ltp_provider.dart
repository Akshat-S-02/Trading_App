// // // import 'dart:async';
// // // import 'dart:convert';
// // // import 'package:flutter/material.dart';
// // // import 'package:web_socket_channel/web_socket_channel.dart';
// // // import 'ltp_model.dart';
// // //
// // // class LtpProvider with ChangeNotifier {
// // //   WebSocketChannel? _channel;
// // //   LtpData? _data;
// // //   bool _isConnected = false;
// // //   final String symbol;
// // //
// // //   LtpProvider(this.symbol) {
// // //     connect();
// // //   }
// // //
// // //   LtpData? get data => _data;
// // //   bool get isConnected => _isConnected;
// // //
// // //   void connect() {
// // //     // final url = "ws://127.0.0.1:8000/ws/ltp?symbol=$symbol";
// // //     final url = "ws://10.0.2.2:8000/ws/ltp?symbol=$symbol";
// // //
// // //     try {
// // //       _channel = WebSocketChannel.connect(Uri.parse(url));
// // //       _isConnected = true;
// // //
// // //       _channel!.stream.listen(
// // //             (message) {
// // //           final decoded = jsonDecode(message);
// // //
// // //           _data = LtpData.fromJson(decoded);
// // //           notifyListeners();
// // //         },
// // //         onError: (_) => reconnect(),
// // //         onDone: () => reconnect(),
// // //       );
// // //     } catch (e) {
// // //       reconnect();
// // //     }
// // //   }
// // //
// // //   void reconnect() {
// // //     _isConnected = false;
// // //     notifyListeners();
// // //
// // //     Future.delayed(const Duration(seconds: 2), () {
// // //       connect();
// // //     });
// // //   }
// // //
// // //   @override
// // //   void dispose() {
// // //     _channel?.sink.close();
// // //     super.dispose();
// // //   }
// // // }
// //
// // //
// // // import 'dart:convert';
// // // import 'package:flutter/foundation.dart';
// // // import '../services/websocket_service.dart';
// // //
// // // class LtpProvider extends ChangeNotifier {
// // //   WebSocketService? _ws;
// // //   double? price;
// // //   bool isConnecting = true;
// // //
// // //   LtpProvider(String s);
// // //
// // //   void connectLtp(String symbol) {
// // //     final url = "ws://192.168.0.111:8000/ws/ltp?symbol=$symbol";
// // //
// // //     _ws = WebSocketService(
// // //       url: url,
// // //       onMessage: (data) {
// // //         try {
// // //           final decoded = jsonDecode(data);
// // //           price = decoded["ltp"];
// // //           notifyListeners();
// // //         } catch (e) {
// // //           print("⚠️ Ingest error: $e");
// // //         }
// // //       },
// // //     );
// // //
// // //     _ws!.connect();
// // //   }
// // //
// // //   @override
// // //   void dispose() {
// // //     _ws?.dispose();
// // //     super.dispose();
// // //   }
// // // }
// // //
// // //
// // // import 'dart:convert';
// // // import 'package:flutter/foundation.dart';
// // // import '../../models/ltp_model.dart';
// // // import '../../services/websocket_service.dart';
// // //
// // // class LtpProvider extends ChangeNotifier {
// // //   WebSocketService? _ws;
// // //
// // //   LtpModel? live;
// // //   String? currentSymbol;
// // //
// // //   void connect(String symbol) {
// // //     currentSymbol = symbol.toUpperCase();
// // //
// // //     final url = "ws://10.0.2.2:8000/ws/ltp?symbol=$currentSymbol";
// // //
// // //     _ws = WebSocketService(
// // //       url: url,
// // //       onMessage: (data) {
// // //         try {
// // //           final decoded = jsonDecode(data);
// // //
// // //           if (decoded["ltp"] != null) {
// // //             live = LtpModel(
// // //               symbol: currentSymbol!,
// // //               ltp: (decoded["ltp"]).toDouble(),
// // //             );
// // //             notifyListeners();
// // //           }
// // //         } catch (e) {
// // //           print("⚠ LTP decode error: $e");
// // //         }
// // //       },
// // //     );
// // //
// // //     _ws!.connect();
// // //   }
// // //
// // //   @override
// // //   void dispose() {
// // //     _ws?.dispose();
// // //     super.dispose();
// // //   }
// // // }
// //
// //
// // import 'dart:convert';
// //
// // import 'package:flutter/material.dart';
// //
// // import '../models/ltp_model.dart';
// // import '../services/websocket_service.dart';
// //
// // /// Change this to your PC IP if testing from a *real* Android device.
// // /// For Android emulator keep 10.0.2.2
// // const String _wsBase = 'ws://10.0.2.2:8000';
// //
// // class LtpProvider extends ChangeNotifier {
// //   WebSocketService? _ws;
// //   LtpModel? live;
// //   String currentSymbol = "RELIANCE";
// //
// //   bool isConnecting = false;
// //   String? lastError;
// //
// //   void connect(String symbol) {
// //     // Normalize symbol
// //     currentSymbol = symbol.toUpperCase().trim();
// //
// //     // Close any previous channel
// //     _ws?.dispose();
// //     lastError = null;
// //     isConnecting = true;
// //     notifyListeners();
// //
// //     final url = '$_wsBase/ws/ltp?symbol=$currentSymbol';
// //
// //     _ws = WebSocketService(
// //       url: url,
// //       onMessage: (data) {
// //         try {
// //           final decoded = jsonDecode(data);
// //           if (decoded is Map && decoded['ltp'] != null) {
// //             live = LtpModel.fromJson(decoded as Map<String, dynamic>);
// //             isConnecting = false;
// //             lastError = null;
// //             notifyListeners();
// //           }
// //         } catch (e) {
// //           lastError = "Decode error: $e";
// //           notifyListeners();
// //         }
// //       },
// //     );
// //
// //     _ws!.connect();
// //   }
// //
// //   void refresh() {
// //     connect(currentSymbol);
// //   }
// //
// //   @override
// //   void dispose() {
// //     _ws?.dispose();
// //     super.dispose();
// //   }
// // }
//
//
// import 'dart:convert';
// import 'package:flutter/foundation.dart';
// import '../models/ltp_model.dart';
// import '../services/websocket_service.dart';
//
// class LtpProvider extends ChangeNotifier {
//   WebSocketService? _ws;
//
//   LtpModel? live;
//   String? currentSymbol;
//   bool isConnecting = false;
//
//   void connect(String symbol) {
//     final sym = symbol.trim().toUpperCase();
//     if (sym.isEmpty) return;
//
//     currentSymbol = sym;
//     isConnecting = true;
//     notifyListeners();
//
//     _ws?.dispose();
//
//     final url = "ws://10.0.2.2:8000/ws/ltp?symbol=$sym"; // or your LAN IP
//
//     _ws = WebSocketService(
//       url: url,
//       onMessage: (data) {
//         try {
//           final decoded = jsonDecode(data);
//           final ltp = (decoded['ltp'] as num?)?.toDouble();
//           if (ltp == null) return;
//
//           live = LtpModel(
//             symbol: sym,
//             ltp: ltp,
//             updatedAt: DateTime.now(),
//             source: decoded['source']?.toString() ?? 'WebSocket',
//           );
//           isConnecting = false;
//           notifyListeners();
//         } catch (e) {
//           debugPrint('⚠ LTP decode error: $e');
//         }
//       },
//       onError: (e) {
//         debugPrint('WS error: $e');
//         isConnecting = false;
//         notifyListeners();
//       },
//     );
//
//     _ws!.connect();
//   }
//
//   @override
//   void dispose() {
//     _ws?.dispose();
//     super.dispose();
//   }
// }

//
// import 'dart:convert';
// import 'package:flutter/foundation.dart';
// import '../services/websocket_service.dart';
// import '../models/ltp_model.dart';
//
// class LtpProvider extends ChangeNotifier {
//   WebSocketService? _ws;
//
//   LtpModel? live;
//   String? currentSymbol;
//   bool isConnecting = false;
//
//   LtpProvider();
//
//
//   void connect(String symbol) {
//     final sym = symbol.trim().toUpperCase();
//     if (sym.isEmpty) return;
//
//     currentSymbol = sym;
//     isConnecting = true;
//     notifyListeners();
//
//     _ws?.dispose();
//
//     final url = "ws://10.0.2.2:8000/ws/ltp?symbol=$sym";
//
//     _ws = WebSocketService(
//       url: url,
//       onMessage: (data) {
//         try {
//           final decoded = jsonDecode(data);
//
//           final price = (decoded["ltp"] as num).toDouble();
//
//           live = LtpModel(
//             symbol: sym,
//             ltp: price,
//             updatedAt: DateTime.now(),
//             source: "WS",
//           );
//
//           isConnecting = false;
//           notifyListeners();
//         } catch (e) {
//           debugPrint("LTP decode error: $e");
//           isConnecting = false;
//           notifyListeners();
//         }
//       },
//       onError: (e) {
//         debugPrint("WS Error: $e");
//         isConnecting = false;
//         notifyListeners();
//       },
//       onDone: () {
//         debugPrint("WS Closed");
//         notifyListeners();
//       },
//     );
//
//     _ws!.connect();
//   }
//
//   @override
//   void dispose() {
//     _ws?.dispose();
//     super.dispose();
//   }
// }


import 'dart:convert';
import 'package:flutter/foundation.dart';
import '../services/websocket_service.dart';
import '../models/ltp_model.dart';

class LtpProvider extends ChangeNotifier {
  WebSocketService? _ws;

  LtpModel? live;
  String? currentSymbol;
  bool isConnecting = false;

  void connect(String symbol) {
    final sym = symbol.trim().toUpperCase();
    if (sym.isEmpty) return;

    currentSymbol = sym;
    isConnecting = true;
    notifyListeners();

    _ws?.dispose();

    final url = "ws://10.0.2.2:8000/ws/ltp?symbol=$sym";

    _ws = WebSocketService(
      url: url,
      onMessage: (data) {
        try {
          final decoded = jsonDecode(data);

          debugPrint('DECODED: $decoded'); // <--- important

          final ltp = decoded['ltp'];
          if (ltp == null) {
            // waiting payload, don’t crash
            return;
          }

          final price = (ltp as num).toDouble();

          live = LtpModel(
            symbol: sym,
            ltp: price,
            updatedAt: DateTime.now(),
            source: decoded['source']?.toString() ?? 'websocket',
          );

          isConnecting = false;
          notifyListeners();
        } catch (e) {
          debugPrint("LTP decode error: $e");
          isConnecting = false;
          notifyListeners();
        }
      },
      onError: (e) {
        debugPrint("WS Error: $e");
        isConnecting = false;
        notifyListeners();
      },
      onDone: () {
        debugPrint("WS Closed");
        notifyListeners();
      },
    );

    _ws!.connect();
  }

  @override
  void dispose() {
    _ws?.dispose();
    super.dispose();
  }
}
