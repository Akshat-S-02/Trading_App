//
// class LtpModel {
//   final String symbol;
//   final double ltp;
//
//   LtpModel({required this.symbol, required this.ltp});
//
//   factory LtpModel.fromJson(Map<String, dynamic> json) {
//     return LtpModel(
//       symbol: json["symbol"],
//       ltp: (json["ltp"] ?? 0).toDouble(),
//     );
//   }
// }
//
// class LtpModel {
//   final String symbol;
//   final double ltp;
//   final DateTime? updatedAt;
//
//   LtpModel({
//     required this.symbol,
//     required this.ltp,
//     this.updatedAt,
//   });
//
//   factory LtpModel.fromJson(Map<String, dynamic> json) {
//     final ts = json['timestamp'];
//     DateTime? dt;
//     if (ts != null) {
//       // backend is sending epoch seconds
//       final millis = (ts is num ? ts.toDouble() : double.parse(ts.toString())) * 1000;
//       dt = DateTime.fromMillisecondsSinceEpoch(millis.toInt(), isUtc: true).toLocal();
//     }
//
//     return LtpModel(
//       symbol: (json['symbol'] ?? '').toString().toUpperCase(),
//       ltp: (json['ltp'] as num).toDouble(),
//       updatedAt: dt,
//     );
//   }
// }

class LtpModel {
  final String symbol;
  final double ltp;
  final DateTime? updatedAt;
  final String? source;

  LtpModel({
    required this.symbol,
    required this.ltp,
    this.updatedAt,
    this.source,
  });
}
