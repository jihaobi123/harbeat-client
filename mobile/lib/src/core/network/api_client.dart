import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/api_response.dart';
import '../storage/token_storage.dart';

class ApiClient {
  ApiClient({http.Client? httpClient}) : _httpClient = httpClient ?? http.Client();

  final http.Client _httpClient;

  String buildUrl(String path, {Map<String, String>? query}) {
    return Uri.parse('${AppConfig.apiBaseUrl}$path')
        .replace(queryParameters: query)
        .toString();
  }

  Future<T> get<T>(
    String path, {
    Map<String, String>? query,
    required T Function(dynamic json) parser,
  }) {
    return _request('GET', path, query: query, parser: parser);
  }

  Future<T> post<T>(
    String path, {
    Object? body,
    Map<String, String>? query,
    required T Function(dynamic json) parser,
  }) {
    return _request('POST', path, body: body, query: query, parser: parser);
  }

  Future<T> patch<T>(
    String path, {
    Object? body,
    Map<String, String>? query,
    required T Function(dynamic json) parser,
  }) {
    return _request('PATCH', path, body: body, query: query, parser: parser);
  }

  Future<T> delete<T>(
    String path, {
    Object? body,
    Map<String, String>? query,
    required T Function(dynamic json) parser,
  }) {
    return _request('DELETE', path, body: body, query: query, parser: parser);
  }

  Future<T> _request<T>(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
    required T Function(dynamic json) parser,
  }) async {
    final token = await TokenStorage.readToken();
    final uri = Uri.parse('${AppConfig.apiBaseUrl}$path').replace(queryParameters: query);

    final headers = <String, String>{
      'Accept': 'application/json',
      if (body != null) 'Content-Type': 'application/json',
      if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
    };

    http.Response response;

    try {
      switch (method) {
        case 'GET':
          response = await _httpClient
              .get(uri, headers: headers)
              .timeout(AppConfig.requestTimeout);
          break;
        case 'POST':
          response = await _httpClient
              .post(uri, headers: headers, body: body == null ? null : jsonEncode(body))
              .timeout(AppConfig.requestTimeout);
          break;
        case 'PATCH':
          response = await _httpClient
              .patch(uri, headers: headers, body: body == null ? null : jsonEncode(body))
              .timeout(AppConfig.requestTimeout);
          break;
        case 'DELETE':
          response = await _httpClient
              .delete(uri, headers: headers, body: body == null ? null : jsonEncode(body))
              .timeout(AppConfig.requestTimeout);
          break;
        default:
          throw UnsupportedError('Unsupported method: $method');
      }
    } on TimeoutException {
      throw Exception('Request timeout: $path');
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final apiResponse = ApiResponse<T>.fromJson(decoded, parser);

    if (response.statusCode < 200 || response.statusCode >= 300 || apiResponse.code != 0) {
      throw Exception(apiResponse.message);
    }

    return apiResponse.data;
  }
}
