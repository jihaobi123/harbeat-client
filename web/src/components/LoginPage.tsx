import { useState, FormEvent } from 'react';
import { useAuthStore } from '../store/useAuthStore';

export default function LoginPage() {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [danceStyle, setDanceStyle] = useState('');
  const { login, register, loading, error, clearError } = useAuthStore();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    clearError();
    if (isRegister) {
      await register(username, password, danceStyle || undefined);
    } else {
      await login(username, password);
    }
  };

  const styles = ['hiphop', 'popping', 'locking', 'breaking', 'house', 'waacking', 'krump', 'jazz'];

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">HarBeat</h1>
          <p className="text-gray-400">智能 DJ 混音系统</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-gray-900 rounded-2xl p-8 shadow-xl space-y-5">
          <h2 className="text-xl font-semibold text-white">
            {isRegister ? '注册' : '登录'}
          </h2>

          <div>
            <label className="block text-sm text-gray-400 mb-1">用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500 transition-colors"
              placeholder="输入用户名"
              required
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500 transition-colors"
              placeholder="输入密码"
              required
            />
          </div>

          {isRegister && (
            <div>
              <label className="block text-sm text-gray-400 mb-1">舞种偏好（可选）</label>
              <select
                value={danceStyle}
                onChange={(e) => setDanceStyle(e.target.value)}
                className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
              >
                <option value="">不指定</option>
                {styles.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          )}

          {error && (
            <div className="bg-red-900/50 border border-red-700 text-red-300 px-4 py-2 rounded-lg text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-semibold rounded-lg transition-colors"
          >
            {loading ? '处理中...' : isRegister ? '注册' : '登录'}
          </button>

          <p className="text-center text-sm text-gray-400">
            {isRegister ? '已有账号？' : '没有账号？'}
            <button
              type="button"
              onClick={() => { setIsRegister(!isRegister); clearError(); }}
              className="ml-1 text-purple-400 hover:text-purple-300"
            >
              {isRegister ? '去登录' : '去注册'}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
