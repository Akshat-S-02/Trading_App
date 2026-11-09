import 'dart:convert';
import 'package:http/http.dart' as http;
import 'auth_service.dart';

/// Market search against `/api/market` (the only call the app still makes here).
class ApiService {
  final String backendBase;
  ApiService({required this.backendBase});

  Future<List<dynamic>> searchStocks(String query) async {
    final uri = Uri.parse('$backendBase/search').replace(queryParameters: {'query': query});
    final res = await http.get(uri, headers: await AuthService.authHeaders())
        .timeout(const Duration(seconds: 10));
    AuthService.checkAuth(res);
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body);
      return data['results'];
    }
    return [];
  }
}
