import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../state/providers.dart';

class ReplayPage extends ConsumerStatefulWidget {
  const ReplayPage({super.key});

  @override
  ConsumerState<ReplayPage> createState() => _ReplayPageState();
}

class _ReplayPageState extends ConsumerState<ReplayPage> {
  List<dynamic> _sessions = [];
  Map<String, dynamic>? _selectedSession;
  List<dynamic> _events = [];
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _loadSessions();
  }

  Future<void> _loadSessions() async {
    setState(() => _isLoading = true);
    try {
      final jetson = ref.read(jetsonClientProvider);
      final playlists = await jetson.getPlaylists();
      setState(() {
        _sessions = playlists;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('加载失败: $e')),
        );
      }
    }
    setState(() => _isLoading = false);
  }

  Future<void> _loadSessionEvents(String sessionId) async {
    setState(() => _isLoading = true);
    try {
      final jetson = ref.read(jetsonClientProvider);
      final response = await jetson.getSessionEvents(sessionId);
      setState(() {
        _selectedSession = _sessions.firstWhere((s) => s['id'] == sessionId);
        _events = (response['events'] ?? []) as List;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('加载Events失败: $e')),
        );
      }
    }
    setState(() => _isLoading = false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('复盘'),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _selectedSession == null
              ? _buildSessionList(theme)
              : _buildEventTimeline(theme),
    );
  }

  Widget _buildSessionList(ThemeData theme) {
    if (_sessions.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.history,
              size: 64,
              color: theme.colorScheme.onSurface.withOpacity(0.3),
            ),
            const SizedBox(height: 16),
            Text(
              '暂无Session记录',
              style: theme.textTheme.titleMedium?.copyWith(
                color: theme.colorScheme.onSurface.withOpacity(0.5),
              ),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      itemCount: _sessions.length,
      itemBuilder: (context, index) {
        final session = _sessions[index];
        return Card(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: theme.colorScheme.primaryContainer,
              child: Icon(
                Icons.play_circle_outline,
                color: theme.colorScheme.primary,
              ),
            ),
            title: Text(session['name'] ?? 'Session ${session['id']}'),
            subtitle: Text(session['created_at'] ?? ''),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => _loadSessionEvents(session['id']),
          ),
        );
      },
    );
  }

  Widget _buildEventTimeline(ThemeData theme) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          color: theme.colorScheme.surfaceContainerHighest,
          child: Row(
            children: [
              IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: () {
                  setState(() {
                    _selectedSession = null;
                    _events = [];
                  });
                },
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  _selectedSession?['name'] ?? 'Session',
                  style: theme.textTheme.titleLarge,
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: _events.isEmpty
              ? Center(
                  child: Text(
                    '暂无Event记录',
                    style: theme.textTheme.bodyLarge?.copyWith(
                      color: theme.colorScheme.onSurface.withOpacity(0.5),
                    ),
                  ),
                )
              : ListView.builder(
                  itemCount: _events.length,
                  itemBuilder: (context, index) {
                    final event = _events[index];
                    return _EventTile(event: event);
                  },
                ),
        ),
      ],
    );
  }
}

class _EventTile extends StatelessWidget {
  final Map<String, dynamic> event;

  const _EventTile({required this.event});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final type = event['type'] ?? 'unknown';
    final timestamp = event['ts'];
    final timeStr = timestamp != null
        ? DateTime.fromMillisecondsSinceEpoch(timestamp).toString().substring(11, 19)
        : '';

    IconData icon;
    Color color;
    String description;

    switch (type) {
      case 'play_start':
        icon = Icons.play_arrow;
        color = Colors.green;
        description = '开始播放';
        break;
      case 'play_end':
        icon = Icons.stop;
        color = Colors.red;
        description = '停止播放';
        break;
      case 'pause':
        icon = Icons.pause;
        color = Colors.orange;
        description = '暂停';
        break;
      case 'resume':
        icon = Icons.play_arrow;
        color = Colors.green;
        description = '继续';
        break;
      case 'key_press':
        icon = Icons.touch_app;
        color = Colors.blue;
        description = '按键 ${event['data']?['key'] ?? '?'}';
        break;
      case 'transition':
        icon = Icons.swap_horiz;
        color = Colors.purple;
        description = '过渡';
        break;
      case 'next':
        icon = Icons.skip_next;
        color = Colors.teal;
        description = '切到下一首';
        break;
      default:
        icon = Icons.circle;
        color = Colors.grey;
        description = type;
    }

    return ListTile(
      leading: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: color.withOpacity(0.1),
          shape: BoxShape.circle,
        ),
        child: Icon(icon, color: color, size: 20),
      ),
      title: Text(description),
      subtitle: Text(timeStr),
    );
  }
}
