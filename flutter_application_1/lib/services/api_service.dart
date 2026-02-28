// import 'package:dio/dio.dart';
// import 'package:flutter/foundation.dart';
//
// class ApiService {
//   final Dio _dio = Dio(BaseOptions(baseUrl: "http://10.0.2.2:8000"));
//   final baseUrl = 'http://10.0.2.2:8000';
//
//   Future<Response> getStockList() async {
//     print("Fetching stocks...");
//     final response = await _dio.get('/stocks');
//     print("Stocks response: ${response.data}");
//     return response;
//   }
//
//   Future<Response> getPortfolio() async {
//     print("Fetching portfolio...");
//     final response = await _dio.get('/portfolio');
//     print("Portfolio response: ${response.data}");
//     return response;
//   }
//
//   Future<Response> buyStock(String symbol, double amount) async {
//     return await _dio.post('/trade/buy', data: {
//       "symbol": symbol,
//       "amount": amount,
//     });
//   }
//
//   Future<Response> sellStock(String symbol, double amount) async {
//     return await _dio.post('/trade/sell', data: {
//       "symbol": symbol,
//       "amount": amount,
//     });
//   }
//
//   Future<Response> addTokens(double tokens) async {
//     return await _dio.post('/admin/add_tokens', data: {
//       "amount": tokens,
//     });
//   }
//
//   Future<Response> getHistory() async {
//     return await _dio.get('/history');
//   }
//
//   // ✅ Correct, single version of searchStocks
//   Future<List<Map<String, dynamic>>> searchStocks(String query) async {
//     try {
//       final response = await _dio.get(
//         '/search_stocks',
//         queryParameters: {'query': query},
//       );
//
//       if (response.statusCode == 200 &&
//           response.data != null &&
//           response.data['results'] != null) {
//         return List<Map<String, dynamic>>.from(
//           (response.data['results'] as List).map(
//                 (item) => {
//               "symbol": item['symbol'] ?? 'Unknown',
//               "name": item['name'] ?? 'N/A',
//               "price": (item['price'] ?? 0).toDouble(),
//             },
//           ),
//         );
//       } else {
//         debugPrint('⚠️ Unexpected response format: ${response.data}');
//         return [];
//       }
//     } catch (e, st) {
//       debugPrint('❌ Error searching stocks: $e\n$st');
//       return [];
//     }
//   }
//
//   Future<Response> getLiveStock(String symbol) async {
//     print("Fetching live data for $symbol...");
//     return await _dio.get('/live_stock/$symbol');
//   }
//
//
//
//
// }


import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  final String backendBase;
  ApiService({required this.backendBase});

  Future<List<dynamic>> getStocks() async {
    final res = await http.get(Uri.parse('$backendBase/stocks'));
    return jsonDecode(res.body)['stocks'];
  }

  Future<Map<String, dynamic>> getPortfolio() async {
    final res = await http.get(Uri.parse('$backendBase/portfolio'));
    return jsonDecode(res.body);
  }

  Future<Map<String, dynamic>> getHistory() async {
    final res = await http.get(Uri.parse('$backendBase/history'));
    return jsonDecode(res.body);
  }

  Future<Map<String, dynamic>> trade(String symbol, double amount, String type) async {
    final res = await http.post(
      Uri.parse('$backendBase/trade'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'symbol': symbol, 'amount': amount, 'type': type}),
    );
    return jsonDecode(res.body);
  }
  Future<List<dynamic>> searchStocks(String query) async {
    final res = await http.get(Uri.parse('$backendBase/search?query=$query'));
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body);
      return data['results'];
    }
    return [];
  }

  Future<void> fetchLtp(String symbol) async {
    try {
      await http.get(Uri.parse('$backendBase/ltp/$symbol'));
    } catch (e) {
      print("Failed to fetch LTP for $symbol: $e");
    }
  }
}
