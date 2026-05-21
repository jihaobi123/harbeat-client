import 'package:flutter/material.dart';
import 'package:harbeat_app/core/config/theme_config.dart';
import 'package:harbeat_app/core/utils/logger.dart';
import 'package:harbeat_app/data/models/session_model.dart';
import 'package:harbeat_app/core/services/session_service.dart';

class SessionHistoryPage extends StatefulWidget {
  const SessionHistoryPage({super.key});

  @override
  State<SessionHistoryPage> createState() => _SessionHistoryPageState();
}

class _SessionHistoryPageState extends State<SessionHistoryPage> {
  final SessionService _sessionService = SessionService();
  List<SessionModel> _sessions = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadSessions();
  }

  Future<void> _loadSessions() async {
    setState(() {
      _isLoading = true;
    });
    await Future.delayed(const Duration(milliseconds: 100));
    setState(() {
      _sessions = _sessionService.sessions;
      _isLoading = false;
    });
  }

  Future<void> _deleteSession(SessionModel session) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: ThemeConfig.backgroundSecondary,
        title: Text(
          '删除会话',
          style: TextStyle(color: ThemeConfig.textLight, fontWeight: FontWeight.bold),
        ),
        content: Text(
          '确定要删除 ${session.playlistName ?? '这个'} 的演出记录吗？',
          style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.8)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text('取消', style: TextStyle(color: ThemeConfig.textLight)),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: ThemeConfig.accentRed,
            ),
            child: Text('删除', style: TextStyle(color: ThemeConfig.textLight)),
          ),
        ],
      ),
    );

    if (confirm == true) {
      await _sessionService.deleteSession(session.id);
      await _loadSessions();
    }
  }

  Future<void> _clearAllSessions() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: ThemeConfig.backgroundSecondary,
        title: Text(
          '清空所有记录',
          style: TextStyle(color: ThemeConfig.textLight, fontWeight: FontWeight.bold),
        ),
        content: Text(
          '确定要清空所有演出记录吗？此操作不可恢复。',
          style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.8)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text('取消', style: TextStyle(color: ThemeConfig.textLight)),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: ThemeConfig.accentRed,
            ),
            child: Text('清空', style: TextStyle(color: ThemeConfig.textLight)),
          ),
        ],
      ),
    );

    if (confirm == true) {
      await _sessionService.clearSessions();
      await _loadSessions();
    }
  }

  void _showSessionDetail(SessionModel session) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => SessionDetailPage(session: session),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ThemeConfig.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: ThemeConfig.backgroundPrimary,
        elevation: 0,
        title: Row(
          children: [
            Icon(Icons.history, color: ThemeConfig.accentOrange),
            const SizedBox(width: 12),
            Text(
              '演出记录',
              style: TextStyle(
                color: ThemeConfig.textLight,
                fontSize: ThemeConfig.fontSizeLarge,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
        actions: [
          if (_sessions.isNotEmpty)
            IconButton(
              icon: Icon(Icons.delete_sweep, color: ThemeConfig.accentRed),
              onPressed: _clearAllSessions,
              tooltip: '清空所有记录',
            ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _sessions.isEmpty
              ? _buildEmptyState()
              : _buildSessionList(),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.music_note_outlined,
            size: 80,
            color: ThemeConfig.textLight.withOpacity(0.3),
          ),
          const SizedBox(height: 24),
          Text(
            '暂无演出记录',
            style: TextStyle(
              color: ThemeConfig.textLight.withOpacity(0.6),
              fontSize: ThemeConfig.fontSizeMedium,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '开始演出后，记录将显示在这里',
            style: TextStyle(
              color: ThemeConfig.textLight.withOpacity(0.4),
              fontSize: ThemeConfig.fontSizeSmall,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSessionList() {
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _sessions.length,
      itemBuilder: (context, index) {
        final session = _sessions[index];
        return _buildSessionCard(session);
      },
    );
  }

  Widget _buildSessionCard(SessionModel session) {
    final dateStr = '${session.startTime.month}月${session.startTime.day}日';
    final timeStr = '${session.startTime.hour.toString().padLeft(2, '0')}:${session.startTime.minute.toString().padLeft(2, '0')}';

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: ThemeConfig.backgroundSecondary.withOpacity(0.2),
        borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
        border: Border.all(
          color: ThemeConfig.backgroundSecondary.withOpacity(0.3),
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => _showSessionDetail(session),
          borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(
                                Icons.event,
                                color: ThemeConfig.accentOrange,
                                size: 20,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                session.playlistName ?? '演出',
                                style: TextStyle(
                                  color: ThemeConfig.textLight,
                                  fontSize: ThemeConfig.fontSizeMedium,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 4),
                          Text(
                            '设备: ${session.deviceName}',
                            style: TextStyle(
                              color: ThemeConfig.textLight.withOpacity(0.7),
                              fontSize: ThemeConfig.fontSizeSmall,
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      icon: Icon(Icons.delete_outline, color: ThemeConfig.accentRed.withOpacity(0.7)),
                      onPressed: () => _deleteSession(session),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: Row(
                        children: [
                          Icon(
                            Icons.access_time,
                            color: ThemeConfig.textLight.withOpacity(0.5),
                            size: 16,
                          ),
                          const SizedBox(width: 6),
                          Text(
                            '$dateStr $timeStr',
                            style: TextStyle(
                              color: ThemeConfig.textLight.withOpacity(0.6),
                              fontSize: ThemeConfig.fontSizeSmall,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: ThemeConfig.backgroundSecondary,
                        borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
                      ),
                      child: Text(
                        '${session.totalEvents} 次操作',
                        style: TextStyle(
                          color: ThemeConfig.textLight.withOpacity(0.7),
                          fontSize: ThemeConfig.fontSizeSmall,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: session.endTime == null
                            ? ThemeConfig.accentSuccess.withOpacity(0.2)
                            : ThemeConfig.backgroundSecondary,
                        borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
                      ),
                      child: Text(
                        session.durationText,
                        style: TextStyle(
                          color: session.endTime == null
                              ? ThemeConfig.accentSuccess
                              : ThemeConfig.textLight.withOpacity(0.7),
                          fontSize: ThemeConfig.fontSizeSmall,
                          fontWeight: session.endTime == null ? FontWeight.bold : FontWeight.normal,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class SessionDetailPage extends StatelessWidget {
  final SessionModel session;

  const SessionDetailPage({super.key, required this.session});

  @override
  Widget build(BuildContext context) {
    final dateStr = '${session.startTime.year}年${session.startTime.month}月${session.startTime.day}日';

    return Scaffold(
      backgroundColor: ThemeConfig.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: ThemeConfig.backgroundPrimary,
        elevation: 0,
        title: Text(
          '演出详情',
          style: TextStyle(
            color: ThemeConfig.textLight,
            fontSize: ThemeConfig.fontSizeLarge,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _buildSessionInfo(),
          const SizedBox(height: 24),
          _buildEventsList(),
        ],
      ),
    );
  }

  Widget _buildSessionInfo() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ThemeConfig.backgroundSecondary.withOpacity(0.2),
        borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
        border: Border.all(color: ThemeConfig.backgroundSecondary.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.music_note, color: ThemeConfig.accentOrange, size: 28),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  session.playlistName ?? '演出',
                  style: TextStyle(
                    color: ThemeConfig.textLight,
                    fontSize: ThemeConfig.fontSizeLarge,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '设备',
                      style: TextStyle(
                        color: ThemeConfig.textLight.withOpacity(0.5),
                        fontSize: ThemeConfig.fontSizeSmall,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      session.deviceName,
                      style: TextStyle(
                        color: ThemeConfig.textLight,
                        fontSize: ThemeConfig.fontSizeMedium,
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      '操作次数',
                      style: TextStyle(
                        color: ThemeConfig.textLight.withOpacity(0.5),
                        fontSize: ThemeConfig.fontSizeSmall,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${session.totalEvents} 次',
                      style: TextStyle(
                        color: ThemeConfig.textLight,
                        fontSize: ThemeConfig.fontSizeMedium,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '开始时间',
                      style: TextStyle(
                        color: ThemeConfig.textLight.withOpacity(0.5),
                        fontSize: ThemeConfig.fontSizeSmall,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${session.startTime.hour.toString().padLeft(2, '0')}:${session.startTime.minute.toString().padLeft(2, '0')}',
                      style: TextStyle(
                        color: ThemeConfig.accentSuccess,
                        fontSize: ThemeConfig.fontSizeMedium,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      '时长',
                      style: TextStyle(
                        color: ThemeConfig.textLight.withOpacity(0.5),
                        fontSize: ThemeConfig.fontSizeSmall,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      session.durationText,
                      style: TextStyle(
                        color: ThemeConfig.textLight,
                        fontSize: ThemeConfig.fontSizeMedium,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildEventsList() {
    if (session.events.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(48),
          child: Text(
            '暂无操作记录',
            style: TextStyle(
              color: ThemeConfig.textLight.withOpacity(0.4),
              fontSize: ThemeConfig.fontSizeMedium,
            ),
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '操作记录',
          style: TextStyle(
            color: ThemeConfig.textLight,
            fontSize: ThemeConfig.fontSizeMedium,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 12),
        ...session.events.map((event) => _buildEventItem(event)),
      ],
    );
  }

  Widget _buildEventItem(SessionEvent event) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: ThemeConfig.backgroundSecondary.withOpacity(0.15),
        borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: event.eventColor.withOpacity(0.2),
              borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
            ),
            child: Icon(event.eventIcon, color: event.eventColor, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  event.description,
                  style: TextStyle(
                    color: ThemeConfig.textLight,
                    fontSize: ThemeConfig.fontSizeSmall,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  event.timeText,
                  style: TextStyle(
                    color: ThemeConfig.textLight.withOpacity(0.5),
                    fontSize: ThemeConfig.fontSizeSmall,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
