import '../../core/network/api_client.dart';
import 'models.dart';

class ProfileService {
  ProfileService({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<UserProfile> getProfile(int userId) {
    return _client.get<UserProfile>(
      '/api/profiles/$userId',
      parser: (json) => UserProfile.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<UserProfile> generateProfile(int userId) {
    return _client.post<UserProfile>(
      '/api/profiles/generate',
      body: {'user_id': userId},
      parser: (json) => UserProfile.fromJson(json as Map<String, dynamic>),
    );
  }
}
