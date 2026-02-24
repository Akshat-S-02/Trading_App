// TODO Implement this library.

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import '../app_config.dart';

class AdminScreen extends StatefulWidget {
  @override
  State createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  final _amountCtl = TextEditingController();

  Future<void> _addTokens() async {
    final amt = int.tryParse(_amountCtl.text) ?? 0;
    if (amt <= 0) return;
    final url = '$kHttpBase/api/admin/add_tokens';
    await http.post(Uri.parse(url),
        headers: {'Content-Type': 'application/json'},
        body: '{"amount": $amt}');
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Added ₹$amt tokens (backend request sent)')));
  }

  @override
  Widget build(BuildContext c) {
    return Scaffold(
      appBar: AppBar(title: Text('Admin')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            TextField(controller: _amountCtl, keyboardType: TextInputType.number, decoration: InputDecoration(labelText: 'Amount to add (₹)')),
            SizedBox(height: 12),
            ElevatedButton(onPressed: _addTokens, child: Text('Add tokens')),
          ],
        ),
      ),
    );
  }
}
