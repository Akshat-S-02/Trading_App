import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../ui/theme.dart';

final _inr = NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 2);
final _inrCompact = NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 0);

/// ₹1,23,456.78
String inr(num? v) => v == null ? '—' : _inr.format(v);

/// ₹1,23,457 (no paise) for large summary figures
String inrWhole(num? v) => v == null ? '—' : _inrCompact.format(v);

/// +₹120.50 / -₹80.00
String signedInr(num? v) {
  if (v == null) return '—';
  return '${v >= 0 ? '+' : '-'}${_inr.format(v.abs())}';
}

/// Colour for a P&L figure
Color pnlColor(num? v) {
  if (v == null || v == 0) return AppColors.secondary;
  return v > 0 ? AppColors.green : AppColors.red;
}

/// 'RELIANCE.NS' -> 'RELIANCE'
String bareSymbol(String s) => s.contains('.') ? s.split('.').first : s;

/// Local HH:mm from an ISO timestamp (naive timestamps are treated as UTC)
String timeOf(dynamic iso) {
  if (iso == null) return '--:--';
  var s = iso.toString();
  if (!s.endsWith('Z') && !RegExp(r'[+-]\d\d:\d\d$').hasMatch(s)) s = '${s}Z';
  final dt = DateTime.tryParse(s);
  if (dt == null) return '--:--';
  return DateFormat('dd MMM, HH:mm').format(dt.toLocal());
}

const kBuyColor = AppColors.green;
const kSellColor = AppColors.red;
const kCardColor = AppColors.card;
const kBgColor = AppColors.bg;
