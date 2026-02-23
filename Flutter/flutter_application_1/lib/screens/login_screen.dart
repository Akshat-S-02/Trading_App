// TODO Implement this library.

import 'package:flutter/material.dart';

class LoginScreen extends StatelessWidget {
  final TextEditingController _userCtl = TextEditingController(text: 'admin');

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Login')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            TextField(controller: _userCtl, decoration: const InputDecoration(labelText: 'Username')),
            const SizedBox(height: 12),
            ElevatedButton(
              child: const Text('Sign in (local)'),
              onPressed: () {
                Navigator.pushReplacementNamed(context, '/dashboard');
              },
            ),
          ],
        ),
      ),
    );
  }
}
